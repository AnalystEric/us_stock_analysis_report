"""在 import weasyprint 之前，確保能找到系統原生庫（pango / gobject / cairo）。

WeasyPrint 依賴 libgobject / libpango / libcairo 等原生庫。macOS 上這些由 Homebrew
安裝於 /opt/homebrew/lib（Apple Silicon）或 /usr/local/lib（Intel），但 Python 的
ctypes.dlopen 預設不會搜尋這些路徑。此模組在程式內把該路徑加入
DYLD_FALLBACK_LIBRARY_PATH，讓使用者不必每次手動 export。

用法：任何會 import weasyprint 的模組，務必先 `import bootstrap_libs`（或呼叫
ensure_native_libs()），再 import weasyprint。
"""
from __future__ import annotations

import os
import platform
from pathlib import Path

_DONE = False

# macOS 常見的 Homebrew lib 路徑
_MAC_LIB_DIRS = ["/opt/homebrew/lib", "/usr/local/lib"]


def ensure_native_libs() -> None:
    global _DONE
    if _DONE:
        return
    _DONE = True

    if platform.system() != "Darwin":
        return  # Linux/Windows 由套件管理器處理，通常可直接找到

    existing = os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")
    parts = [p for p in existing.split(os.pathsep) if p]
    for lib_dir in _MAC_LIB_DIRS:
        if Path(lib_dir).is_dir() and lib_dir not in parts:
            parts.append(lib_dir)
    # macOS 預設 fallback 也包含 ~/lib:/usr/local/lib:/usr/lib
    if parts:
        os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = os.pathsep.join(parts)


# import 即生效
ensure_native_libs()
