"""綜合體質評分：以透明的分段門檻，將客觀數據轉為五維 0-100 分。

五維：價值 (Value)、成長 (Growth)、獲利 (Profitability)、財務健康 (Financial Health)、動能 (Momentum)。
每個維度取「可得子指標」的平均；缺資料的子指標略過，全缺則該維度為 None。
總分為可得維度的平均。評分規則公開透明，純依數據計算，不含主觀判斷。
"""
from __future__ import annotations

import logging

from core.models import (
    DimensionScore,
    Fundamentals,
    FinancialsData,
    KeyMetrics,
    PriceData,
    RatingData,
    ScoreCard,
    ValuationMultiples,
)

logger = logging.getLogger(__name__)


def _interp(v, pts):
    """線性內插評分。pts 為 [(x, score), ...] 依 x 遞增；兩端夾住。"""
    if v is None:
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    if v <= pts[0][0]:
        return float(pts[0][1])
    if v >= pts[-1][0]:
        return float(pts[-1][1])
    for (x0, s0), (x1, s1) in zip(pts, pts[1:]):
        if x0 <= v <= x1:
            t = (v - x0) / (x1 - x0) if x1 != x0 else 0.0
            return float(s0 + t * (s1 - s0))
    return float(pts[-1][1])


def _pct(v, d=1):
    return "N/A" if v is None else f"{v * 100:.{d}f}%"


def _num(v, d=1):
    return "N/A" if v is None else f"{v:.{d}f}"


def _avg(subs):
    vals = [s for s in subs if s is not None]
    return (sum(vals) / len(vals)) if vals else None


def _dim(key, name, items):
    """items: list of (label, value_str, subscore)。回傳 DimensionScore。"""
    subs = [s for _, _, s in items if s is not None]
    score = (sum(subs) / len(subs)) if subs else None
    details = [(lbl, val, round(s) if s is not None else None) for lbl, val, s in items]
    return DimensionScore(key=key, name=name, score=score, details=details)


# --- 各維度 ---
def _value_dim(v: ValuationMultiples, rating: RatingData) -> DimensionScore:
    fpe = v.forward_pe if v.forward_pe is not None else v.trailing_pe
    pe_ratio = (v.pe_current / v.pe_mean_3y) if (v.pe_current and v.pe_mean_3y) else None
    items = [
        ("Forward/Trailing P/E", _num(fpe), _interp(fpe, [(8, 100), (15, 85), (20, 70), (25, 58), (30, 45), (40, 28), (60, 12), (100, 5)])),
        ("P/S", _num(v.ps_ratio, 2), _interp(v.ps_ratio, [(1, 100), (3, 80), (5, 65), (8, 48), (12, 32), (20, 15), (30, 8)])),
        ("EV/FCF", _num(v.ev_fcf), _interp(v.ev_fcf, [(10, 100), (20, 82), (30, 65), (45, 48), (60, 32), (100, 12)])),
        ("PEG", _num(v.peg, 2), _interp(v.peg, [(0.5, 100), (1, 85), (1.5, 68), (2, 52), (3, 32), (5, 12)])),
        ("P/E vs 近3年均值", _num(pe_ratio, 2), _interp(pe_ratio, [(0.6, 100), (0.8, 85), (1.0, 65), (1.2, 45), (1.5, 25), (2.0, 10)])),
        ("分析師隱含漲幅", _pct((rating.implied_upside_pct or 0) / 100) if rating.implied_upside_pct is not None else "N/A",
         _interp(rating.implied_upside_pct, [(-30, 10), (-10, 30), (0, 50), (15, 68), (30, 82), (50, 95), (80, 100)])),
    ]
    return _dim("value", "價值 Value", items)


def _growth_dim(km: KeyMetrics, fin: FinancialsData, f: Fundamentals, v: ValuationMultiples) -> DimensionScore:
    rev_g = f.revenue_growth if f.revenue_growth is not None else km.latest_revenue_yoy
    fwd_ratio = (v.forward_pe / v.trailing_pe) if (v.forward_pe and v.trailing_pe) else None
    g_bands = [(-0.1, 10), (0, 25), (0.05, 45), (0.1, 60), (0.2, 78), (0.3, 90), (0.5, 100)]
    items = [
        ("營收年增率", _pct(rev_g), _interp(rev_g, g_bands)),
        ("營收年化成長 (3Y)", _pct(fin.revenue_cagr_3y), _interp(fin.revenue_cagr_3y, g_bands)),
        ("盈餘成長", _pct(f.earnings_growth), _interp(f.earnings_growth, [(-0.2, 10), (0, 30), (0.1, 55), (0.2, 72), (0.4, 88), (0.7, 100)])),
        ("Forward/Trailing P/E 比", _num(fwd_ratio, 2), _interp(fwd_ratio, [(0.6, 100), (0.8, 80), (1.0, 55), (1.2, 35), (1.5, 15)])),
    ]
    return _dim("growth", "成長 Growth", items)


