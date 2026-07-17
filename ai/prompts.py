"""將結構化數據與新聞整理成 LLM Prompt，並提供無 LLM 時的純數據模板。"""
from __future__ import annotations

from core.models import (
    CompanyProfile,
    FinancialsData,
    KeyMetrics,
    NewsBundle,
    PeerComparison,
    RatingData,
    ValuationMultiples,
)

SYSTEM_PROMPT = (
    "你是一位頂尖投資銀行的資深股票研究分析師，擅長撰寫機構級（sell-side）研究報告。"
    "請以繁體中文、專業但精煉的語氣撰寫，可適度中英夾雜（專有名詞保留英文）。"
    "嚴格根據提供的數據與新聞事實作答，不得杜撰任何未提供的數字或事件；"
    "若某項資訊不足，可作合理的定性判斷但需說明為推論。"
    "輸出為連貫的段落（可用少量條列），不要加標題、不要重述題目、不要加免責聲明。"
)


def _pct(v, digits=1):
    if v is None:
        return "N/A"
    return f"{v * 100:.{digits}f}%"


def _pct_raw(v, digits=1):
    if v is None:
        return "N/A"
    return f"{v:.{digits}f}%"


def _money(v):
    if v is None:
        return "N/A"
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "N/A"
    for unit, size in (("兆", 1e12), ("十億", 1e9), ("百萬", 1e6)):
        if abs(v) >= size:
            return f"${v / size:,.2f}{unit}"
    return f"${v:,.0f}"


def _num(v, digits=2):
    if v is None:
        return "N/A"
    try:
        return f"{float(v):,.{digits}f}"
    except (TypeError, ValueError):
        return "N/A"


def build_facts(
    profile: CompanyProfile,
    km: KeyMetrics,
    financials: FinancialsData,
    valuation: ValuationMultiples,
    rating: RatingData,
    peers: PeerComparison,
    news: NewsBundle,
) -> str:
    """把可用事實濃縮成一段供 LLM 參考的文字。"""
    lines: list[str] = []
    lines.append(f"公司：{profile.company_name}（{profile.ticker}），交易所 {profile.exchange_name or 'N/A'}")
    lines.append(f"產業：{profile.sector or 'N/A'} / {profile.industry or 'N/A'}；市值 {_money(profile.market_cap)}")
    if profile.long_summary:
        lines.append(f"公司簡介：{profile.long_summary[:600]}")

    lines.append(
        f"股價 {_num(km.current_price)}；52週高 {_num(km.week52_high)} / 低 {_num(km.week52_low)}；"
        f"Trailing P/E {_num(valuation.trailing_pe)}；Forward P/E {_num(valuation.forward_pe)}；"
        f"P/S {_num(valuation.ps_ratio)}；EV/Sales {_num(valuation.ev_sales)}；EV/FCF {_num(valuation.ev_fcf)}"
    )
    if valuation.pe_context_note:
        lines.append(f"估值位階：{valuation.pe_context_note}")

    # 季度財務
    if financials.quarters:
        lines.append("近期季度（由舊到新）：")
        for q in financials.quarters:
            lines.append(
                f"  {q.period}：營收 {_money(q.revenue)}，YoY {_pct(q.revenue_yoy)}，"
                f"毛利率 {_pct(q.gross_margin)}，FCF 利潤率 {_pct(q.fcf_margin)}，"
                f"EPS 實際 {_num(q.eps_actual)} vs 預期 {_num(q.eps_estimate)}"
                f"（{q.beat_miss or 'N/A'}）"
            )
        if financials.revenue_cagr_3y is not None:
            lines.append(f"營收年化成長 (估) {_pct(financials.revenue_cagr_3y)}")

    # 評等
    lines.append(
        f"華爾街共識評等 {rating.consensus or 'N/A'}（{rating.num_analysts or 'N/A'} 位分析師）；"
        f"平均目標價 {_num(rating.target_mean)}（高 {_num(rating.target_high)} / 低 {_num(rating.target_low)}）；"
        f"隱含空間 {_pct_raw(rating.implied_upside_pct)}"
    )

    # 同業
    peer_rows = [r for r in peers.rows if not r.is_self]
    if peer_rows:
        names = "、".join(f"{r.ticker}(毛利率{_pct(r.gross_margin)})" for r in peer_rows)
        lines.append(f"主要同業：{names}")

    # 新聞
    if news.items:
        lines.append("近期新聞標題：")
        for it in news.items[:8]:
            lines.append(f"  - {it.title}（{it.source}，{it.publish_date}）")

    return "\n".join(lines)


