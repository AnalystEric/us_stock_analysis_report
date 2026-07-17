"""下載 Noto Sans CJK TC 字型（僅在找不到使用者 / 系統中文字型時才需要）。

可手動執行：python -m scripts.setup_fonts
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import requests

from config import FONTS_DIR, HTTP_USER_AGENT

logger = logging.getLogger(__name__)

_NOTO_BASE_URL = (
    "https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/OTF/TraditionalChinese/"
)
_FILES = {
    "NotoSansCJKtc-Regular.otf": "regular",
    "NotoSansCJKtc-Bold.otf": "bold",
}
_MIN_EXPECTED_BYTES = 1_000_000  # 正常約 16MB，遠小於此視為下載失敗 / 被攔截頁面


def download_noto_sans_tc() -> tuple[Path, Path] | None:
    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    result: dict[str, Path] = {}

    for filename, weight in _FILES.items():
        dest = FONTS_DIR / filename
        if dest.exists() and dest.stat().st_size > _MIN_EXPECTED_BYTES:
            result[weight] = dest
            continue

        url = _NOTO_BASE_URL + filename
        logger.info("下載字型 %s ...", filename)
        try:
            resp = requests.get(
                url, headers={"User-Agent": HTTP_USER_AGENT}, timeout=60, stream=True
            )
            resp.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1 << 16):
                    f.write(chunk)
        except requests.exceptions.RequestException as exc:
            logger.error("下載字型 %s 失敗: %s", filename, exc)
            return None

        if dest.stat().st_size <= _MIN_EXPECTED_BYTES:
            logger.error("字型 %s 下載內容異常（檔案過小）", filename)
            return None
        result[weight] = dest

    return result["regular"], result["bold"]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    paths = download_noto_sans_tc()
    if paths is None:
        print("字型下載失敗，請檢查網路連線，或手動放入字型至 fonts/")
        sys.exit(1)
    print("字型已就緒:", paths)
