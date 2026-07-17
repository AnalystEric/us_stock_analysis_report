"""以 Pandas 為主的衍生指標計算：YoY、CAGR、FCF 利潤率、情境目標價、關鍵數據彙整。

純函式、無 I/O，方便單元測試與重複使用。
"""
from __future__ import annotations

import logging

from core.models import (
    FinancialsData,
    KeyMetrics,
    PriceData,
    PriceScenario,
    RatingData,
    ValuationMultiples,
)

logger = logging.getLogger(__name__)


def safe_div(a, b) -> float | None:
    try:
        if a is None or b is None or b == 0:
            return None
        return a / b
    except (TypeError, ZeroDivisionError):
        return None


def cagr(begin: float | None, end: float | None, years: float) -> float | None:
    """複合年均成長率（比例）。begin/end 需為正值。"""
    if begin is None or end is None or begin <= 0 or end <= 0 or years <= 0:
        return None
    try:
        return (end / begin) ** (1.0 / years) - 1.0
    except (ValueError, ZeroDivisionError):
        return None


def yoy(current: float | None, year_ago: float | None) -> float | None:
    """年增率（比例）。"""
    if current is None or year_ago is None or year_ago == 0:
        return None
    return (current - year_ago) / abs(year_ago)


def revenue_cagr_from_quarters(financials: FinancialsData) -> float | None:
    """由季度營收（近 8 季）估算年化成長：以最舊與最新季度、跨越年數換算。"""
    quarters = [q for q in financials.quarters if q.revenue]
    if len(quarters) < 5:
        return None
    begin = quarters[0].revenue
    end = quarters[-1].revenue
    years = (len(quarters) - 1) / 4.0
    return cagr(begin, end, years)


def build_scenarios(rating: RatingData) -> list[PriceScenario]:
    """由分析師目標價高/均/低建立樂觀/基準/保守三情境。"""
    cur = rating.current_price
    scenarios: list[PriceScenario] = []

    def implied(target: float | None) -> float | None:
        if target is None or not cur:
            return None
        return (target - cur) / cur * 100

    mapping = [
        ("樂觀 (Bull)", rating.target_high, "分析師最高目標價；反映需求 / 利潤率優於預期。"),
        ("基準 (Base)", rating.target_mean, "分析師共識平均目標價。"),
        ("保守 (Bear)", rating.target_low, "分析師最低目標價；反映競爭加劇 / 成長放緩風險。"),
    ]
    for name, target, rationale in mapping:
        if target is not None:
            scenarios.append(
                PriceScenario(name=name, target=target, implied_pct=implied(target),
                              rationale=rationale)
            )
    return scenarios


def assemble_key_metrics(
    profile,
    price: PriceData,
    financials: FinancialsData,
    valuation: ValuationMultiples,
    rating: RatingData,
) -> KeyMetrics:
    """彙整首頁「關鍵數據一覽表」所需欄位。"""
    km = KeyMetrics()
    km.current_price = price.current_price
    km.market_cap = profile.market_cap
    km.week52_high = price.week52_high
    km.week52_low = price.week52_low
    km.trailing_pe = valuation.trailing_pe
    km.forward_pe = valuation.forward_pe

    if financials.quarters:
        last = financials.quarters[-1]
        km.latest_quarter = last.period
        km.latest_revenue = last.revenue
        km.latest_revenue_yoy = last.revenue_yoy
        km.gross_margin = last.gross_margin

    km.consensus_rating = rating.consensus
    km.target_mean = rating.target_mean
    km.implied_upside_pct = rating.implied_upside_pct
    return km
