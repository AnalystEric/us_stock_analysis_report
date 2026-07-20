"""台股三大法人買賣超（外資 / 投信 / 自營商）近 ~20 個交易日趨勢與期間累計。

  * 趨勢：FinMind `TaiwanStockInstitutionalInvestorsBuySell`（每日、分法人別，單位：股）。
      外資 = Foreign_Investor + Foreign_Dealer_Self
      投信 = Investment_Trust
      自營商 = Dealer_self + Dealer_Hedging
  * 備援：證交所 T86（單一交易日全市場三大法人買賣超）。
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from core.models import InstDayPoint, InstitutionalFlow
from data_sources.tw.tw_client import finmind, to_float, twse_legacy

logger = logging.getLogger(__name__)

_WINDOW = 20

_FOREIGN = {"Foreign_Investor", "Foreign_Dealer_Self"}
_TRUST = {"Investment_Trust"}
_DEALER = {"Dealer_self", "Dealer_Hedging"}


def _from_finmind(code: str) -> list[InstDayPoint]:
    start = (date.today() - timedelta(days=45)).isoformat()
    rows = finmind("TaiwanStockInstitutionalInvestorsBuySell", code, start)
    if not rows:
        return []

    by_date: dict[str, dict[str, float]] = {}
    for r in rows:
        d = r.get("date")
        name = r.get("name")
        buy = to_float(r.get("buy")) or 0.0
        sell = to_float(r.get("sell")) or 0.0
        if not d or not name:
            continue
        net = buy - sell
        agg = by_date.setdefault(d, {"foreign": 0.0, "trust": 0.0, "dealer": 0.0})
        if name in _FOREIGN:
            agg["foreign"] += net
        elif name in _TRUST:
            agg["trust"] += net
        elif name in _DEALER:
            agg["dealer"] += net

    points: list[InstDayPoint] = []
    for d in sorted(by_date.keys()):
        a = by_date[d]
        total = a["foreign"] + a["trust"] + a["dealer"]
        points.append(InstDayPoint(date=d, foreign=a["foreign"], trust=a["trust"],
                                   dealer=a["dealer"], total=total))
    return points[-_WINDOW:]


def _from_t86(code: str) -> list[InstDayPoint]:
    """證交所 T86 備援：抓最近有資料的一個交易日（往回試幾天）。"""
    for back in range(0, 7):
        d = date.today() - timedelta(days=back)
        payload = twse_legacy("fund/T86", {
            "date": d.strftime("%Y%m%d"), "selectType": "ALL", "response": "json"})
        if payload.get("stat") != "OK":
            continue
        fields = payload.get("fields", [])
        rows = payload.get("data", [])
        idx = {name: i for i, name in enumerate(fields)}

        def col(row, *keys):
            for k in keys:
                for name, i in idx.items():
                    if k in name and i < len(row):
                        return to_float(row[i])
            return None

        for row in rows:
            if row and str(row[0]).strip() == code:
                foreign = col(row, "外陸資買賣超股數(不含外資自營商)", "外資買賣超")
                trust = col(row, "投信買賣超股數", "投信買賣超")
                dealer = col(row, "自營商買賣超股數")
                total = col(row, "三大法人買賣超股數")
                return [InstDayPoint(date=d.isoformat(), foreign=foreign, trust=trust,
                                    dealer=dealer, total=total)]
    return []


def fetch_institutional(code: str, market: str = "TWSE") -> InstitutionalFlow:
    data = InstitutionalFlow()

    points = _from_finmind(code)
    if points:
        data.source = "FinMind（每日三大法人買賣超）"
    else:
        points = _from_t86(code)
        if points:
            data.source = "TWSE 三大法人買賣超（T86）"

    if not points:
        data.warning = "查無三大法人買賣超資料。"
        return data

    data.days = points
    data.window_days = len(points)
    data.foreign_sum = sum(p.foreign or 0 for p in points)
    data.trust_sum = sum(p.trust or 0 for p in points)
    data.dealer_sum = sum(p.dealer or 0 for p in points)
    data.total_sum = sum(p.total or 0 for p in points)

    # 情緒註解（以「張」＝股/1000 呈現較貼近台股習慣）
    def lots(v):
        return None if v is None else v / 1000

    f = lots(data.foreign_sum)
    if f is not None:
        window = data.window_days
        if f > 0:
            data.sentiment_note = (
                f"近 {window} 個交易日外資合計買超約 {f:,.0f} 張，籌碼面偏多。")
        elif f < 0:
            data.sentiment_note = (
                f"近 {window} 個交易日外資合計賣超約 {abs(f):,.0f} 張，籌碼面偏空。")
        else:
            data.sentiment_note = f"近 {window} 個交易日外資買賣大致持平。"
    return data
