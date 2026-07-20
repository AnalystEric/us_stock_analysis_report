"""台股月營收：近 ~15 個月當月營收、年增（YoY）、月增（MoM）、今年累計與累計 YoY。

月營收是台股最即時、最受重視的營運指標。
  * 趨勢序列：FinMind `TaiwanStockMonthRevenue`（聚合官方 TWSE/MOPS，含歷史）。
  * 權威最新值與成長原因備註：TWSE OpenAPI `t187ap05_L`（上市公司每月營業收入彙總表）。
兩者互為補強；任一失敗仍盡量填出可得欄位。
"""
from __future__ import annotations

import logging

from core.models import MonthlyRevenue, MonthRevPoint
from data_sources.tw.tw_client import roc_ym_to_period, to_float, twse_openapi

logger = logging.getLogger(__name__)

_LOOKBACK_MONTHS = 15


def _from_finmind(code: str) -> list[MonthRevPoint]:
    from data_sources.tw.tw_client import finmind
    # 抓約 2.5 年以確保能算 YoY
    rows = finmind("TaiwanStockMonthRevenue", code, "2023-01-01")
    if not rows:
        return []

    # 以 (年, 月) 為鍵；FinMind 的 revenue_year/revenue_month 即營收所屬年月
    by_ym: dict[tuple[int, int], float] = {}
    for r in rows:
        y = r.get("revenue_year")
        m = r.get("revenue_month")
        rev = to_float(r.get("revenue"))
        if y is None or m is None or rev is None:
            continue
        by_ym[(int(y), int(m))] = rev

    keys = sorted(by_ym.keys())
    points: list[MonthRevPoint] = []
    for i, (y, m) in enumerate(keys):
        rev = by_ym[(y, m)]
        p = MonthRevPoint(period=f"{y:04d}-{m:02d}", revenue=rev)
        prev_year = by_ym.get((y - 1, m))
        if prev_year:
            p.yoy = (rev - prev_year) / abs(prev_year)
        if i > 0:
            prev = by_ym[keys[i - 1]]
            if prev:
                p.mom = (rev - prev) / abs(prev)
        points.append(p)
    return points[-_LOOKBACK_MONTHS:]


def _twse_latest(code: str) -> dict | None:
    """TWSE OpenAPI 上市月營收彙總（最新一期），取權威數值與成長原因備註。"""
    rows = twse_openapi("opendata/t187ap05_L", cache_key="t187ap05_L")
    for r in rows:
        if str(r.get("公司代號", "")).strip() == code:
            return r
    return None


def fetch_monthly_revenue(code: str, market: str = "TWSE") -> MonthlyRevenue:
    data = MonthlyRevenue(source="FinMind / TWSE 公開資訊觀測站")

    points = _from_finmind(code)
    if points:
        data.points = points
        last = points[-1]
        data.latest_period = last.period
        data.latest_revenue = last.revenue
        data.latest_yoy = last.yoy
        data.latest_mom = last.mom

    # 上市：以 TWSE 官方彙總補權威最新值、累計與備註（值為千元，需 ×1000 轉元）
    official = _twse_latest(code) if market == "TWSE" else None
    if official:
        period = roc_ym_to_period(str(official.get("資料年月", "")))
        cur = to_float(official.get("營業收入-當月營收"))
        yoy = to_float(official.get("營業收入-去年同月增減(%)"))
        mom = to_float(official.get("營業收入-上月比較增減(%)"))
        cum = to_float(official.get("累計營業收入-當月累計營收"))
        cum_yoy = to_float(official.get("累計營業收入-前期比較增減(%)"))
        note = str(official.get("備註", "")).strip()

        if cur is not None:
            data.latest_period = period or data.latest_period
            data.latest_revenue = cur * 1000
            data.latest_yoy = (yoy / 100) if yoy is not None else data.latest_yoy
            data.latest_mom = (mom / 100) if mom is not None else data.latest_mom
        if cum is not None:
            data.cum_revenue = cum * 1000
        if cum_yoy is not None:
            data.cum_yoy = cum_yoy / 100
        if note and note not in ("-", "無"):
            data.note = note

    if not data.points and data.latest_revenue is None:
        data.warning = "查無月營收資料。"
    return data
