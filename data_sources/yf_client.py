"""yfinance 存取層。

集中處理：
  * 以瀏覽器 User-Agent 建立 session（優先 curl_cffi 瀏覽器指紋模擬，降低被 Yahoo 阻擋機率）。
  * Ticker 物件快取，避免重複建立。
  * 所有對 yfinance 的呼叫都包在 try/except，抓不到資料回傳空值 / 空結構，絕不讓程式崩潰。
"""
from __future__ import annotations

import logging
from typing import Any, Callable

import yfinance as yf

from config import HTTP_USER_AGENT
from utils.retry import run_with_retry

logger = logging.getLogger(__name__)


def _build_session():
    """建立帶瀏覽器指紋 / User-Agent 的 session；失敗則回傳 None（yfinance 用內建預設）。"""
    # 1) 優先 curl_cffi：可模擬 Chrome TLS 指紋，Yahoo 較不會擋
    try:
        from curl_cffi import requests as cffi_requests

        session = cffi_requests.Session(impersonate="chrome")
        session.headers.update({"User-Agent": HTTP_USER_AGENT})
        logger.debug("yfinance 使用 curl_cffi (impersonate=chrome) session")
        return session
    except Exception as exc:  # noqa: BLE001
        logger.debug("curl_cffi session 建立失敗（%s），改試 requests", exc)

    # 2) 退回一般 requests session
    try:
        import requests

        session = requests.Session()
        session.headers.update({"User-Agent": HTTP_USER_AGENT})
        return session
    except Exception:  # noqa: BLE001
        return None


_session = None
_ticker_cache: dict[str, "yf.Ticker"] = {}


def get_ticker(symbol: str) -> "yf.Ticker":
    """回傳（快取的）yf.Ticker。若 session 參數不被接受則以無 session 方式建立。"""
    global _session
    symbol = symbol.upper().strip()
    if symbol in _ticker_cache:
        return _ticker_cache[symbol]

    if _session is None:
        _session = _build_session()

    tk: "yf.Ticker" | None = None
    if _session is not None:
        try:
            tk = yf.Ticker(symbol, session=_session)
        except Exception as exc:  # noqa: BLE001 - 某些 yfinance 版本 session 相容性問題
            logger.debug("yf.Ticker(session=...) 失敗（%s），改用預設 session", exc)
    if tk is None:
        tk = yf.Ticker(symbol)

    _ticker_cache[symbol] = tk
    return tk


def safe_call(func: Callable[[], Any], *, default: Any = None, label: str = "yf") -> Any:
    """對 yfinance 呼叫做 retry 包裝，最終失敗回傳 default。"""
    return run_with_retry(func, default=default, label=label)


def safe_info(tk: "yf.Ticker") -> dict:
    """取得 .info（或退回 .get_info()），失敗回傳空 dict。"""

    def _fetch() -> dict:
        try:
            info = tk.info
        except Exception:  # noqa: BLE001
            info = tk.get_info()
        return info or {}

    result = safe_call(_fetch, default={}, label="ticker.info")
    return result if isinstance(result, dict) else {}


def safe_fast_info(tk: "yf.Ticker") -> dict:
    """fast_info 較穩定（不需完整爬取），用於補股價等基本欄位。"""

    def _fetch() -> dict:
        fi = tk.fast_info
        try:
            return dict(fi)
        except Exception:  # noqa: BLE001
            # fast_info 可能是特殊物件，逐一嘗試常用鍵
            out = {}
            for key in ("last_price", "year_high", "year_low", "market_cap", "currency"):
                try:
                    out[key] = fi[key]
                except Exception:  # noqa: BLE001
                    pass
            return out

    result = safe_call(_fetch, default={}, label="ticker.fast_info")
    return result if isinstance(result, dict) else {}
