#!/usr/bin/env python3
"""美股投資分析報告產生器 — Streamlit 網頁介面。

啟動：
    source .venv/bin/activate
    streamlit run app.py

功能：輸入代號/公司名 → 代號驗證/建議 → 線上預覽關鍵數據與圖表
     → 網頁內嵌 PDF 預覽 → 一鍵下載 PDF。報告結果具快取（同代號重跑更快）。

亦支援網址參數自動帶入：http://localhost:8501/?ticker=ORCL
"""
from __future__ import annotations

import logging

import bootstrap_libs  # noqa: F401  # 確保 weasyprint 原生庫路徑（在 import 前）

import streamlit as st

from ai import llm_client
from ai.llm_client import provider_label
from config import OUTPUT_DIR
from core.report_builder import build_report_data
from core.ticker_resolver import StockNotFoundError, search_candidates
from report import pdf_builder
from utils.logging_setup import setup_logging
from viz import interactive

setup_logging(False)
logger = logging.getLogger(__name__)

st.set_page_config(page_title="美股／台股投資分析報告產生器", page_icon="📈", layout="wide")


# ---------------------------------------------------------------------------
# 快取層：同一輸入短時間內重跑直接取用（TTL 1 小時）
# ---------------------------------------------------------------------------
@st.cache_data(ttl=3600, show_spinner=False)
def cached_report(query: str, ai_token: str):
    # ai_token 僅作為快取鍵：金鑰 / 供應商改變時強制重新產生（不含金鑰明文）
    return build_report_data(query)


@st.cache_data(ttl=1800, show_spinner=False)
def cached_candidates(query: str):
    return search_candidates(query)


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------
def _fmt_money(v, tw=False):
    if v is None:
        return "—"
    if tw:
        if abs(v) >= 1e12:
            return f"NT${v/1e12:,.2f}兆"
        if abs(v) >= 1e8:
            return f"NT${v/1e8:,.1f}億"
        if abs(v) >= 1e4:
            return f"NT${v/1e4:,.0f}萬"
        return f"NT${v:,.0f}"
    for unit, size in (("T", 1e12), ("B", 1e9), ("M", 1e6)):
        if abs(v) >= size:
            return f"${v/size:,.2f}{unit}"
    return f"${v:,.0f}"


def _fmt_price(v, tw=False):
    if v is None:
        return "—"
    return f"{'NT$' if tw else '$'}{v:,.2f}"


def _fmt_pct(ratio):
    return "—" if ratio is None else f"{ratio*100:.1f}%"


@st.cache_data(ttl=1800, show_spinner=False)
def _pdf_page_images(pdf_bytes: bytes, dpi: int = 130) -> list[bytes]:
    """將 PDF 每頁算成 PNG bytes（不依賴瀏覽器 PDF 外掛，Chrome 不會封鎖）。"""
    import fitz  # PyMuPDF

    pages: list[bytes] = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page in doc:
            pix = page.get_pixmap(dpi=dpi)
            pages.append(pix.tobytes("png"))
    return pages


def _embed_pdf(pdf_bytes: bytes):
    """內嵌完整報告預覽：逐頁渲染為圖片顯示。

    不使用 <iframe>/data:/blob: 的 PDF 檢視器（Chrome 會在沙箱 iframe 內封鎖），
    改以 PyMuPDF 後端逐頁轉圖，用 st.image 內嵌，任何瀏覽器皆可正常顯示。
    """
    try:
        images = _pdf_page_images(pdf_bytes)
    except Exception as exc:  # noqa: BLE001
        st.warning(f"無法產生內嵌預覽（{exc}）；請使用上方「⬇️ 下載 PDF 報告」按鈕開啟。")
        return

    with st.container(height=880, border=True):
        for i, png in enumerate(images, 1):
            st.image(png, use_container_width=True)
            st.caption(f"第 {i} / {len(images)} 頁")


