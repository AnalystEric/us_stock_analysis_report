"""營收結構：yfinance 無穩定的部門別營收，退而以「近 4 個年度總營收」作為結構圖資料，
呈現營收規模與趨勢；若連年度營收都取不到則標記查無資料，該圖由排版層略過。
"""
from __future__ import annotations

import logging

import pandas as pd

from core.models import RevenueSegments
from data_sources.yf_client import get_ticker, safe_call

logger = logging.getLogger(__name__)

_REVENUE_ROWS = ["Total Revenue", "TotalRevenue", "OperatingRevenue"]


def _to_float(v) -> float | None:
    try:
        f = float(v)
        return None if pd.isna(f) else f
    except (TypeError, ValueError):
        return None


def fetch_segments(ticker: str) -> RevenueSegments:
    tk = get_ticker(ticker)
    seg = RevenueSegments()

    def _f():
        df = tk.income_stmt
        if df is None or df.empty:
            df = tk.financials
        return df if df is not None else pd.DataFrame()

    df = safe_call(_f, default=pd.DataFrame(), label="annual_income_stmt")
    if not isinstance(df, pd.DataFrame) or df.empty:
        seg.warning = "查無營收結構資料。"
        return seg

    row = None
    for n in _REVENUE_ROWS:
        if n in df.index:
            row = df.loc[n]
            break
    if row is None:
        seg.warning = "查無年度營收資料。"
        return seg

    row = row.dropna()
    try:
        row = row.sort_index()  # 舊→新
    except Exception:  # noqa: BLE001
        pass

    labels, values = [], []
    for col in row.index[-4:]:
        val = _to_float(row[col])
        if val is None or val <= 0:
            continue
        year = getattr(col, "year", None)
        labels.append(f"{year}" if year else str(col)[:4])
        values.append(val)

    if not values:
        seg.warning = "查無有效年度營收資料。"
        return seg

    seg.labels = labels
    seg.values = values
    seg.basis = "近 4 年度總營收（yfinance 無部門別明細，以年度營收規模呈現）"
    return seg
