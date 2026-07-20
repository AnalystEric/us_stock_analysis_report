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
    for unit, size in (("T", 1e12), ("B", 1e9), ("M", 1e6)):
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


# --- 各區塊指令（要求 LLM 以繁體中文詳細撰寫）---
SECTION_INSTRUCTIONS = {
    "core_view": (
        "以繁體中文撰寫 250-400 字的『核心觀點 (Core View)』執行摘要，"
        "涵蓋：公司定位與規模、近期營收/獲利動能、估值位階、華爾街觀點與主要風險，語氣客觀平衡。"
    ),
    "business_overview": (
        "以繁體中文詳細撰寫 450-650 字的『公司業務概述與商業模式』。"
        "請將提供的英文公司簡介翻譯並整理為通順的繁體中文，說明：(1) 公司主要產品與服務、"
        "(2) 主要營收來源與商業模式（如何賺錢）、(3) 目標市場與客群、(4) 結合近期營收規模、"
        "成長率與利潤率數據描述其營運概況。分段書寫、內容務求完整詳盡。"
    ),
    "moat": (
        "以繁體中文詳細撰寫 450-650 字的『護城河分析 (Economic Moat)』。"
        "分段評估其競爭優勢來源（規模經濟、品牌、網路效應、轉換成本、技術/專利、生態系等），"
        "並以毛利率/淨利率相對同業、營收成長、市值規模等數據佐證，最後判斷護城河的寬窄與可持續性。"
    ),
    "risks": (
        "以繁體中文撰寫 300-450 字的『主要風險 (Key Risks)』，分點說明競爭加劇、成長放緩、"
        "利潤率壓縮、估值修正、法規與總經等面向，並盡量對應到具體數據。"
    ),
    "conclusion": (
        "以繁體中文撰寫 250-400 字的『結論 (Conclusion)』，綜合基本面、估值與華爾街觀點給出"
        "平衡總結，並點出後續值得追蹤的關鍵指標（避免直接的買賣建議）。"
    ),
}


def build_section_prompt(section: str, facts: str) -> str:
    instruction = SECTION_INSTRUCTIONS[section]
    return f"{instruction}\n\n=== 事實資料 ===\n{facts}"


# ---------------------------------------------------------------------------
# 無 LLM 時的純數據模板（繁體中文、盡量詳盡；預設即有內容）
# ---------------------------------------------------------------------------
def _peer_margin_avg(peers, field: str):
    vals = [getattr(r, field) for r in peers.rows if not r.is_self and getattr(r, field) is not None]
    return (sum(vals) / len(vals)) if vals else None


def _revenue_trend_note(financials) -> str:
    qs = [q for q in financials.quarters if q.revenue is not None]
    if len(qs) < 2:
        return ""
    first, last = qs[0], qs[-1]
    direction = "成長" if last.revenue >= first.revenue else "下滑"
    note = (f"近 {len(qs)} 季營收自 {first.period} 的 {_money(first.revenue)} "
            f"{direction}至 {last.period} 的 {_money(last.revenue)}")
    if financials.revenue_cagr_3y is not None:
        note += f"，年化成長率約 {_pct(financials.revenue_cagr_3y)}"
    return note + "。"


def template_core_view(profile, km, financials, valuation, rating, peers) -> str:
    p1 = (f"{profile.company_name}（{profile.ticker}）為 {profile.sector or '該'} 類股、"
          f"{profile.industry or 'N/A'} 產業之公司，目前市值約 {_money(profile.market_cap)}"
          f"{('，屬產業中的大型企業' if (profile.market_cap or 0) >= 1e11 else '')}。"
          f"目前股價 {_num(km.current_price)}，位於 52 週區間 {_num(km.week52_low)}～{_num(km.week52_high)} 之間。")

    p2_bits = []
    if km.latest_revenue is not None:
        p2_bits.append(f"最新季度（{km.latest_quarter}）營收 {_money(km.latest_revenue)}、"
                       f"年增率 {_pct(km.latest_revenue_yoy)}，毛利率 {_pct(km.gross_margin)}")
    trend = _revenue_trend_note(financials)
    if trend:
        p2_bits.append(trend.rstrip("。"))
    p2 = ("營運動能方面，" + "；".join(p2_bits) + "。") if p2_bits else ""

    p3_bits = []
    if valuation.trailing_pe is not None or valuation.forward_pe is not None:
        p3_bits.append(f"Trailing P/E {_num(valuation.trailing_pe)}、Forward P/E {_num(valuation.forward_pe)}")
    if valuation.ps_ratio is not None:
        p3_bits.append(f"P/S {_num(valuation.ps_ratio)}")
    p3 = ("估值方面，" + "、".join(p3_bits) + "。" + (valuation.pe_context_note or "")) if p3_bits else ""

    p4 = ""
    if rating.consensus or rating.target_mean is not None:
        p4 = (f"華爾街目前共識評等為 {rating.consensus or 'N/A'}"
              f"（{rating.num_analysts or 'N/A'} 位分析師），平均目標價 {_num(rating.target_mean)}，"
              f"相對現價隱含 {_pct_raw(rating.implied_upside_pct)} 空間。")

    return "\n\n".join(x for x in [p1, p2, p3, p4] if x)


