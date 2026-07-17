"""將 ReportData 渲染為 HTML → WeasyPrint 產出 PDF。

流程：產生圖表(temp_images) → 組裝 Jinja2 context → 渲染 HTML → WeasyPrint 輸出 →
清理 temp_images。圖表以 base64 data URI 內嵌，避免路徑問題。
"""
from __future__ import annotations

import base64
import html
import logging
import shutil
from pathlib import Path

import bootstrap_libs  # noqa: F401  # 必須在 import weasyprint 前設定原生庫路徑

from jinja2 import Environment, FileSystemLoader, select_autoescape

from config import BASE_DIR, DISCLAIMER_TEXT, TEMP_IMAGES_DIR
from core.models import ReportData
from viz import charts, fonts

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
_CSS_PATH = Path(__file__).resolve().parent / "styles.css"


# ---------------------------------------------------------------------------
# 格式化
# ---------------------------------------------------------------------------
def esc(t) -> str:
    return html.escape(str(t)) if t is not None else ""


def money(v) -> str:
    if v is None:
        return "—"
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "—"
    for unit, size in (("兆", 1e12), ("十億", 1e9), ("百萬", 1e6)):
        if abs(v) >= size:
            return f"${v / size:,.2f}{unit}"
    return f"${v:,.0f}"


def price(v) -> str:
    if v is None:
        return "—"
    try:
        return f"${float(v):,.2f}"
    except (TypeError, ValueError):
        return "—"


def num(v, digits=2) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):,.{digits}f}"
    except (TypeError, ValueError):
        return "—"


def pct(ratio, digits=1) -> str:
    """比例(0~1) → 百分比字串。"""
    if ratio is None:
        return "—"
    try:
        return f"{float(ratio) * 100:.{digits}f}%"
    except (TypeError, ValueError):
        return "—"


def colored_pct(value_pct, digits=1) -> str:
    """已是百分比數值 → 帶正負色的 HTML。"""
    if value_pct is None:
        return "—"
    try:
        v = float(value_pct)
    except (TypeError, ValueError):
        return "—"
    cls = "pos" if v > 0 else ("neg" if v < 0 else "")
    sign = "+" if v > 0 else ""
    return f'<span class="{cls}">{sign}{v:.{digits}f}%</span>'


def colored_pct_from_ratio(ratio, digits=1) -> str:
    if ratio is None:
        return "—"
    try:
        return colored_pct(float(ratio) * 100, digits)
    except (TypeError, ValueError):
        return "—"


def para_html(text: str) -> str:
    """把純文字（可能含換行）轉為跳脫後的 <p> 段落。"""
    if not text:
        return ""
    blocks = [b.strip() for b in text.replace("\r", "").split("\n") if b.strip()]
    return "".join(f"<p>{esc(b)}</p>" for b in blocks)


def data_uri(path: str) -> str:
    if not path or not Path(path).exists():
        return ""
    try:
        raw = Path(path).read_bytes()
        b64 = base64.b64encode(raw).decode("ascii")
        return f"data:image/png;base64,{b64}"
    except Exception as exc:  # noqa: BLE001
        logger.warning("內嵌圖片失敗 %s: %s", path, exc)
        return ""


# ---------------------------------------------------------------------------
# 圖表
# ---------------------------------------------------------------------------
def _generate_charts(r: ReportData) -> dict[str, str]:
    t = r.profile.ticker
    return {
        "chart_segments": data_uri(charts.revenue_segments_chart(t, r.segments)),
        "chart_revenue_yoy": data_uri(charts.revenue_yoy_chart(t, r.financials)),
        "chart_margins": data_uri(charts.margins_chart(t, r.financials)),
        "chart_eps": data_uri(charts.eps_chart(t, r.financials)),
        "chart_price": data_uri(charts.price_candle_chart(t, r.price)),
        "chart_pe": data_uri(charts.pe_trend_chart(t, r.valuation)),
        "chart_peers": data_uri(charts.peers_chart(t, r.peers)),
    }


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------
def _font_face_css() -> str:
    path = fonts.resolve_font_path()
    if not path:
        return ""
    uri = Path(path).resolve().as_uri()
    return f'@font-face {{ font-family: "CJK"; src: url("{uri}"); }}'


def _beat_miss_html(bm: str) -> str:
    if bm == "Beat":
        return '<span class="pos">Beat ▲</span>'
    if bm == "Miss":
        return '<span class="neg">Miss ▼</span>'
    return esc(bm) or "—"


