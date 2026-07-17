"""中文字型解析（供 Matplotlib 圖表與 WeasyPrint PDF 使用）。

優先序：
  1. 使用者放入 fonts/ 的 .ttf/.otf/.ttc（建議 NotoSansTC 或微軟正黑體）。
  2. 系統內建中文字型（macOS / Linux / Windows 常見路徑）。
  3. 皆無則下載 Noto Sans CJK TC。

Matplotlib 以字型檔路徑載入（FontProperties）；WeasyPrint 則優先用 fontconfig
依家族名稱解析系統字型，若有使用者字型檔則另以 @font-face 綁定（見 report 模組）。
"""
from __future__ import annotations

import logging
import platform
from pathlib import Path

from matplotlib.font_manager import FontProperties

from config import FONTS_DIR

logger = logging.getLogger(__name__)

_USER_REGULAR_HINTS = ["notosanstc-regular", "notosanscjk", "msjh", "notosanstc", "regular"]

_SYSTEM_CANDIDATES = [
    # macOS
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/Library/Fonts/Microsoft/msjh.ttf",
    # Linux
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    # Windows
    "C:/Windows/Fonts/msjh.ttc",
    "C:/Windows/Fonts/msyh.ttc",
]

_cached_path: str | None = None


def _find_user_font() -> str | None:
    files = [p for p in FONTS_DIR.glob("*") if p.suffix.lower() in (".ttf", ".otf", ".ttc")]
    if not files:
        return None
    for hint in _USER_REGULAR_HINTS:
        for f in files:
            if hint in f.name.lower():
                return str(f)
    return str(files[0])


def _find_system_font() -> str | None:
    for path in _SYSTEM_CANDIDATES:
        if Path(path).exists():
            return path
    return None


def resolve_font_path() -> str | None:
    """回傳可用的中文字型檔路徑；全部失敗回傳 None（圖表退回預設字型）。"""
    global _cached_path
    if _cached_path is not None:
        return _cached_path

    path = _find_user_font() or _find_system_font()
    if path:
        logger.info("使用中文字型: %s", path)
        _cached_path = path
        return path

    logger.info("找不到系統中文字型（平台 %s），嘗試下載 Noto Sans CJK TC", platform.system())
    try:
        from scripts.setup_fonts import download_noto_sans_tc

        paths = download_noto_sans_tc()
        if paths:
            _cached_path = str(paths[0])
            return _cached_path
    except Exception as exc:  # noqa: BLE001
        logger.warning("字型下載失敗: %s", exc)
    return None


def get_fontproperties() -> FontProperties | None:
    path = resolve_font_path()
    if path:
        try:
            return FontProperties(fname=path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("載入字型 FontProperties 失敗: %s", exc)
    return None


def user_font_file() -> str | None:
    """僅回傳『使用者提供』的字型檔（供 WeasyPrint @font-face 綁定），無則 None。"""
    return _find_user_font()
