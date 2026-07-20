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
from dataclasses import dataclass

from core.market import (
    Market,
    default_market_for_code,
    detect_market,
    lookup_by_code,
    lookup_by_name,
    yf_suffix,
)
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
    # 台股
    "TAI": "臺灣證券交易所",
    "TWO": "證券櫃檯買賣中心（上櫃）",
}


class StockNotFoundError(Exception):
    """無法將輸入解析為有效股票代號。"""


@dataclass
class ResolvedStock:
    """解析後的個股：symbol 為 yfinance 用代號（台股帶 .TW/.TWO）。"""
    symbol: str            # yfinance 代號，例如 AAPL / 2330.TW / 6488.TWO
    market: str            # "US" / "TWSE" / "TPEX"
    code: str = ""         # 台股純代號（如 2330）；美股留空
    name: str = ""         # 已知的公司名（台股由官方清單帶入，可為空）


def _looks_like_ticker(text: str) -> bool:
    return bool(_TICKER_RE.match(text.strip()))


# ---------------------------------------------------------------------------
# 台股解析
# ---------------------------------------------------------------------------
def _resolve_tw(raw: str, hinted: Market) -> ResolvedStock:
    """把台股輸入（純代號 / 中文名 / 帶 .TW·.TWO）解析為 ResolvedStock。"""
    upper = raw.upper()

    # 1) 已帶後綴 → 直接採用
    if upper.endswith(".TWO") or upper.endswith(".TW"):
        market = Market.TPEX if upper.endswith(".TWO") else Market.TWSE
        code = upper.rsplit(".", 1)[0]
        info = lookup_by_code(code)
        if info:
            market = Market(info["market"])
        return ResolvedStock(symbol=f"{code}{yf_suffix(market)}", market=market.value,
                             code=code, name=(info or {}).get("name", ""))

    # 2) 純代號 → 查官方清單決定上市/上櫃
    if _TW_CODE_RE.match(raw):
        code = raw
        info = lookup_by_code(code)
        if info:
            market = Market(info["market"])
            return ResolvedStock(symbol=f"{code}{yf_suffix(market)}",
                                 market=market.value, code=code, name=info["name"])
        # 查不到清單：以聰明預設判斷（不在上市清單 → 多為上櫃 .TWO）
        market = default_market_for_code(code)
        logger.warning("代號 %s 不在清單中，預設當 %s 處理", code, market.value)
        return ResolvedStock(symbol=f"{code}{yf_suffix(market)}",
                             market=market.value, code=code)

    # 3) 中文名稱 → 查清單
    info = lookup_by_name(raw)
    if info:
        market = Market(info["market"])
        logger.info("已將「%s」解析為台股 %s（%s）", raw, info["code"], info["name"])
        return ResolvedStock(symbol=f"{info['code']}{yf_suffix(market)}",
                             market=market.value, code=info["code"], name=info["name"])

    raise StockNotFoundError(
        f"無法將「{raw}」解析為台股，請改用股票代號（例如 2330）重試。"
    )


_TW_CODE_RE = re.compile(r"^\d{4,6}[A-Za-z]?$")


def _tw_candidates(raw: str, limit: int = 6) -> list[dict]:
    """由官方台股清單建立候選（供前端驗證 / 建議）。"""
    from core.market import get_directory

    upper = raw.upper()
    code_q = upper.rsplit(".", 1)[0] if (
        upper.endswith(".TW") or upper.endswith(".TWO")) else raw
    directory = get_directory()
    ex_name = {"TWSE": "上市", "TPEX": "上櫃"}
    out: list[dict] = []

    # 純代號：完全相符優先，其餘做前綴比對
    if _TW_CODE_RE.match(code_q):
        matches = ([(code_q, directory[code_q])] if code_q in directory else [])
        matches += [(c, i) for c, i in directory.items()
                    if c.startswith(code_q) and c != code_q]
    else:
        matches = [(c, i) for c, i in directory.items() if raw in i["name"]]
        matches.sort(key=lambda kv: (len(kv[1]["name"]), kv[0]))

    for code, info in matches[:limit]:
        suffix = ".TWO" if info["market"] == "TPEX" else ".TW"
        out.append({
            "symbol": f"{code}{suffix}",
            "name": info["name"],
            "exchange": ex_name.get(info["market"], info["market"]),
        })
    return out


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

    # 台股：直接查官方清單目錄（純代號 / 中文名 / 帶後綴）
    if detect_market(raw) in (Market.TWSE, Market.TPEX):
        return _tw_candidates(raw, limit)

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


def resolve_stock(user_input: str) -> ResolvedStock:
    """解析輸入為 ResolvedStock（含市場別）。支援美股與台股。"""
    raw = (user_input or "").strip()
    if not raw:
        raise StockNotFoundError("輸入為空，請提供股票代號或公司名稱。")

    market = detect_market(raw)
    if market in (Market.TWSE, Market.TPEX):
        return _resolve_tw(raw, market)

    # --- 美股 ---
    quotes = _yahoo_search(raw) or _yfinance_search(raw)
    best = _pick_best(quotes, raw)
    if best and best.get("symbol"):
        symbol = best["symbol"].upper()
        name = best.get("shortname") or best.get("longname") or ""
        logger.info("已將輸入「%s」解析為代號 %s（%s）", raw, symbol, name)
        return ResolvedStock(symbol=symbol, market=Market.US.value, name=name)

    if _looks_like_ticker(raw):
        symbol = raw.upper()
        logger.warning("搜尋無結果，直接沿用輸入為代號：%s", symbol)
        return ResolvedStock(symbol=symbol, market=Market.US.value)

    raise StockNotFoundError(
        f"無法將「{raw}」解析為有效的股票代號，請改用代號（美股如 AAPL、台股如 2330）重試。"
    )


def resolve(user_input: str) -> str:
    """回傳正規化後的 yfinance 股票代號（相容舊介面）。"""
    return resolve_stock(user_input).symbol
