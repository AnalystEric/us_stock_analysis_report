"""股價與技術面：1 年日線 OHLCV、50/200 日均線、52 週高低點與距離百分比。"""
from __future__ import annotations

import logging

import pandas as pd

from config import PRICE_PERIOD
from core.models import PriceData
from data_sources.yf_client import get_ticker, safe_call, safe_fast_info

logger = logging.getLogger(__name__)


def _history(ticker: str, period: str) -> pd.DataFrame:
    tk = get_ticker(ticker)

    def _fetch() -> pd.DataFrame:
        df = tk.history(period=period, interval="1d", auto_adjust=False)
        return df if df is not None else pd.DataFrame()

    df = safe_call(_fetch, default=pd.DataFrame(), label="price.history")
    return df if isinstance(df, pd.DataFrame) else pd.DataFrame()


def fetch_price(ticker: str, period: str = PRICE_PERIOD) -> PriceData:
    data = PriceData()
    df = _history(ticker, period)

    if df.empty or "Close" not in df.columns:
        data.warning = "無法取得股價歷史資料。"
        return data

    df = df.dropna(subset=["Close"]).copy()
    if df.empty:
        data.warning = "股價歷史資料為空。"
        return data

    # 移動平均線（若資料點不足 200 天仍會盡量計算，不足處為 NaN）
    df["MA50"] = df["Close"].rolling(window=50, min_periods=1).mean()
    df["MA200"] = df["Close"].rolling(window=200, min_periods=1).mean()
    data.price_df = df

    close = df["Close"]
    data.current_price = float(close.iloc[-1])
    data.ma50 = float(df["MA50"].iloc[-1])
    data.ma200 = float(df["MA200"].iloc[-1])

    # 52 週高低點（以近一年資料為準）
    high_idx = df["High"].idxmax()
    low_idx = df["Low"].idxmin()
    data.week52_high = float(df["High"].max())
    data.week52_low = float(df["Low"].min())
    data.recent_high_date = high_idx.date() if hasattr(high_idx, "date") else None
    data.recent_low_date = low_idx.date() if hasattr(low_idx, "date") else None

    # 以 fast_info 的 year_high/low 校正（若可得，涵蓋盤中極值）
    fast = safe_fast_info(get_ticker(ticker))
    if fast.get("year_high"):
        data.week52_high = max(data.week52_high, float(fast["year_high"]))
    if fast.get("year_low"):
        data.week52_low = min(data.week52_low, float(fast["year_low"]))

    if data.current_price and data.week52_high:
        data.pct_from_high = (data.current_price - data.week52_high) / data.week52_high * 100
    if data.current_price and data.week52_low:
        data.pct_from_low = (data.current_price - data.week52_low) / data.week52_low * 100

    return data
