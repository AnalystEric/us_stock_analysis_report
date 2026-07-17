"""華爾街目標價與投資評等。

優先 yfinance（recommendationKey / targetMeanPrice 等）；
若 yfinance 無資料，退回 stockanalysis.com 公開摘要。
"""
from __future__ import annotations

import logging
import re

from core.models import RatingData
from data_sources.yf_client import get_ticker, safe_info
from utils.http import get_session, safe_get

logger = logging.getLogger(__name__)

_CONSENSUS_MAP = {
    "strong_buy": "Strong Buy",
    "buy": "Buy",
    "hold": "Hold",
    "underperform": "Underperform",
    "sell": "Sell",
    "strong_sell": "Strong Sell",
    "none": "",
}


def _from_yfinance(ticker: str) -> RatingData:
    info = safe_info(get_ticker(ticker))
    data = RatingData(source="yfinance")
    if not info:
        return data

    key = (info.get("recommendationKey") or "").lower()
    data.consensus = _CONSENSUS_MAP.get(key, key.replace("_", " ").title())
    data.num_analysts = info.get("numberOfAnalystOpinions")
    data.target_mean = info.get("targetMeanPrice")
    data.target_high = info.get("targetHighPrice")
    data.target_low = info.get("targetLowPrice")
    data.current_price = (
        info.get("currentPrice")
        or info.get("regularMarketPrice")
        or info.get("previousClose")
    )
    return data


def _from_stockanalysis(ticker: str) -> RatingData:
    """備援：抓 stockanalysis.com forecast 頁面的共識評等與平均目標價。"""
    data = RatingData(source="stockanalysis.com")
    url = f"https://stockanalysis.com/stocks/{ticker.lower()}/forecast/"
    resp = safe_get(get_session(), url)
    if resp is None:
        return data

    text = resp.text
    # 平均目標價：頁面文字通常含 "price target of $XXX" 或 "average ... $XXX"
    m = re.search(r"price target of \$?([\d,]+\.?\d*)", text, re.IGNORECASE)
    if m:
        try:
            data.target_mean = float(m.group(1).replace(",", ""))
        except ValueError:
            pass

    # 共識評等
    m2 = re.search(r"consensus rating[^A-Za-z]*(Strong Buy|Buy|Hold|Sell|Strong Sell)",
                   text, re.IGNORECASE)
    if m2:
        data.consensus = m2.group(1).title()

    return data


def _finalize(data: RatingData) -> RatingData:
    if data.current_price and data.target_mean:
        data.implied_upside_pct = (
            (data.target_mean - data.current_price) / data.current_price * 100
        )
    if not data.consensus and data.target_mean is None:
        data.warning = "查無華爾街評等與目標價資料。"
    return data


def fetch_rating(ticker: str, current_price: float | None = None) -> RatingData:
    data = _from_yfinance(ticker)

    # yfinance 沒抓到目標價 → 退回網站
    if data.target_mean is None and not data.consensus:
        logger.info("yfinance 無評等資料，改抓 stockanalysis.com")
        fallback = _from_stockanalysis(ticker)
        # 合併：以有值者為準
        data.consensus = data.consensus or fallback.consensus
        data.target_mean = data.target_mean if data.target_mean is not None else fallback.target_mean
        if fallback.consensus or fallback.target_mean is not None:
            data.source = "stockanalysis.com"

    if data.current_price is None and current_price is not None:
        data.current_price = current_price

    return _finalize(data)