def _run_report(query: str):
    """執行（或取用快取）並渲染整個報告畫面。"""
    try:
        with st.spinner("擷取資料與分析中（新聞、財報、估值、同業）…"):
            report = cached_report(query, llm_client.credentials_fingerprint())
    except StockNotFoundError as exc:
        st.error(str(exc))
        return
    except Exception as exc:  # noqa: BLE001
        st.error(f"產生報告時發生錯誤：{exc}")
        return

    p, km = report.profile, report.key_metrics
    st.subheader(f"{p.company_name}（{p.ticker}）")
    st.caption(f"{p.exchange_name or ('台股' if p.market in ('TWSE','TPEX') else '美股')} · {p.sector or 'N/A'} / {p.industry or 'N/A'}")

    # === 綜合體質評分（最先呈現的一眼判斷）===
    sc = report.scorecard
    if sc.overall is not None:
        st.markdown("#### 綜合體質評分")
        sa, sb = st.columns([1, 1.15])
        with sa:
            st.metric("總分", f"{sc.overall:.0f} / 100", sc.verdict)
            for d in sc.dimensions:
                val = 0.0 if d.score is None else max(0.0, min(d.score, 100)) / 100
                label = f"{d.name}：{d.score:.0f}" if d.score is not None else f"{d.name}：N/A"
                st.progress(val, text=label)
        with sb:
            radar = interactive.radar_fig(p.ticker, sc)
            if radar is not None:
                st.plotly_chart(radar, use_container_width=True)
        with st.expander("評分明細（各指標數值與子分數，規則透明）"):
            for d in sc.dimensions:
                head = f"**{d.name}**（{d.score:.0f}）" if d.score is not None else f"**{d.name}**（N/A）"
                st.markdown(head)
                st.table([{"指標": lbl, "數值": val, "分數": ("—" if sub is None else sub)}
                          for lbl, val, sub in d.details])
        st.caption("評分為依公開數據以固定規則計算之客觀參考，非投資建議。")

    tw = p.market in ("TWSE", "TPEX")
    st.markdown("#### 關鍵指標")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("目前股價", _fmt_price(km.current_price, tw))
    c2.metric("總市值", _fmt_money(km.market_cap, tw))
    c3.metric("共識評等", km.consensus_rating or "—")
    c4.metric("平均目標價", _fmt_price(km.target_mean, tw),
              delta=f"{km.implied_upside_pct:+.1f}%" if km.implied_upside_pct is not None else None)

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("最新季營收", _fmt_money(km.latest_revenue, tw))
    c6.metric("營收 YoY", _fmt_pct(km.latest_revenue_yoy))
    c7.metric("毛利率", _fmt_pct(km.gross_margin))
    c8.metric("Forward P/E", f"{km.forward_pe:.1f}" if km.forward_pe else "—")

    # 台股專屬：月營收動能 + 三大法人籌碼
    if tw:
        mr, inst, mgn = report.monthly_revenue, report.institutional, report.margin
        if mr.latest_revenue is not None or mr.points:
            st.markdown("#### 🇹🇼 月營收動能")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric(f"當月營收（{mr.latest_period or '—'}）", _fmt_money(mr.latest_revenue, True))
            m2.metric("月營收 YoY", _fmt_pct(mr.latest_yoy))
            m3.metric("月營收 MoM", _fmt_pct(mr.latest_mom))
            m4.metric("累計營收 YoY", _fmt_pct(mr.cum_yoy))
            if mr.note:
                st.caption(f"官方備註：{mr.note}")
        if inst.days:
            st.markdown(f"#### 🇹🇼 三大法人買賣超（近 {inst.window_days} 交易日累計）")
            i1, i2, i3, i4 = st.columns(4)
            lot = lambda v: "—" if v is None else f"{v/1000:+,.0f} 張"
            i1.metric("外資", lot(inst.foreign_sum))
            i2.metric("投信", lot(inst.trust_sum))
            i3.metric("自營商", lot(inst.dealer_sum))
            i4.metric("融資餘額", f"{mgn.margin_balance:,.0f} 張" if mgn.margin_balance is not None else "—")
            if inst.sentiment_note:
                st.caption(inst.sentiment_note)

    st.markdown("#### 核心觀點 (Core View)")
    badge = "🤖 AI 分析" if report.ai.ai_generated else "📊 數據模板"
    st.caption(f"來源：{badge}　·　{report.ai.provider}")
    if report.ai.notice:
        st.warning(report.ai.notice)
    st.write(report.ai.core_view)

    st.markdown("#### 互動圖表")
    st.caption("可框選縮放、拖曳平移、滑鼠懸停看數值；右上角工具列可還原或下載圖片。")
    t = p.ticker
    for fig in (interactive.price_fig(t, report.price),
                interactive.revenue_yoy_fig(t, report.financials),
                interactive.margins_fig(t, report.financials),
                interactive.eps_fig(t, report.financials)):
        if fig is not None:
            st.plotly_chart(fig, use_container_width=True)

    with st.expander("更多互動圖表：本益比趨勢、同業比較"):
        for fig in (interactive.pe_fig(t, report.valuation),
                    interactive.peers_fig(t, report.peers)):
            if fig is not None:
                st.plotly_chart(fig, use_container_width=True)

    with st.spinner("產生 PDF 報告…"):
        fname = f"{t}_{p.company_name.replace(' ', '_')}_投資分析報告.pdf"
        out_path = OUTPUT_DIR / fname
        try:
            pdf_builder.build_pdf(report, out_path, cleanup=True)
            pdf_bytes = out_path.read_bytes()
        except Exception as exc:  # noqa: BLE001
            st.error(f"產生 PDF 失敗：{exc}")
            return

    st.success("PDF 報告已產生！")
    st.download_button("⬇️ 下載 PDF 報告", data=pdf_bytes, file_name=fname,
                       mime="application/pdf", type="primary")

    st.markdown("#### 完整報告預覽")
    _embed_pdf(pdf_bytes)