def template_business_overview(profile, km, financials, valuation) -> str:
    paras = []

    intro = (f"{profile.company_name}（{profile.ticker}）為一家"
             f"{('總部位於 ' + profile.country + ' 的') if profile.country else ''}"
             f"{profile.sector or ''} 類股公司，專注於 {profile.industry or '相關'} 領域。"
             f"公司目前總市值約 {_money(profile.market_cap)}"
             f"{('，全職員工約 ' + format(profile.employees, ',') + ' 人') if profile.employees else ''}。")
    paras.append(intro)

    ops = []
    if km.latest_revenue is not None:
        ops.append(f"以最新季度（{km.latest_quarter}）計，公司營收達 {_money(km.latest_revenue)}，"
                   f"年增率 {_pct(km.latest_revenue_yoy)}")
    trend = _revenue_trend_note(financials)
    if trend:
        ops.append(trend.rstrip("。"))
    if ops:
        paras.append("在營運規模上，" + "；".join(ops) + "。")

    prof = []
    if km.gross_margin is not None:
        prof.append(f"毛利率約 {_pct(km.gross_margin)}")
    if km.net_margin is not None:
        prof.append(f"淨利率約 {_pct(km.net_margin)}")
    q_fcf = next((q.fcf_margin for q in reversed(financials.quarters) if q.fcf_margin is not None), None)
    if q_fcf is not None:
        prof.append(f"自由現金流利潤率約 {_pct(q_fcf)}")
    if prof:
        paras.append("獲利能力方面，" + "、".join(prof) +
                     "，反映其在產業中的成本結構與現金創造能力。")

    if valuation.trailing_pe is not None or valuation.ps_ratio is not None:
        paras.append(f"市場評價方面，目前 Trailing P/E {_num(valuation.trailing_pe)}、"
                     f"Forward P/E {_num(valuation.forward_pe)}、P/S {_num(valuation.ps_ratio)}，"
                     f"{valuation.pe_context_note or '可作為與同業比較估值高低的參考。'}")

    # 保留官方英文業務簡述作為原文參考（yfinance 僅提供英文；未啟用 AI 時無法翻譯）
    if profile.long_summary:
        paras.append("〔公司官方英文業務簡述（原文參考）〕\n" + profile.long_summary[:900])

    paras.append("（註：以上為依公開數據自動彙整之概述；如需 AI 將英文業務內容翻譯並"
                 "深入解讀為完整中文分析，可於側邊欄輸入 API Key 後重新產出。）")
    return "\n\n".join(paras)


def template_moat(profile, km, financials, valuation, peers) -> str:
    self_row = next((r for r in peers.rows if r.is_self), None)
    peer_rows = [r for r in peers.rows if not r.is_self]
    paras = []

    paras.append(f"就 {profile.industry or '所屬'} 產業而言，可持續的競爭優勢（護城河）通常來自"
                 "規模經濟、品牌與定價能力、網路效應、客戶轉換成本、技術與專利，以及生態系綁定等來源。"
                 "以下結合可得財務數據，對其護城河作初步定性評估。")

    # 定價能力：毛利率 vs 同業
    if self_row and self_row.gross_margin is not None:
        avg_gm = _peer_margin_avg(peers, "gross_margin")
        if avg_gm is not None:
            cmp = "高於" if self_row.gross_margin > avg_gm else "低於"
            judge = ("顯示其具備較強的定價能力或成本優勢，是護城河的正面訊號"
                     if cmp == "高於" else "顯示其在定價或成本上面臨較大競爭壓力")
            paras.append(f"在定價能力上，公司毛利率約 {_pct(self_row.gross_margin)}，"
                         f"{cmp}可比同業平均的 {_pct(avg_gm)}，{judge}。")
        else:
            paras.append(f"公司毛利率約 {_pct(self_row.gross_margin)}，"
                         "毛利率水準可作為其定價能力與產品競爭力的觀察指標。")

    # 獲利品質：淨利率 vs 同業
    if self_row and self_row.profit_margin is not None:
        avg_pm = _peer_margin_avg(peers, "profit_margin")
        extra = ""
        if avg_pm is not None:
            cmp = "優於" if self_row.profit_margin > avg_pm else "低於"
            extra = f"，{cmp}同業平均的 {_pct(avg_pm)}"
        paras.append(f"在獲利品質上，公司淨利率約 {_pct(self_row.profit_margin)}{extra}，"
                     "較高且穩定的淨利率通常代表營運效率與議價地位較佳，有助於支撐長期護城河。")

    # 規模與成長
    scale_bits = []
    if profile.market_cap:
        if peer_rows:
            caps = [r.market_cap for r in peer_rows if r.market_cap]
            if caps and profile.market_cap >= max(caps):
                scale_bits.append("其市值為所列同業中最大，規模本身即構成一定的進入障礙")
            else:
                scale_bits.append(f"市值約 {_money(profile.market_cap)}，具備一定規模")
        else:
            scale_bits.append(f"市值約 {_money(profile.market_cap)}")
    if financials.revenue_cagr_3y is not None:
        scale_bits.append(f"營收年化成長約 {_pct(financials.revenue_cagr_3y)}，成長性為護城河的動態面向")
    if scale_bits:
        paras.append("在規模與成長上，" + "；".join(scale_bits) + "。")

    # 市場評價隱含的信心
    if valuation.pe_current and valuation.pe_mean_3y:
        if valuation.pe_current > valuation.pe_mean_3y:
            paras.append("市場評價方面，目前本益比高於自身近 3 年均值，某種程度反映市場對其"
                         "競爭地位與成長前景給予溢價，但也代表估值已計入較高期待，需留意落差風險。")
        else:
            paras.append("市場評價方面，目前本益比低於自身近 3 年均值，市場對其前景的定價相對保守，"
                         "若基本面優勢延續，估值有修復空間。")

    paras.append("（註：以上為依公開財務數據所作之定性評估；護城河的深入判斷（如技術壁壘、"
                 "客戶集中度、生態系黏著度等）建議搭配 AI 分析或產業研究進一步佐證。）")
    return "\n\n".join(paras)


