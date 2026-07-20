"""台股資料存取層：統一封裝官方 OpenAPI / 證交所 legacy JSON / FinMind 開放 API。

原則（與美股層一致）：
  * 全部呼叫包在容錯裡，抓不到回傳空結構，絕不拋例外拖垮整份報告。
  * 帶瀏覽器 User-Agent、含 retry（沿用 utils.http.safe_get）。
  * 同一次執行對「全市場單日檔」做記憶體快取，避免各區塊重複下載。

資料源皆為合法、公開、免登入：
  * TWSE OpenAPI：https://openapi.twse.com.tw/v1/...
  * TWSE legacy JSON：https://www.twse.com.tw/rwd/zh/...
  * TPEX OpenAPI：https://www.tpex.org.tw/openapi/v1/...
  * FinMind 開放資料（聚合官方 TWSE/TPEX/MOPS）：https://api.finmindtrade.com/api/v4/data
"""
from __future__ import annotations

import logging
from typing import Any

from utils.http import get_session, safe_get

logger = logging.getLogger(__name__)

_TWSE_OPENAPI = "https://openapi.twse.com.tw/v1"
_TWSE_LEGACY = "https://www.twse.com.tw/rwd/zh"
_TPEX_OPENAPI = "https://www.tpex.org.tw/openapi/v1"
_FINMIND = "https://api.finmindtrade.com/api/v4/data"

_session = None
# 全市場單日資料（如 MI_MARGN / STOCK_DAY_ALL）本次執行內快取
_dataset_cache: dict[str, Any] = {}


def _sess():
    global _session
    if _session is None:
        _session = get_session()
    return _session


# ---------------------------------------------------------------------------
# 日期
# ---------------------------------------------------------------------------
def roc_to_ad(roc: str) -> str:
    """民國日期字串 → 西元 ISO。'1150717' → '2026-07-17'；解析失敗回原字串。"""
    s = (roc or "").strip().replace("/", "")
    if len(s) >= 7 and s[:7].isdigit():
        try:
            y = int(s[:3]) + 1911
            return f"{y:04d}-{int(s[3:5]):02d}-{int(s[5:7]):02d}"
        except ValueError:
            return roc
    return roc


def roc_ym_to_period(roc_ym: str) -> str:
    """民國年月 '11506' → '2026-06'（資料年月＝營收所屬月份）。"""
    s = (roc_ym or "").strip()
    if len(s) >= 5 and s[:5].isdigit():
        try:
            return f"{int(s[:3]) + 1911:04d}-{int(s[3:5]):02d}"
        except ValueError:
            return roc_ym
    return roc_ym


# ---------------------------------------------------------------------------
# 取數
# ---------------------------------------------------------------------------
def twse_openapi(path: str, *, timeout: int = 25, cache_key: str | None = None) -> list[dict]:
    """呼叫 TWSE OpenAPI，回傳 list[dict]；失敗回空 list。"""
    if cache_key and cache_key in _dataset_cache:
        return _dataset_cache[cache_key]
    url = f"{_TWSE_OPENAPI}/{path.lstrip('/')}"
    resp = safe_get(_sess(), url, attempts=2, timeout=timeout,
                    headers={"accept": "application/json"})
    data: list[dict] = []
    if resp is not None:
        try:
            j = resp.json()
            data = j if isinstance(j, list) else []
        except ValueError:
            logger.warning("TWSE OpenAPI 回應非 JSON：%s", path)
    if cache_key:
        _dataset_cache[cache_key] = data
    return data


def tpex_openapi(path: str, *, timeout: int = 40, cache_key: str | None = None) -> list[dict]:
    if cache_key and cache_key in _dataset_cache:
        return _dataset_cache[cache_key]
    url = f"{_TPEX_OPENAPI}/{path.lstrip('/')}"
    resp = safe_get(_sess(), url, attempts=3, timeout=timeout,
                    headers={"accept": "application/json"})
    data: list[dict] = []
    if resp is not None:
        try:
            j = resp.json()
            data = j if isinstance(j, list) else []
        except ValueError:
            logger.warning("TPEX OpenAPI 回應非 JSON：%s", path)
    if cache_key:
        _dataset_cache[cache_key] = data
    return data


def twse_legacy(path: str, params: dict | None = None, *, timeout: int = 20) -> dict:
    """呼叫證交所 legacy rwd JSON（如 T86 三大法人）；回傳 dict，失敗回空 dict。"""
    url = f"{_TWSE_LEGACY}/{path.lstrip('/')}"
    resp = safe_get(_sess(), url, attempts=2, timeout=timeout, params=params or {})
    if resp is None:
        return {}
    try:
        return resp.json()
    except ValueError:
        return {}


def finmind(dataset: str, data_id: str, start_date: str, *,
            end_date: str | None = None, timeout: int = 25) -> list[dict]:
    """FinMind 開放資料查詢（免 token，低頻使用）。失敗回空 list。"""
    params = {"dataset": dataset, "data_id": data_id, "start_date": start_date}
    if end_date:
        params["end_date"] = end_date
    resp = safe_get(_sess(), _FINMIND, attempts=2, timeout=timeout, params=params)
    if resp is None:
        return []
    try:
        j = resp.json()
    except ValueError:
        return []
    if j.get("status") != 200:
        logger.info("FinMind %s 回應非成功：%s", dataset, j.get("msg"))
        return []
    return j.get("data", []) or []


# ---------------------------------------------------------------------------
# 解析小工具
# ---------------------------------------------------------------------------
def to_float(v) -> float | None:
    """把含千分位逗號 / 空白的字串轉 float；空值回 None。"""
    if v is None:
        return None
    s = str(v).replace(",", "").replace("%", "").strip()
    if s in ("", "-", "--", "N/A"):
        return None
    try:
        return float(s)
    except ValueError:
        return None
