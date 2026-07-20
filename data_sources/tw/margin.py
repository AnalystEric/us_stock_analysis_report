"""台股融資融券餘額（最新交易日）。

  * 上市：TWSE OpenAPI `MI_MARGN`（集中市場融資融券餘額，單位：張）。
  * 兩市備援：FinMind `TaiwanStockMarginPurchaseShortSale`（餘額單位：張）。
融資餘額增加通常代表散戶追價、籌碼偏亂；融券餘額為潛在回補買盤。
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from core.models import MarginData
from data_sources.tw.tw_client import finmind, to_float, twse_openapi

logger = logging.getLogger(__name__)


def _from_twse(code: str) -> MarginData | None:
    rows = twse_openapi("exchangeReport/MI_MARGN", cache_key="MI_MARGN")
    for r in rows:
        if str(r.get("股票代號", "")).strip() == code:
            m = MarginData(source="TWSE 集中市場融資融券餘額")
            today = to_float(r.get("融資今日餘額"))
            prev = to_float(r.get("融資前日餘額"))
            m.margin_balance = today
            if today is not None and prev is not None:
                m.margin_change = today - prev
            s_today = to_float(r.get("融券今日餘額"))
            s_prev = to_float(r.get("融券前日餘額"))
            m.short_balance = s_today
            if s_today is not None and s_prev is not None:
                m.short_change = s_today - s_prev
            m.note = "單位：張"
            return m
    return None


def _from_finmind(code: str) -> MarginData | None:
    start = (date.today() - timedelta(days=10)).isoformat()
    rows = finmind("TaiwanStockMarginPurchaseShortSale", code, start)
    if not rows:
        return None
    rows = sorted(rows, key=lambda r: r.get("date", ""))
    last = rows[-1]
    m = MarginData(source="FinMind 融資融券", date=last.get("date", ""))

    # FinMind 融資融券餘額單位即為「張」
    m.margin_balance = to_float(last.get("MarginPurchaseTodayBalance"))
    prev_m = to_float(last.get("MarginPurchaseYesterdayBalance"))
    if m.margin_balance is not None and prev_m is not None:
        m.margin_change = m.margin_balance - prev_m
    m.short_balance = to_float(last.get("ShortSaleTodayBalance"))
    prev_s = to_float(last.get("ShortSaleYesterdayBalance"))
    if m.short_balance is not None and prev_s is not None:
        m.short_change = m.short_balance - prev_s
    m.note = "單位：張"
    return m


def fetch_margin(code: str, market: str = "TWSE") -> MarginData:
    m = _from_twse(code) if market == "TWSE" else None
    if m is None:
        m = _from_finmind(code)
    if m is None:
        return MarginData(warning="查無融資融券資料。")
    return m
