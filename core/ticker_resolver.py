"""股票正規化：使用者輸入代號或公司名 → 標準美股 Ticker。

流程：
  1. 若輸入本身就像代號（短、無空白），先當作代號候選。
  2. 用 Yahoo Finance search endpoint 依關鍵字查詢，挑最合適的 EQUITY。
  3. yfinance 內建 Search 作為備援。
  4. 全部失敗時，若輸入像代號就直接沿用（大寫），否則拋出 StockNotFoundError。
"""
from __future__ import annotations

import logging
import re

from utils.http import get_session, safe_get

logger = logging.getLogger(__name__)

_YAHOO_SEARCH_URL = "https://query2.finance.yahoo.com/v1/finance/search"
_TICKER_RE = re.compile(r"^[A-Za-z][A-Za-z.\-]{0,6}$")

# 美股常見交易所代碼 → 顯示名稱
EXCHANGE_MAP = {
    "NMS": "NASDAQ",
    "NGM": "NASDAQ",
    "NCM": "NASDAQ",
    "NAS": "NASDAQ",
    "NYQ": "NYSE",
    "NYS": "NYSE",
    "PCX": "NYSE Arca",
    "ASE": "NYSE American",
    "BATS": "Cboe BZX",
}


class StockNotFoundError(Exception):
    """無法將輸入解析為有效股票代號。"""


def _looks_like_ticker(text: str) -> bool:
    return bool(_TICKER_RE.match(text.strip()))


def _yahoo_search(query: str) -> list[dict]:
    session = get_session()
    # 只嘗試一次：此端點常回 429，且有 yfinance Search 作為備援，不值得重試等待
    resp = safe_get(
        session,
        _YAHOO_SEARCH_URL,
        attempts=1,
        params={"q": query, "quotesCount": 10, "newsCount": 0, "lang": "en-US"},
    )
    if resp is None:
        return []
    try:
        data = resp.json()
    except ValueError:
        return []
    return data.get("quotes", []) or []


def _yfinance_search(query: str) -> list[dict]:
    try:
        import yfinance as yf

        result = yf.Search(query, max_results=10)
        return result.quotes or []
    except Exception as exc:  # noqa: BLE001
        logger.debug("yfinance Search 失敗: %s", exc)
        return []


def _pick_best(quotes: list[dict], raw: str) -> dict | None:
    """從搜尋結果挑最合適的股票（優先 EQUITY / 美股交易所 / 與輸入相符）。"""
    raw_upper = raw.upper().strip()
    equities = [q for q in quotes if (q.get("quoteType") or "").upper() == "EQUITY"]
    pool = equities or quotes
    if not pool:
        return None

    # 完全等於輸入代號者最優先
    for q in pool:
        if (q.get("symbol") or "").upper() == raw_upper:
            return q

    # 其次挑美股交易所的第一筆
    for q in pool:
        if (q.get("exchange") or "") in EXCHANGE_MAP:
            return q

    return pool[0]


def search_candidates(query: str, limit: int = 6) -> list[dict]:
    """回傳與輸入相符的股票候選清單（供前端驗證 / 建議）。

    每筆為 {"symbol", "name", "exchange"}；優先 EQUITY。查無則回傳空清單。
    """
    raw = (query or "").strip()
    if not raw:
        return []
    quotes = _yahoo_search(raw) or _yfinance_search(raw)
    out: list[dict] = []
    seen: set[str] = set()
    # EQUITY 優先，其餘其次
    ordered = [q for q in quotes if (q.get("quoteType") or "").upper() == "EQUITY"]
    ordered += [q for q in quotes if q not in ordered]
    for q in ordered:
        sym = (q.get("symbol") or "").upper()
        if not sym or sym in seen:
            continue
        seen.add(sym)
        out.append({
            "symbol": sym,
            "name": q.get("shortname") or q.get("longname") or "",
            "exchange": EXCHANGE_MAP.get(q.get("exchange", ""), q.get("exchange", "")),
        })
        if len(out) >= limit:
            break
    return out


def resolve(user_input: str) -> str:
    """回傳正規化後的股票代號（大寫）。找不到時拋 StockNotFoundError。"""
    raw = (user_input or "").strip()
    if not raw:
        raise StockNotFoundError("輸入為空，請提供股票代號或公司名稱。")

    quotes = _yahoo_search(raw) or _yfinance_search(raw)
    best = _pick_best(quotes, raw)

    if best and best.get("symbol"):
        symbol = best["symbol"].upper()
        name = best.get("shortname") or best.get("longname") or ""
        logger.info("已將輸入「%s」解析為代號 %s（%s）", raw, symbol, name)
        return symbol

    if _looks_like_ticker(raw):
        symbol = raw.upper()
        logger.warning("搜尋無結果，直接沿用輸入為代號：%s", symbol)
        return symbol

    raise StockNotFoundError(
        f"無法將「{raw}」解析為有效的美股代號，請改用股票代號（例如 AAPL）重試。"
    )
