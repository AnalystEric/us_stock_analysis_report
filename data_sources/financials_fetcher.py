"""季度財務（近 8 季）：營收、YoY、毛利率、自由現金流 (FCF)、FCF 利潤率、EPS Beat/Miss。

資料源（yfinance）：
  * quarterly_income_stmt → Total Revenue, Gross Profit
  * quarterly_cashflow    → Free Cash Flow（或 Operating Cash Flow − CapEx）
  * get_earnings_dates    → EPS 實際 / 預期 / 驚奇
以季度結束日期對齊三份報表；EPS 以「季末後 ~80 天內的公布日」對應。
"""
from __future__ import annotations

import logging

import pandas as pd

from analytics.metrics import revenue_cagr_from_quarters, safe_div
from config import QUARTERS_LOOKBACK
from core.models import FinancialsData, QuarterPoint
from data_sources.yf_client import get_ticker, safe_call

logger = logging.getLogger(__name__)

_REVENUE_ROWS = ["Total Revenue", "TotalRevenue", "OperatingRevenue"]
_GROSS_ROWS = ["Gross Profit", "GrossProfit"]
_FCF_ROWS = ["Free Cash Flow", "FreeCashFlow"]
_OCF_ROWS = ["Operating Cash Flow", "OperatingCashFlow",
             "Cash Flow From Continuing Operating Activities"]
_CAPEX_ROWS = ["Capital Expenditure", "CapitalExpenditure", "Capital Expenditures"]


def _row(df: pd.DataFrame, names: list[str]) -> pd.Series | None:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return None
    for n in names:
        if n in df.index:
            return df.loc[n]
    return None


def _period_label(ts) -> str:
    try:
        q = (ts.month - 1) // 3 + 1
        return f"{ts.year}Q{q}"
    except Exception:  # noqa: BLE001
        return str(ts)


def _to_float(v) -> float | None:
    try:
        f = float(v)
        return None if pd.isna(f) else f
    except (TypeError, ValueError):
        return None


def _income(tk) -> pd.DataFrame:
    def _f():
        df = tk.quarterly_income_stmt
        if df is None or df.empty:
            df = tk.quarterly_financials
        return df if df is not None else pd.DataFrame()
    df = safe_call(_f, default=pd.DataFrame(), label="quarterly_income_stmt")
    return df if isinstance(df, pd.DataFrame) else pd.DataFrame()


def _cashflow(tk) -> pd.DataFrame:
    def _f():
        df = tk.quarterly_cashflow
        return df if df is not None else pd.DataFrame()
    df = safe_call(_f, default=pd.DataFrame(), label="quarterly_cashflow")
    return df if isinstance(df, pd.DataFrame) else pd.DataFrame()


def _earnings(tk) -> pd.DataFrame:
    def _f():
        try:
            df = tk.get_earnings_dates(limit=24)
        except Exception:  # noqa: BLE001
            df = tk.earnings_dates
        return df if df is not None else pd.DataFrame()
    df = safe_call(_f, default=pd.DataFrame(), label="earnings_dates")
    return df if isinstance(df, pd.DataFrame) else pd.DataFrame()


def _match_eps(earnings: pd.DataFrame, quarter_end) -> tuple:
    """回傳該季 (actual, estimate, surprise%)；找季末後 0~80 天內的公布日。"""
    if not isinstance(earnings, pd.DataFrame) or earnings.empty:
        return None, None, None

    def col(cands):
        for c in earnings.columns:
            for cand in cands:
                if cand.lower() in str(c).lower():
                    return c
        return None

    act_c = col(["Reported EPS", "Reported"])
    est_c = col(["EPS Estimate", "Estimate"])
    sur_c = col(["Surprise"])
    if act_c is None:
        return None, None, None

    try:
        qend = pd.Timestamp(quarter_end)
        if qend.tzinfo is None and getattr(earnings.index, "tz", None) is not None:
            qend = qend.tz_localize(earnings.index.tz)
    except Exception:  # noqa: BLE001
        return None, None, None

    best = None
    for idx, r in earnings.iterrows():
        try:
            delta_days = (idx - qend).days
        except Exception:  # noqa: BLE001
            continue
        if 0 <= delta_days <= 80 and _to_float(r.get(act_c)) is not None:
            if best is None or delta_days < best[0]:
                best = (delta_days, r)
    if best is None:
        return None, None, None

    r = best[1]
    actual = _to_float(r.get(act_c))
    estimate = _to_float(r.get(est_c)) if est_c else None
    surprise = _to_float(r.get(sur_c)) if sur_c else None
    if surprise is None and actual is not None and estimate not in (None, 0):
        surprise = (actual - estimate) / abs(estimate) * 100
    return actual, estimate, surprise


def fetch_financials(ticker: str) -> FinancialsData:
    tk = get_ticker(ticker)
    data = FinancialsData()

    inc = _income(tk)
    rev = _row(inc, _REVENUE_ROWS)
    gross = _row(inc, _GROSS_ROWS)
    if rev is None:
        data.warning = "無法取得季度營收資料。"
        return data

    cf = _cashflow(tk)
    fcf_row = _row(cf, _FCF_ROWS)
    ocf_row = _row(cf, _OCF_ROWS)
    capex_row = _row(cf, _CAPEX_ROWS)
    earnings = _earnings(tk)

    # 以季末日期排序（舊→新）
    rev = rev.dropna()
    try:
        rev = rev.sort_index()
    except Exception:  # noqa: BLE001
        pass
    cols = list(rev.index)
    rev_vals = [_to_float(rev[c]) for c in cols]

    points: list[QuarterPoint] = []
    for i, c in enumerate(cols):
        p = QuarterPoint(period=_period_label(c), revenue=rev_vals[i])

        # YoY（前 4 個季度）
        if i - 4 >= 0 and rev_vals[i - 4]:
            p.revenue_yoy = (rev_vals[i] - rev_vals[i - 4]) / abs(rev_vals[i - 4])

        # 毛利率
        if gross is not None and c in gross.index:
            gp = _to_float(gross[c])
            p.gross_margin = safe_div(gp, rev_vals[i])

        # FCF 與 FCF 利潤率
        fcf_val = None
        if fcf_row is not None and c in fcf_row.index:
            fcf_val = _to_float(fcf_row[c])
        if fcf_val is None and ocf_row is not None and capex_row is not None and c in ocf_row.index:
            ocf = _to_float(ocf_row.get(c))
            capex = _to_float(capex_row.get(c))
            if ocf is not None and capex is not None:
                fcf_val = ocf + capex  # CapEx 在 yfinance 通常為負值
        p.fcf = fcf_val
        p.fcf_margin = safe_div(fcf_val, rev_vals[i])

        # EPS
        actual, estimate, surprise = _match_eps(earnings, c)
        p.eps_actual = actual
        p.eps_estimate = estimate
        p.eps_surprise_pct = surprise
        if actual is not None and estimate is not None:
            p.beat_miss = "Beat" if actual > estimate else ("Miss" if actual < estimate else "In-line")

        points.append(p)

    data.quarters = points[-QUARTERS_LOOKBACK:]
    data.revenue_cagr_3y = revenue_cagr_from_quarters(data)

    if not any(q.eps_actual is not None for q in data.quarters):
        logger.info("EPS 對齊未取得資料（僅營收 / 利潤率可用）")
    return data