# ---------------------------------------------------------------------------
# 版面
# ---------------------------------------------------------------------------
st.markdown(
    """
<style>
/* 全域背景與留白 */
.stApp { background: #F4F7FB; }
.block-container { padding-top: 1.1rem; max-width: 1150px; }

/* 財經風橫幅 */
.hero {
  background: linear-gradient(120deg, #14273F 0%, #1F3A5F 55%, #2C5A8C 100%);
  border-radius: 14px; padding: 26px 30px; margin: 2px 0 20px 0; color: #fff;
  box-shadow: 0 6px 22px rgba(20,39,63,.22); position: relative; overflow: hidden;
}
.hero::after {
  content: ""; position: absolute; right: -50px; top: -50px; width: 240px; height: 240px;
  background: radial-gradient(circle, rgba(217,119,6,.35), transparent 70%);
}
.hero .eyebrow { font-size: .78rem; letter-spacing: 3px; color: #9FC0E0; text-transform: uppercase; }
.hero .title { font-size: 1.85rem; font-weight: 800; margin: 6px 0 2px; }
.hero .sub { font-size: .95rem; color: #CFE0F0; }
.hero .chips { margin-top: 14px; }
.hero .chip { display: inline-block; background: rgba(255,255,255,.12);
  border: 1px solid rgba(255,255,255,.28); border-radius: 20px; padding: 3px 12px;
  font-size: .78rem; margin: 0 8px 6px 0; }

/* 指標卡片 */
[data-testid="stMetric"] {
  background: #fff; border: 1px solid #E2E8F0; border-radius: 12px;
  padding: 14px 16px; box-shadow: 0 1px 3px rgba(16,42,67,.06);
}
[data-testid="stMetricLabel"] p { color: #64748B; font-size: .8rem; font-weight: 600; }
[data-testid="stMetricValue"] { color: #1F3A5F; font-weight: 800; }

/* 區塊標題（#### ...） */
.stApp h4 { color: #1F3A5F; border-left: 4px solid #D97706; padding-left: 10px; margin-top: 1.3rem; }

/* 按鈕 */
.stButton > button[kind="primary"], .stDownloadButton > button {
  background: #1F3A5F; border: 0; border-radius: 8px; font-weight: 700;
}
.stButton > button[kind="primary"]:hover, .stDownloadButton > button:hover { background: #2C5A8C; }

/* 側邊欄：淡藍面板 */
section[data-testid="stSidebar"] { background: #EDF2F8; border-right: 1px solid #DCE4EE; }
</style>
""",
    unsafe_allow_html=True,
)

