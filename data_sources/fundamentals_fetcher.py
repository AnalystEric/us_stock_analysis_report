"""基本面指標擷取：從 yfinance .info 取出評分所需欄位（ROE、負債、流動比、成長、股利等）。"""
from __future__ import annotations

import logging

import pandas as pd

from core.models import Fundamentals
from data_sources.yf_client import get_ticker, safe_info

logger = logging.getLogger(__name__)


def _num(v) -> float | None:
    try:
        f = float(v)
        return None if pd.isna(f) else f
    except (TypeError, ValueError):
        return None


def fetch_fundamentals(ticker: str) -> Fundamentals:
    info = safe_info(get_ticker(ticker))
    f = Fundamentals()
    if not info:
        f.warning = "無法取得基本面資料。"
        return f

    f.roe = _num(info.get("returnOnEquity"))
    f.roa = _num(info.get("returnOnAssets"))
    f.profit_margin = _num(info.get("profitMargins"))
    f.gross_margin = _num(info.get("grossMargins"))
    f.operating_margin = _num(info.get("operatingMargins"))
    f.revenue_growth = _num(info.get("revenueGrowth"))
    f.earnings_growth = _num(info.get("earningsGrowth")) or _num(info.get("earningsQuarterlyGrowth"))
    f.debt_to_equity = _num(info.get("debtToEquity"))
    f.current_ratio = _num(info.get("currentRatio"))
    f.quick_ratio = _num(info.get("quickRatio"))
    f.total_cash = _num(info.get("totalCash"))
    f.total_debt = _num(info.get("totalDebt"))
    f.free_cashflow = _num(info.get("freeCashflow"))
    f.dividend_yield = _num(info.get("dividendYield"))
    f.payout_ratio = _num(info.get("payoutRatio"))
    return f
