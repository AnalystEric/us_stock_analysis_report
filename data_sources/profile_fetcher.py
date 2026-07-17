"""個股基本資訊（公司名、交易所、產業、市值等）。"""
from __future__ import annotations

import logging

from core.models import CompanyProfile
from core.ticker_resolver import EXCHANGE_MAP
from data_sources.yf_client import get_ticker, safe_fast_info, safe_info

logger = logging.getLogger(__name__)


def fetch_profile(ticker: str) -> CompanyProfile:
    tk = get_ticker(ticker)
    info = safe_info(tk)
    fast = safe_fast_info(tk)

    profile = CompanyProfile(ticker=ticker.upper())

    if not info and not fast:
        profile.warning = "無法取得公司基本資料（yfinance 回傳空值）。"
        profile.company_name = ticker.upper()
        return profile

    profile.company_name = (
        info.get("longName") or info.get("shortName") or ticker.upper()
    )
    exch_code = info.get("exchange") or ""
    profile.exchange = exch_code
    profile.exchange_name = EXCHANGE_MAP.get(exch_code, info.get("fullExchangeName", exch_code))
    profile.sector = info.get("sector", "") or ""
    profile.industry = info.get("industry", "") or ""
    profile.market_cap = info.get("marketCap") or fast.get("market_cap")
    profile.currency = info.get("currency") or fast.get("currency") or "USD"
    profile.website = info.get("website", "") or ""
    profile.long_summary = info.get("longBusinessSummary", "") or ""
    profile.country = info.get("country", "") or ""
    emp = info.get("fullTimeEmployees")
    profile.employees = int(emp) if isinstance(emp, (int, float)) else None

    if not profile.sector and not profile.industry:
        profile.warning = "產業分類資料不完整。"

    return profile