def _build_context(r: ReportData) -> dict:
    p, km, val, rating = r.profile, r.key_metrics, r.valuation, r.rating

    kpi_rows = [
        ("目前股價", price(km.current_price), "總市值", money(km.market_cap)),
        ("最新季度", esc(km.latest_quarter) or "—", "季度營收", money(km.latest_revenue)),
        ("季度營收 YoY", colored_pct_from_ratio(km.latest_revenue_yoy),
         "毛利率 (GAAP)", pct(km.gross_margin)),
        ("Trailing P/E", num(km.trailing_pe), "Forward P/E", num(km.forward_pe)),
        ("華爾街共識評等", esc(km.consensus_rating) or "—",
         "平均目標價", price(km.target_mean)),
        ("隱含漲跌幅", colored_pct(km.implied_upside_pct),
         "52 週高 / 低", f"{price(km.week52_high)} / {price(km.week52_low)}"),
    ]

    valuation_rows = [
        ("Trailing P/E", num(val.trailing_pe), "Forward P/E", num(val.forward_pe)),
        ("P/S", num(val.ps_ratio), "EV/Sales", num(val.ev_sales)),
        ("EV/EBITDA", num(val.ev_ebitda), "EV/FCF", num(val.ev_fcf)),
        ("PEG", num(val.peg), "P/B", num(val.price_to_book)),
    ]

    quarter_rows = [{
        "period": esc(q.period),
        "revenue": money(q.revenue),
        "yoy": colored_pct_from_ratio(q.revenue_yoy),
        "gm": pct(q.gross_margin),
        "fcfm": pct(q.fcf_margin),
        "eps_a": num(q.eps_actual),
        "eps_e": num(q.eps_estimate),
        "bm": _beat_miss_html(q.beat_miss),
    } for q in r.financials.quarters]

    scenario_rows = [{
        "name": esc(s.name),
        "target": price(s.target),
        "implied": colored_pct(s.implied_pct),
        "rationale": esc(s.rationale),
    } for s in rating.scenarios]

    peer_rows = [{
        "ticker": esc(pr.ticker),
        "name": esc((pr.name or "")[:24]),
        "mcap": money(pr.market_cap),
        "growth": colored_pct_from_ratio(pr.revenue_growth),
        "gm": pct(pr.gross_margin),
        "pm": pct(pr.profit_margin),
        "evs": num(pr.ev_sales),
        "fpe": num(pr.forward_pe),
        "is_self": pr.is_self,
    } for pr in r.peers.rows]

    news_items = [{
        "title": esc(n.title),
        "url": esc(n.url),
        "meta": esc(" ｜ ".join(x for x in [n.publish_date, n.source] if x)),
        "snippet": esc((n.snippet or "")[:200]),
    } for n in r.news.items]

    sm = r.smart_money
    opt = r.options

    ctx = {
        "css": _CSS_PATH.read_text(encoding="utf-8").replace("__DISCLAIMER__", DISCLAIMER_TEXT),
        "font_face_css": _font_face_css(),
        # 封面 / 基本
        "company": esc(p.company_name),
        "ticker": esc(p.ticker),
        "exchange": esc(p.exchange_name),
        "sector": esc(p.sector),
        "industry": esc(p.industry),
        "generated_on": r.generated_on.isoformat(),
        "market_cap": money(p.market_cap),
        "current_price": price(km.current_price),
        "consensus": esc(rating.consensus),
        "ai_provider": esc(r.ai.provider),
        # AI 區塊
        "ai_generated": r.ai.ai_generated,
        "ai_notice": esc(r.ai.notice),
        "core_view_html": para_html(r.ai.core_view),
        "business_overview_html": para_html(r.ai.business_overview),
        "moat_html": para_html(r.ai.moat),
        "risks_html": para_html(r.ai.risks),
        "conclusion_html": para_html(r.ai.conclusion),
        # 表格
        "kpi_rows": kpi_rows,
        "valuation_rows": valuation_rows,
        "quarter_rows": quarter_rows,
        "scenario_rows": scenario_rows,
        "peer_rows": peer_rows if len(peer_rows) > 1 else [],
        "peers_basis": esc(r.peers.basis_note),
        # 估值 / 籌碼
        "pe_context": esc(val.pe_context_note),
        "opt_expiry": esc(opt.expiry) or "—",
        "put_call": num(opt.put_call_ratio) if opt.put_call_ratio is not None else "查無選擇權數據",
        "options_note": esc(opt.sentiment_note or opt.warning),
        "inst_pct": pct(sm.institutional_ownership_pct / 100) if sm.institutional_ownership_pct is not None else "—",
        "insider_pct": pct(sm.insider_ownership_pct / 100) if sm.insider_ownership_pct is not None else "—",
        "insider_summary": [esc(x) for x in sm.insider_summary],
        # 圖表說明
        "segments_basis": esc(r.segments.basis or "年度營收結構"),
        # 新聞
        "news_items": news_items,
        "news_sources": esc(", ".join(r.news.providers_used)) or "—",
    }
    ctx.update(_generate_charts(r))
    return ctx


# ---------------------------------------------------------------------------
# 對外主函式
# ---------------------------------------------------------------------------
def build_pdf(report: ReportData, output_path: Path, cleanup: bool = True) -> Path:
    from weasyprint import HTML  # 延遲 import（bootstrap_libs 已先設定路徑）

    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template("report.html.j2")
    ctx = _build_context(report)
    html_str = template.render(**ctx)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html_str, base_url=str(BASE_DIR)).write_pdf(str(output_path))
    logger.info("PDF 已寫出：%s", output_path)

    if cleanup and TEMP_IMAGES_DIR.exists():
        try:
            shutil.rmtree(TEMP_IMAGES_DIR)
            logger.info("已清理暫存圖檔：%s", TEMP_IMAGES_DIR)
        except OSError as exc:
            logger.warning("清理暫存圖檔失敗: %s", exc)

    return output_path
