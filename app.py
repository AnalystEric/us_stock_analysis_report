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
from viz import charts

setup_logging(False)
logger = logging.getLogger(__name__)

st.set_page_config(page_title="美股投資分析報告產生器", page_icon="📈", layout="wide")


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
def _fmt_money(v):
    if v is None:
        return "—"
    for unit, size in (("兆", 1e12), ("十億", 1e9), ("百萬", 1e6)):
        if abs(v) >= size:
            return f"${v/size:,.2f}{unit}"
    return f"${v:,.0f}"


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
    st.caption(f"{p.exchange_name or '美股'} · {p.sector or 'N/A'} / {p.industry or 'N/A'}")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("目前股價", f"${km.current_price:,.2f}" if km.current_price else "—")
    c2.metric("總市值", _fmt_money(km.market_cap))
    c3.metric("共識評等", km.consensus_rating or "—")
    c4.metric("平均目標價", f"${km.target_mean:,.2f}" if km.target_mean else "—",
              delta=f"{km.implied_upside_pct:+.1f}%" if km.implied_upside_pct is not None else None)

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("最新季營收", _fmt_money(km.latest_revenue))
    c6.metric("營收 YoY", _fmt_pct(km.latest_revenue_yoy))
    c7.metric("毛利率", _fmt_pct(km.gross_margin))
    c8.metric("Forward P/E", f"{km.forward_pe:.1f}" if km.forward_pe else "—")

    st.markdown("#### 核心觀點 (Core View)")
    badge = "🤖 AI 分析" if report.ai.ai_generated else "📊 數據模板"
    st.caption(f"來源：{badge}　·　{report.ai.provider}")
    if report.ai.notice:
        st.warning(report.ai.notice)
    st.write(report.ai.core_view)

    st.markdown("#### 圖表預覽")
    t = p.ticker
    prev1 = charts.price_candle_chart(t, report.price)
    prev2 = charts.revenue_yoy_chart(t, report.financials)
    pc1, pc2 = st.columns(2)
    if prev1:
        pc1.image(prev1, caption="股價 K 線 + 均線 + 成交量")
    if prev2:
        pc2.image(prev2, caption="季度營收與 YoY")

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
st.title("📈 美股投資分析 PDF 報告產生器")
st.caption("以 yfinance 為核心資料源，整合 Pandas 分析、專業圖表、AI 質化分析與 WeasyPrint 排版。")

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
ticker_input = st.text_input("美股代號或公司名稱", value=default_val,
                             placeholder="例如 AAPL、NVDA、Apple、Tesla")

col_v, col_g, _ = st.columns([1, 1, 4])
validate = col_v.button("🔍 驗證代號")
go = col_g.button("產生報告", type="primary")

# 驗證 / 建議
if validate and ticker_input.strip():
    with st.spinner("查詢相符代號…"):
        cands = cached_candidates(ticker_input.strip())
    if not cands:
        st.warning("查無相符的美股代號，請改用正確的股票代號（例如 ORCL）重試。")
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
