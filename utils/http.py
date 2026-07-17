"""共用 HTTP 工具：統一 timeout、瀏覽器 User-Agent、含 retry 的安全 GET。"""
from __future__ import annotations

import logging
import time

import requests

from config import (
    HTTP_TIMEOUT_SECONDS,
    HTTP_USER_AGENT,
    RETRY_ATTEMPTS,
    RETRY_BACKOFF_SECONDS,
)

logger = logging.getLogger(__name__)

_DEFAULT_HEADERS = {
    "User-Agent": HTTP_USER_AGENT,
    "Accept-Language": "en-US,en;q=0.9,zh-TW;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def get_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(_DEFAULT_HEADERS)
    return session


def safe_get(
    session: requests.Session | None,
    url: str,
    *,
    attempts: int = RETRY_ATTEMPTS,
    **kwargs,
) -> requests.Response | None:
    """含 retry 的 GET；逾時 / 連線錯誤 / HTTP 錯誤最終一律回傳 None，不拋出例外。

    403 / 404 視為「該來源不可用」，不重試，直接回傳 None。
    """
    sess = session or get_session()
    kwargs.setdefault("timeout", HTTP_TIMEOUT_SECONDS)

    for attempt in range(1, attempts + 1):
        try:
            resp = sess.get(url, **kwargs)
            if resp.status_code in (403, 404, 451):
                logger.warning("GET %s 回應 %d（來源不可用，跳過）", url, resp.status_code)
                return None
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as exc:
            if attempt < attempts:
                wait = RETRY_BACKOFF_SECONDS * attempt
                logger.warning("GET %s 第 %d/%d 次失敗: %s（%.1fs 後重試）",
                               url, attempt, attempts, exc, wait)
                time.sleep(wait)
            else:
                logger.warning("GET %s 重試 %d 次後仍失敗: %s", url, attempts, exc)
    return None
