"""市場判別與台股清單目錄。

職責：
  * detect_market()：由使用者輸入判斷屬於美股或台股（上市 / 上櫃）。
  * TW 清單目錄：代號 ↔ 名稱 ↔ 市場（上市 TWSE / 上櫃 TPEX），以官方 OpenAPI 建立並快取一天。

資料源（合法、公開、免登入、免 API Key）：
  * 上市：https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL
  * 上櫃：https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes
清單抓取失敗時仍能運作：純數字輸入預設當上市（.TW），僅名稱查詢會失準。
"""
from __future__ import annotations

import json
import logging
import re
import time
from enum import Enum

from config import CACHE_DIR
from utils.http import get_session, safe_get

logger = logging.getLogger(__name__)


class Market(str, Enum):
    US = "US"
    TWSE = "TWSE"   # 上市 → yfinance 後綴 .TW
    TPEX = "TPEX"   # 上櫃 → yfinance 後綴 .TWO


_TWSE_LIST_URL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
_TPEX_LIST_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"

_CACHE_FILE = CACHE_DIR / "tw_directory.json"
_CACHE_TTL_SECONDS = 24 * 3600

# 台股代號：4~6 位數字，末尾可帶一個英文字母（如 00679B、2330）
_TW_CODE_RE = re.compile(r"^\d{4,6}[A-Za-z]?$")
# 含中日韓字元 → 視為中文公司名
_CJK_RE = re.compile(r"[一-鿿]")

_SUFFIX = {Market.TWSE: ".TW", Market.TPEX: ".TWO"}

# 記憶體內目錄快取：{code: {"name": str, "market": "TWSE"/"TPEX"}}
_directory: dict[str, dict] | None = None


# ---------------------------------------------------------------------------
# 清單目錄
# ---------------------------------------------------------------------------
def _fetch_twse_list(session) -> dict[str, dict]:
    resp = safe_get(session, _TWSE_LIST_URL, attempts=2,
                    headers={"accept": "application/json"})
    out: dict[str, dict] = {}
    if resp is None:
        return out
    try:
        for row in resp.json():
            code = str(row.get("Code", "")).strip()
            name = str(row.get("Name", "")).strip()
            if code and name:
                out[code] = {"name": name, "market": Market.TWSE.value}
    except (ValueError, AttributeError) as exc:
        logger.warning("解析上市清單失敗: %s", exc)
    return out


def _fetch_tpex_list(session) -> dict[str, dict]:
    # TPEX OpenAPI 回應量大且偶爾緩慢，拉長 timeout 並多重試
    resp = safe_get(session, _TPEX_LIST_URL, attempts=3, timeout=45,
                    headers={"accept": "application/json"})
    out: dict[str, dict] = {}
    if resp is None:
        return out
    try:
        for row in resp.json():
            code = str(row.get("SecuritiesCompanyCode", "")).strip()
            name = str(row.get("CompanyName", "")).strip()
            if code and name:
                out[code] = {"name": name, "market": Market.TPEX.value}
    except (ValueError, AttributeError) as exc:
        logger.warning("解析上櫃清單失敗: %s", exc)
    return out


def _load_cache() -> dict[str, dict] | None:
    if not _CACHE_FILE.exists():
        return None
    try:
        if time.time() - _CACHE_FILE.stat().st_mtime > _CACHE_TTL_SECONDS:
            return None
        data = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) and data else None
    except (OSError, ValueError):
        return None


def _save_cache(data: dict[str, dict]) -> None:
    try:
        _CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        logger.debug("寫入台股清單快取失敗: %s", exc)


def get_directory() -> dict[str, dict]:
    """回傳 {code: {"name", "market"}}；優先快取，過期或缺失則重新抓取。"""
    global _directory
    if _directory is not None:
        return _directory

    cached = _load_cache()
    if cached is not None:
        _directory = cached
        return _directory

    session = get_session()
    merged: dict[str, dict] = {}
    merged.update(_fetch_twse_list(session))
    merged.update(_fetch_tpex_list(session))

    if merged:
        _save_cache(merged)
        _directory = merged
    else:
        # 全抓失敗：退回舊快取（即使過期）以維持運作
        logger.warning("台股清單抓取失敗，改用（可能過期的）快取或空目錄")
        try:
            _directory = json.loads(_CACHE_FILE.read_text(encoding="utf-8")) \
                if _CACHE_FILE.exists() else {}
        except (OSError, ValueError):
            _directory = {}
    return _directory


# ---------------------------------------------------------------------------
# 查詢
# ---------------------------------------------------------------------------
def lookup_by_code(code: str) -> dict | None:
    """以純代號查目錄，回傳 {"code","name","market"} 或 None。"""
    entry = get_directory().get(str(code).strip())
    if entry:
        return {"code": str(code).strip(), **entry}
    return None


def lookup_by_name(name: str) -> dict | None:
    """以（部分）中文名稱查目錄，回傳最相符者 {"code","name","market"} 或 None。"""
    q = (name or "").strip()
    if not q:
        return None
    directory = get_directory()
    # 完全相符優先
    for code, info in directory.items():
        if info["name"] == q:
            return {"code": code, **info}
    # 其次：名稱包含輸入（挑代號最短者，通常為本尊而非衍生商品）
    matches = [(code, info) for code, info in directory.items() if q in info["name"]]
    if matches:
        matches.sort(key=lambda kv: (len(kv[1]["name"]), kv[0]))
        code, info = matches[0]
        return {"code": code, **info}
    return None


# ---------------------------------------------------------------------------
# 市場判別
# ---------------------------------------------------------------------------
def is_tw_market(market: str) -> bool:
    return market in (Market.TWSE.value, Market.TPEX.value)


def default_market_for_code(code: str) -> Market:
    """代號不在清單、或清單缺 TPEX 部分時的聰明預設。

    只要目錄非空（至少載到上市清單）而代號不在其中，即推定為上櫃（.TWO），
    因為上市清單抓取穩定；查無多半代表它是上櫃股。目錄全空才退回上市。
    """
    directory = get_directory()
    entry = directory.get(str(code).strip())
    if entry:
        return Market(entry["market"])
    if directory:
        return Market.TPEX
    return Market.TWSE


def yf_suffix(market: Market | str) -> str:
    m = Market(market) if not isinstance(market, Market) else market
    return _SUFFIX.get(m, "")


def detect_market(user_input: str) -> Market:
    """由使用者輸入粗略判斷市場（不查網路，僅看格式）。

    - 明確後綴 .TW / .TWO
    - 純數字（含末位字母）→ 台股（實際上市/上櫃由 resolver 查目錄決定，預設上市）
    - 含中文字 → 台股
    - 其餘 → 美股
    """
    raw = (user_input or "").strip()
    if not raw:
        return Market.US
    upper = raw.upper()
    if upper.endswith(".TWO"):
        return Market.TPEX
    if upper.endswith(".TW"):
        return Market.TWSE
    if _TW_CODE_RE.match(raw):
        return Market.TWSE
    if _CJK_RE.search(raw):
        return Market.TWSE
    return Market.US