st.markdown(
    """
<div class="hero">
  <div class="eyebrow">US / TW Equity Research · 美股・台股投資分析</div>
  <div class="title">📈 美股／台股投資分析報告產生器</div>
  <div class="sub">官方源 + yfinance 資料引擎 · Pandas 深度分析 · AI 質化解讀 · 投行級 PDF 報告</div>
  <div class="chips">
    <span class="chip">📊 估值與籌碼</span>
    <span class="chip">🏦 目標價/共識</span>
    <span class="chip">🇹🇼 月營收・三大法人</span>
    <span class="chip">🧭 護城河分析</span>
    <span class="chip">📈 技術面 K 線</span>
  </div>
</div>
""",
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("設定")

    with st.expander("🔑 使用自己的 API Key（選用）", expanded=False):
        st.caption("啟用 AI 撰寫的深度質化分析。金鑰**僅用於本次連線、不會被儲存或記錄**。"
                   "留空則使用伺服器預設金鑰（若有）或純數據模板。")
        prov = st.radio("AI 供應商",
                        ["不使用（純數據模板）", "Anthropic (Claude)", "OpenAI (GPT)"],
                        index=0)
        ak = ok = ""
        if prov.startswith("Anthropic"):
            ak = st.text_input("Anthropic API Key", type="password", placeholder="sk-ant-...")
        elif prov.startswith("OpenAI"):
            ok = st.text_input("OpenAI API Key", type="password", placeholder="sk-...")
        llm_client.set_runtime_keys(anthropic_key=ak, openai_key=ok)

    st.write(f"**目前質化分析來源：** {provider_label()}")

    if st.button("🔄 清除報告快取"):
        cached_report.clear()
        cached_candidates.clear()
        st.success("已清除快取，下次查詢將重新擷取。")
    st.divider()
    st.caption("所有投資相關內容僅供參考，不構成任何投資建議，使用者應自行評估風險。")

# 網址參數自動帶入（例如 ?ticker=ORCL）
qp_ticker = st.query_params.get("ticker", "")

default_val = st.session_state.get("selected_ticker", qp_ticker)
ticker_input = st.text_input("股票代號或公司名稱（美股 / 台股）", value=default_val,
                             placeholder="美股：AAPL、NVDA　｜　台股：2330、6488、台積電")

col_v, col_g, _ = st.columns([1, 1, 4])
validate = col_v.button("🔍 驗證代號")
go = col_g.button("產生報告", type="primary")

# 驗證 / 建議
if validate and ticker_input.strip():
    with st.spinner("查詢相符代號…"):
        cands = cached_candidates(ticker_input.strip())
    if not cands:
        st.warning("查無相符的代號，請改用正確的股票代號重試（美股如 ORCL、台股如 2330）。")
    else:
        st.markdown("**符合的候選代號**（點選即帶入輸入框）：")
        cols = st.columns(min(3, len(cands)))
        for i, c in enumerate(cands):
            label = f"{c['symbol']}｜{(c['name'] or '')[:18]}"
            if cols[i % len(cols)].button(label, key=f"cand_{c['symbol']}"):
                st.session_state["selected_ticker"] = c["symbol"]
                st.rerun()

# 自動執行（網址參數帶入且本輪尚未跑過）
auto = bool(qp_ticker) and st.session_state.get("auto_done") != qp_ticker

if (go or auto) and ticker_input.strip():
    st.session_state["auto_done"] = qp_ticker if auto else ticker_input.strip()
    _run_report(ticker_input.strip())
elif go:
    st.warning("請先輸入股票代號或公司名稱。")
