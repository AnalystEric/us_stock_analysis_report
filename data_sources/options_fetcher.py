"""選擇權情緒：近月合約 Put/Call Ratio（以未平倉量 Open Interest 計算）。"""
from __future__ import annotations

import logging

import pandas as pd

from core.models import OptionsSentiment
from data_sources.yf_client import get_ticker, safe_call

logger = logging.getLogger(__name__)


def fetch_options_sentiment(ticker: str) -> OptionsSentiment:
    tk = get_ticker(ticker)
    data = OptionsSentiment()

    expirations = safe_call(lambda: tk.options, default=(), label="options.expirations")
    if not expirations:
        data.warning = "查無選擇權數據。"
        return data

    expiry = expirations[0]
    data.expiry = expiry

    chain = safe_call(lambda: tk.option_chain(expiry), default=None, label="option_chain")
    if chain is None:
        data.warning = "查無選擇權數據。"
        return data

    try:
        calls = chain.calls
        puts = chain.puts
    except Exception:  # noqa: BLE001
        data.warning = "查無選擇權數據。"
        return data

    call_oi = _sum_oi(calls)
    put_oi = _sum_oi(puts)
    data.call_oi = call_oi
    data.put_oi = put_oi

    if call_oi and put_oi is not None and call_oi > 0:
        ratio = put_oi / call_oi
        data.put_call_ratio = ratio
        if ratio > 1.1:
            data.sentiment_note = (
                f"Put/Call Ratio 約 {ratio:.2f}（Put 較多），市場情緒偏向避險 / 看空。"
            )
        elif ratio < 0.7:
            data.sentiment_note = (
                f"Put/Call Ratio 約 {ratio:.2f}（Call 較多），市場情緒偏向看多。"
            )
        else:
            data.sentiment_note = (
                f"Put/Call Ratio 約 {ratio:.2f}，多空情緒大致中性。"
            )
    else:
        data.warning = "查無選擇權數據。"

    return data


def _sum_oi(df: pd.DataFrame | None) -> int | None:
    if not isinstance(df, pd.DataFrame) or df.empty or "openInterest" not in df.columns:
        return None
    try:
        return int(df["openInterest"].fillna(0).sum())
    except Exception:  # noqa: BLE001
        return None
