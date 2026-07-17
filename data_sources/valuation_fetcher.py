"""估值倍數：Trailing/Forward P/E、P/S、EV/Sales、EV/EBITDA、EV/FCF、PEG、P/B，
以及近 3 年近似 P/E 趨勢（以歷史股價 ÷ 目前 TTM EPS 推算，僅供位階參考）。
"""
from __future__ import annotations

import logging

import pandas as pd

from analytics.metrics import safe_div
from config import PRICE_PERIOD_VALUATION
from core.models import ValuationMultiples
from data_sources.yf_client import get_ticker, safe_call, safe_info

logger = logging.getLogger(__name__)


def _num(v) -> float | None:
    try:
        f = float(v)
        return None if pd.isna(f) else f
    except (TypeError, ValueError):
        return None


def fetch_valuation(ticker: str) -> ValuationMultiples:
    tk = get_ticker(ticker)
    info = safe_info(tk)
    v = ValuationMultiples()
    if not info:
        v.warning = "無法取得估值資料。"
        return v

    v.trailing_pe = _num(info.get("trailingPE"))
    v.forward_pe = _num(info.get("forwardPE"))
    v.ps_ratio = _num(info.get("priceToSalesTrailing12Months"))
    v.ev_sales = _num(info.get("enterpriseToRevenue"))
    v.ev_ebitda = _num(info.get("enterpriseToEbitda"))
    v.peg = _num(info.get("trailingPegRatio") or info.get("pegRatio"))
    v.price_to_book = _num(info.get("priceToBook"))

    ev = _num(info.get("enterpriseValue"))
    fcf = _num(info.get("freeCashflow"))
    v.ev_fcf = safe_div(ev, fcf)

    # 近似歷史 P/E 趨勢
    trailing_eps = _num(info.get("trailingEps"))
    if trailing_eps and trailing_eps > 0:
        def _hist():
            df = tk.history(period=PRICE_PERIOD_VALUATION, interval="1wk", auto_adjust=False)
            return df if df is not None else pd.DataFrame()
        df = safe_call(_hist, default=pd.DataFrame(), label="valuation.history")
        if isinstance(df, pd.DataFrame) and not df.empty and "Close" in df.columns:
            pe_series = (df["Close"] / trailing_eps).dropna()
            if not pe_series.empty:
                v.pe_series = pe_series
                v.pe_mean_3y = float(pe_series.mean())
                v.pe_current = v.trailing_pe or float(pe_series.iloc[-1])

    if v.pe_current and v.pe_mean_3y:
        diff = (v.pe_current - v.pe_mean_3y) / v.pe_mean_3y * 100
        if diff > 10:
            v.pe_context_note = (
                f"目前本益比約 {v.pe_current:.1f} 倍，高於近 3 年均值 "
                f"{v.pe_mean_3y:.1f} 倍約 {diff:.0f}%，估值處於相對偏貴區間。"
            )
        elif diff < -10:
            v.pe_context_note = (
                f"目前本益比約 {v.pe_current:.1f} 倍，低於近 3 年均值 "
                f"{v.pe_mean_3y:.1f} 倍約 {abs(diff):.0f}%，估值處於相對便宜區間。"
            )
        else:
            v.pe_context_note = (
                f"目前本益比約 {v.pe_current:.1f} 倍，接近近 3 年均值 "
                f"{v.pe_mean_3y:.1f} 倍，估值處於中性區間。"
            )

    if v.trailing_pe is None and v.forward_pe is None and v.ps_ratio is None:
        v.warning = "查無主要估值倍數（可能為虧損公司或資料不足）。"
    return v