def template_risks(profile, km, financials, valuation, rating) -> str:
    bullets = []
    bullets.append(f"競爭與市佔風險：{profile.industry or '所屬'} 產業競爭激烈，"
                   "新進者或既有對手的價格與技術競爭，可能壓縮公司市佔與利潤率。")
    if km.gross_margin is not None:
        bullets.append(f"利潤率風險：目前毛利率約 {_pct(km.gross_margin)}，"
                       "若成本上升或產品組合惡化，獲利能力恐受影響。")
    if km.latest_revenue_yoy is not None and km.latest_revenue_yoy < 0.05:
        bullets.append(f"成長放緩風險：最新季營收年增率僅 {_pct(km.latest_revenue_yoy)}，"
                       "成長動能若進一步放緩，將影響評價。")
    if valuation.pe_current and valuation.pe_mean_3y and valuation.pe_current > valuation.pe_mean_3y * 1.1:
        bullets.append(f"估值修正風險：目前本益比（約 {_num(valuation.pe_current)}）高於近 3 年均值"
                       f"（約 {_num(valuation.pe_mean_3y)}），一旦成長或獲利不如預期，股價回檔壓力較大。")
    if rating.implied_upside_pct is not None and rating.implied_upside_pct < 0:
        bullets.append(f"上檔有限：現價已高於分析師平均目標價 {_num(rating.target_mean)}，"
                       f"隱含空間為 {_pct_raw(rating.implied_upside_pct)}，短期上檔或受限。")
    bullets.append("總體與政策風險：利率、匯率、景氣循環與法規變動，均可能影響需求與市場評價。")

    head = "綜合公開數據，主要風險面向包含："
    body = "\n\n".join(f"• {b}" for b in bullets)
    return head + "\n\n" + body


def template_conclusion(profile, km, financials, rating) -> str:
    paras = []
    trend = "維持成長" if (km.latest_revenue_yoy or 0) > 0 else "面臨成長壓力"
    seg = f"綜合基本面與估值，{profile.company_name}（{profile.ticker}）目前營收{trend}"
    if km.latest_revenue_yoy is not None:
        seg += f"（最新季 YoY {_pct(km.latest_revenue_yoy)}）"
    if km.gross_margin is not None:
        seg += f"，毛利率約 {_pct(km.gross_margin)}"
    seg += "。"
    paras.append(seg)

    if rating.consensus or rating.target_mean is not None:
        paras.append(f"華爾街共識評等為 {rating.consensus or 'N/A'}，平均目標價 {_num(rating.target_mean)}，"
                     f"相對現價隱含 {_pct_raw(rating.implied_upside_pct)} 空間，可作為市場預期的參考。")

    paras.append("後續建議追蹤：季度營收與 YoY 動能、毛利率與自由現金流利潤率的變化、"
                 "估值相對歷史與同業的位階，以及分析師評等與目標價的調整方向。"
                 "投資人應結合自身風險承受度與投資期間審慎評估。")
    return "\n\n".join(paras)