def _profit_dim(km: KeyMetrics, fin: FinancialsData, f: Fundamentals) -> DimensionScore:
    fcf_m = next((q.fcf_margin for q in reversed(fin.quarters) if q.fcf_margin is not None), None)
    items = [
        ("毛利率", _pct(f.gross_margin or km.gross_margin), _interp(f.gross_margin or km.gross_margin, [(0.1, 20), (0.2, 40), (0.35, 60), (0.5, 78), (0.65, 90), (0.8, 100)])),
        ("淨利率", _pct(f.profit_margin), _interp(f.profit_margin, [(0, 10), (0.05, 40), (0.1, 60), (0.2, 80), (0.3, 92), (0.4, 100)])),
        ("ROE", _pct(f.roe), _interp(f.roe, [(0, 10), (0.05, 35), (0.1, 55), (0.15, 72), (0.2, 85), (0.3, 100)])),
        ("自由現金流利潤率", _pct(fcf_m), _interp(fcf_m, [(-0.1, 15), (0, 35), (0.05, 55), (0.1, 70), (0.2, 88), (0.3, 100)])),
    ]
    return _dim("profitability", "獲利 Profitability", items)


def _health_dim(f: Fundamentals) -> DimensionScore:
    cash_to_debt = None
    if f.total_cash is not None and f.total_debt is not None:
        cash_to_debt = 10.0 if f.total_debt == 0 else f.total_cash / f.total_debt
    fcf_pos = None
    if f.free_cashflow is not None:
        fcf_pos = 88.0 if f.free_cashflow > 0 else 28.0
    items = [
        ("負債/權益 (D/E %)", _num(f.debt_to_equity), _interp(f.debt_to_equity, [(0, 100), (30, 90), (50, 82), (100, 65), (150, 50), (200, 38), (300, 20), (500, 8)])),
        ("流動比率", _num(f.current_ratio, 2), _interp(f.current_ratio, [(0.5, 15), (1.0, 45), (1.5, 72), (2.0, 88), (3.0, 100)])),
        ("現金/負債", _num(cash_to_debt, 2), _interp(cash_to_debt, [(0.2, 20), (0.5, 45), (1.0, 70), (2.0, 88), (5.0, 100)])),
        ("自由現金流為正", "是" if fcf_pos and fcf_pos > 50 else ("否" if fcf_pos else "N/A"), fcf_pos),
    ]
    return _dim("health", "財務健康 Financial Health", items)


def _momentum_dim(price: PriceData) -> DimensionScore:
    cur = price.current_price
    p_ma50 = (cur / price.ma50) if (cur and price.ma50) else None
    p_ma200 = (cur / price.ma200) if (cur and price.ma200) else None
    golden = (price.ma50 / price.ma200) if (price.ma50 and price.ma200) else None

    pos52 = None
    if cur and price.week52_high and price.week52_low and price.week52_high > price.week52_low:
        pos52 = (cur - price.week52_low) / (price.week52_high - price.week52_low)

    ret3m = None
    df = price.price_df
    try:
        if df is not None and not getattr(df, "empty", True) and "Close" in df.columns and len(df) > 63:
            ret3m = float(df["Close"].iloc[-1] / df["Close"].iloc[-63] - 1)
    except Exception:  # noqa: BLE001
        ret3m = None

    ma_bands = [(0.85, 20), (0.95, 45), (1.0, 60), (1.05, 75), (1.15, 90), (1.3, 100)]
    items = [
        ("股價 / 50 日均線", _num(p_ma50, 2), _interp(p_ma50, ma_bands)),
        ("股價 / 200 日均線", _num(p_ma200, 2), _interp(p_ma200, ma_bands)),
        ("50 / 200 日均線 (黃金交叉)", _num(golden, 2), _interp(golden, [(0.9, 25), (0.98, 48), (1.0, 62), (1.05, 80), (1.15, 95)])),
        ("52 週區間位置", _pct(pos52), _interp(pos52, [(0, 15), (0.25, 40), (0.5, 60), (0.75, 80), (1.0, 95)])),
        ("近 3 個月報酬", _pct(ret3m), _interp(ret3m, [(-0.2, 15), (-0.05, 40), (0, 55), (0.05, 70), (0.15, 88), (0.3, 100)])),
    ]
    return _dim("momentum", "動能 Momentum", items)


def _verdict(overall: float) -> str:
    if overall >= 80:
        return "體質優異"
    if overall >= 65:
        return "穩健"
    if overall >= 50:
        return "中性"
    if overall >= 35:
        return "偏弱"
    return "疲弱"


def build_scorecard(
    key_metrics: KeyMetrics,
    price: PriceData,
    financials: FinancialsData,
    valuation: ValuationMultiples,
    rating: RatingData,
    fundamentals: Fundamentals,
) -> ScoreCard:
    dims = [
        _value_dim(valuation, rating),
        _growth_dim(key_metrics, financials, fundamentals, valuation),
        _profit_dim(key_metrics, financials, fundamentals),
        _health_dim(fundamentals),
        _momentum_dim(price),
    ]
    overall = _avg([d.score for d in dims])
    card = ScoreCard(dimensions=dims, overall=overall)
    if overall is None:
        card.warning = "資料不足，無法計算綜合評分。"
    else:
        card.verdict = _verdict(overall)
    return card
