"""簡單的 retry 裝飾器 / 執行器：指數退避，最終失敗回傳預設值而非拋出。"""
from __future__ import annotations

import functools
import logging
import time
from typing import Any, Callable, TypeVar

from config import RETRY_ATTEMPTS, RETRY_BACKOFF_SECONDS

logger = logging.getLogger(__name__)

T = TypeVar("T")


def with_retry(
    attempts: int = RETRY_ATTEMPTS,
    backoff: float = RETRY_BACKOFF_SECONDS,
    default: Any = None,
    label: str = "",
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """裝飾器：對函式做多次重試，全部失敗後記錄警告並回傳 default（不拋出）。"""

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            name = label or func.__name__
            last_exc: Exception | None = None
            for attempt in range(1, attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:  # noqa: BLE001 - 有意攔截所有例外以維持穩定
                    last_exc = exc
                    if attempt < attempts:
                        wait = backoff * attempt
                        logger.warning(
                            "%s 第 %d/%d 次失敗: %s（%.1fs 後重試）",
                            name, attempt, attempts, exc, wait,
                        )
                        time.sleep(wait)
                    else:
                        logger.warning(
                            "%s 重試 %d 次後仍失敗: %s（回傳預設值）",
                            name, attempts, exc,
                        )
            return default

        return wrapper

    return decorator


def run_with_retry(
    func: Callable[[], T],
    *,
    attempts: int = RETRY_ATTEMPTS,
    backoff: float = RETRY_BACKOFF_SECONDS,
    default: T | None = None,
    label: str = "task",
) -> T | None:
    """以函式形式呼叫（適合 lambda）。用法：run_with_retry(lambda: fetch(), label='price')。"""
    wrapped = with_retry(attempts=attempts, backoff=backoff, default=default, label=label)(func)
    return wrapped()