# --- 各區塊指令 ---
SECTION_INSTRUCTIONS = {
    "core_view": (
        "根據以下事實，撰寫一段 150-250 字的『核心觀點 (Core View)』執行摘要，"
        "點出投資亮點、成長動能、估值位階與主要風險，語氣客觀。"
    ),
    "business_overview": (
        "根據以下事實，撰寫 200-300 字，說明該公司的『業務模式 (Business Model)』"
        "與主要營收來源、獲利方式。"
    ),
    "moat": (
        "根據以下事實，撰寫 200-300 字的『護城河分析 (Economic Moat)』，"
        "評估其競爭優勢來源（品牌、網路效應、規模、轉換成本、技術等）與可持續性。"
    ),
    "risks": (
        "根據以下事實，撰寫 200-300 字的『主要風險 (Key Risks)』，"
        "涵蓋競爭加劇、估值修正、成長放緩、法規/總經等面向，並盡量對應到數據。"
    ),
    "conclusion": (
        "根據以下事實，撰寫 150-250 字的『結論 (Conclusion)』，"
        "綜合基本面、估值與華爾街觀點給出平衡的總結（避免直接的買賣建議）。"
    ),
}


def build_section_prompt(section: str, facts: str) -> str:
    instruction = SECTION_INSTRUCTIONS[section]
    return f"{instruction}\n\n=== 事實資料 ===\n{facts}"


# ---------------------------------------------------------------------------
# 無 LLM 時的純數據模板
# ---------------------------------------------------------------------------
def template_core_view(profile, km, valuation, rating) -> str:
    parts = [f"{profile.company_name}（{profile.ticker}）為 {profile.sector or '該'} 產業"
             f"（{profile.industry or 'N/A'}）公司，目前市值約 {_money(profile.market_cap)}。"]
    if km.current_price is not None:
        parts.append(f"目前股價 {_num(km.current_price)}。")
    if km.latest_revenue is not None:
        parts.append(f"最新季度（{km.latest_quarter}）營收 {_money(km.latest_revenue)}，"
                     f"年增率 {_pct(km.latest_revenue_yoy)}，毛利率 {_pct(km.gross_margin)}。")
    if valuation.trailing_pe is not None or valuation.forward_pe is not None:
        parts.append(f"估值方面，Trailing P/E {_num(valuation.trailing_pe)}、"
                     f"Forward P/E {_num(valuation.forward_pe)}。")
    if valuation.pe_context_note:
        parts.append(valuation.pe_context_note)
    if rating.consensus:
        parts.append(f"華爾街共識評等為 {rating.consensus}，平均目標價 {_num(rating.target_mean)}，"
                     f"隱含空間 {_pct_raw(rating.implied_upside_pct)}。")
    return "".join(parts)


def template_business_overview(profile) -> str:
    if profile.long_summary:
        return profile.long_summary[:800]
    return (f"{profile.company_name} 屬於 {profile.sector or 'N/A'} 類股、"
            f"{profile.industry or 'N/A'} 產業。（公開資料未提供詳細業務描述。）")


def template_moat(profile, peers) -> str:
    self_row = next((r for r in peers.rows if r.is_self), None)
    peer_rows = [r for r in peers.rows if not r.is_self]
    parts = [f"就 {profile.industry or '所屬'} 產業而言，護城河通常來自規模、品牌與技術壁壘。"]
    if self_row and self_row.gross_margin is not None and peer_rows:
        avg_gm = [r.gross_margin for r in peer_rows if r.gross_margin is not None]
        if avg_gm:
            mean_gm = sum(avg_gm) / len(avg_gm)
            cmp = "高於" if self_row.gross_margin > mean_gm else "低於"
            parts.append(f"該公司毛利率 {_pct(self_row.gross_margin)}，{cmp}同業平均 {_pct(mean_gm)}，"
                         f"{'反映一定的定價能力與競爭優勢' if cmp == '高於' else '顯示成本或競爭壓力'}。")
    return "".join(parts)


def template_risks(profile, valuation, rating) -> str:
    parts = ["主要風險面向包含："]
    bullets = ["產業競爭加劇可能壓縮市佔與利潤率；"]
    if valuation.pe_current and valuation.pe_mean_3y and valuation.pe_current > valuation.pe_mean_3y * 1.1:
        bullets.append("目前估值高於歷史均值，存在估值修正風險；")
    bullets.append("總體經濟與利率環境變動影響需求與評價；")
    if rating.implied_upside_pct is not None and rating.implied_upside_pct < 0:
        bullets.append("目前股價已高於分析師平均目標價，短期上檔空間有限。")
    return parts[0] + "".join(bullets)


def template_conclusion(profile, km, rating) -> str:
    parts = [f"綜合基本面與估值，{profile.company_name}（{profile.ticker}）"]
    if km.latest_revenue_yoy is not None:
        trend = "維持成長" if km.latest_revenue_yoy > 0 else "面臨成長壓力"
        parts.append(f"營收{trend}（最新季 YoY {_pct(km.latest_revenue_yoy)}）")
    if rating.consensus:
        parts.append(f"，華爾街共識為 {rating.consensus}，平均目標價 {_num(rating.target_mean)}"
                     f"（隱含 {_pct_raw(rating.implied_upside_pct)}）")
    parts.append("。投資人應結合自身風險承受度與投資期間審慎評估。")
    return "".join(parts)
