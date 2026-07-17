"""同業比較：依產業別找 3-4 家競品，比較市值、營收成長率、毛利率、淨利率、EV/Sales、Forward P/E。"""
from __future__ import annotations

import logging

import pandas as pd

from config import PEERS_MAX
from core.models import PeerComparison, PeerRow
from data_sources.yf_client import get_ticker, safe_call, safe_info

logger = logging.getLogger(__name__)


def _num(v) -> float | None:
    try:
        f = float(v)
        return None if pd.isna(f) else f
    except (TypeError, ValueError):
        return None


def _find_peer_symbols(self_ticker: str, info: dict) -> tuple[list[str], str]:
    industry_key = info.get("industryKey") or ""
    sector_key = info.get("sectorKey") or ""

    def _top(obj) -> list[str]:
        df = safe_call(lambda: obj.top_companies, default=None, label="peers.top_companies")
        if isinstance(df, pd.DataFrame) and not df.empty:
            return [str(s).upper() for s in df.index.tolist()]
        return []

    symbols, basis = [], ""
    if industry_key:
        try:
            import yfinance as yf
            symbols = _top(yf.Industry(industry_key))
            basis = f"產業別：{info.get('industry', industry_key)}"
        except Exception as exc:  # noqa: BLE001
            logger.debug("yf.Industry 失敗: %s", exc)
    if not symbols and sector_key:
        try:
            import yfinance as yf
            symbols = _top(yf.Sector(sector_key))
            basis = f"類股：{info.get('sector', sector_key)}"
        except Exception as exc:  # noqa: BLE001
            logger.debug("yf.Sector 失敗: %s", exc)

    self_upper = self_ticker.upper()
    peers = [s for s in symbols if s and s != self_upper][:PEERS_MAX]
    return peers, basis


def _row_from_info(ticker: str, is_self: bool = False) -> PeerRow:
    info = safe_info(get_ticker(ticker))
    return PeerRow(
        ticker=ticker.upper(),
        name=info.get("shortName") or info.get("longName") or ticker,
        market_cap=_num(info.get("marketCap")),
        revenue_growth=_num(info.get("revenueGrowth")),
        gross_margin=_num(info.get("grossMargins")),
        profit_margin=_num(info.get("profitMargins")),
        ev_sales=_num(info.get("enterpriseToRevenue")),
        forward_pe=_num(info.get("forwardPE")),
        is_self=is_self,
    )


def fetch_peers(ticker: str) -> PeerComparison:
    result = PeerComparison()
    info = safe_info(get_ticker(ticker))
    if not info:
        result.warning = "無法取得產業資訊，略過同業比較。"
        return result

    peer_symbols, basis = _find_peer_symbols(ticker, info)
    result.basis_note = basis

    result.rows.append(_row_from_info(ticker, is_self=True))
    for sym in peer_symbols:
        result.rows.append(_row_from_info(sym))

    if len(result.rows) <= 1:
        result.warning = "查無可比較的同業資料。"
    return result
