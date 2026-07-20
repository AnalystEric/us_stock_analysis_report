"""統一的商務風格 Matplotlib 主題（白底、專業配色），並提供 CJK 字型套用。"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from viz import fonts  # noqa: E402

# 商務配色
NAVY = "#1F3A5F"
STEEL = "#4A7BA7"
LIGHT_BLUE = "#A9C0D6"
AMBER = "#D97706"
TEAL = "#2C7A7B"
GREEN = "#15803D"
RED = "#B91C1C"
GRID = "#E5E7EB"
TEXT = "#111827"
MUTED = "#6B7280"

SERIES = [NAVY, STEEL, AMBER, TEAL, LIGHT_BLUE]


def apply_style() -> None:
    plt.rcParams.update({
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "savefig.facecolor": "white",
        "axes.edgecolor": MUTED,
        "axes.linewidth": 0.8,
        "axes.grid": True,
        "axes.axisbelow": True,
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "axes.labelcolor": TEXT,
        "xtick.color": TEXT,
        "ytick.color": TEXT,
        "text.color": TEXT,
        "axes.titlesize": 13,
        "axes.titleweight": "bold",
        "axes.labelsize": 10,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "legend.fontsize": 9,
        "legend.frameon": False,
        "figure.autolayout": False,
    })


def fp():
    """回傳 CJK FontProperties（可能為 None）。"""
    return fonts.get_fontproperties()


def apply_cjk(ax, title: str | None = None, xlabel: str | None = None, ylabel: str | None = None):
    """對座標軸標題與標籤套用中文字型。"""
    font = fp()
    if title is not None:
        ax.set_title(title, fontproperties=font, color=TEXT)
    if xlabel is not None:
        ax.set_xlabel(xlabel, fontproperties=font)
    if ylabel is not None:
        ax.set_ylabel(ylabel, fontproperties=font)
    if font is not None:
        for lbl in ax.get_xticklabels() + ax.get_yticklabels():
            lbl.set_fontproperties(font)
    return font


def legend_cjk(ax, **kwargs):
    font = fp()
    leg = ax.legend(prop=font, **kwargs)
    return leg


def legend_below(ax, handles=None, labels=None, ncol=2):
    """將圖例統一置於圖表『下方外側』，永遠不會覆蓋資料。

    搭配 savefig(bbox_inches="tight") 會自動把圖例納入輸出、不被裁切。
    """
    font = fp()
    kw = dict(prop=font, loc="upper center", bbox_to_anchor=(0.5, -0.28),
              ncol=ncol, frameon=False, borderaxespad=0.0, columnspacing=1.6,
              handlelength=1.8)
    if handles is not None:
        return ax.legend(handles, labels, **kw)
    return ax.legend(**kw)
