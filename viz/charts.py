"""報告圖表生成（300 DPI，暫存於 temp_images/）。回傳 PNG 路徑；失敗回傳 ''。

圖表清單：
  1. revenue_segments  近 4 年度營收結構長條圖
  2. revenue_yoy       近 8 季營收(長條) + YoY(折線) 雙軸圖
  3. margins           近 8 季毛利率 + FCF 利潤率折線圖
  4. eps               近 8 季實際 vs 預估 EPS 對比（Beat/Miss 上色）
  5. price_candle      近 1 年 K 線 + 50/200MA + 成交量
  6. pe_trend          近 3 年近似 P/E 趨勢
  7. peers             同業毛利率 / 淨利率比較
"""
from __future__ import annotations

import logging
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

from config import CHART_DPI, TEMP_IMAGES_DIR
from core.models import FinancialsData, PeerComparison, PriceData, RevenueSegments, ValuationMultiples
from viz import style

logger = logging.getLogger(__name__)

# 統一圖表尺寸（英吋），確保各圖比例一致、預覽與 PDF 皆整齊
FIG_W = 8.0          # 一致寬度
FIG_H = 4.0          # 一般圖表高度（長寬比 2:1）
FIG_H_PRICE = 4.8    # K 線圖較高（含成交量子圖）


def _out(name: str) -> Path:
    TEMP_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    return TEMP_IMAGES_DIR / name


def _save(fig, path: Path) -> str:
    try:
        fig.savefig(path, dpi=CHART_DPI, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        return str(path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("儲存圖表失敗 %s: %s", path, exc)
        plt.close(fig)
        return ""


def _millions(v, _pos=None):
    if abs(v) >= 1e12:
        return f"{v/1e12:.1f}T"
    if abs(v) >= 1e9:
        return f"{v/1e9:.0f}B"
    if abs(v) >= 1e6:
        return f"{v/1e6:.0f}M"
    return f"{v:.0f}"


def revenue_segments_chart(ticker: str, seg: RevenueSegments) -> str:
    if not seg.values or len(seg.values) < 2:
        return ""
    style.apply_style()
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
    bars = ax.bar(seg.labels, seg.values, color=style.SERIES[: len(seg.values)], width=0.6)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(_millions))
    style.apply_cjk(ax, title=f"{ticker} 年度營收規模", ylabel="營收 (USD)")
    for b, v in zip(bars, seg.values):
        ax.annotate(_millions(v), (b.get_x() + b.get_width() / 2, v),
                    ha="center", va="bottom", fontsize=8, color=style.TEXT)
    ax.margins(y=0.15)
    return _save(fig, _out(f"{ticker}_segments.png"))


def revenue_yoy_chart(ticker: str, fin: FinancialsData) -> str:
    quarters = [q for q in fin.quarters if q.revenue is not None]
    if len(quarters) < 2:
        return ""
    style.apply_style()
    periods = [q.period for q in quarters]
    revenue = [q.revenue for q in quarters]
    yoy = [q.revenue_yoy * 100 if q.revenue_yoy is not None else None for q in quarters]

    fig, ax1 = plt.subplots(figsize=(FIG_W, FIG_H))
    x = np.arange(len(periods))
    ax1.bar(x, revenue, color=style.STEEL, width=0.6, label="營收")
    ax1.yaxis.set_major_formatter(mticker.FuncFormatter(_millions))
    ax1.set_xticks(x)
    ax1.set_xticklabels(periods, rotation=30, ha="right")
    style.apply_cjk(ax1, title=f"{ticker} 季度營收與年增率 (YoY)", ylabel="營收 (USD)")

    ax2 = ax1.twinx()
    xs = [i for i, v in enumerate(yoy) if v is not None]
    ys = [v for v in yoy if v is not None]
    if xs:
        ax2.plot(xs, ys, color=style.AMBER, marker="o", linewidth=1.8, label="YoY %")
        for xi, yi in zip(xs, ys):
            ax2.annotate(f"{yi:.0f}%", (xi, yi), textcoords="offset points",
                         xytext=(0, 8), ha="center", fontsize=8, color=style.AMBER)
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.1f}%"))
    ax2.yaxis.set_major_locator(mticker.MaxNLocator(nbins=5))
    ax2.set_ylabel("YoY (%)", fontproperties=style.fp())
    ax2.grid(False)

    # 合併圖例
    lines = [plt.Rectangle((0, 0), 1, 1, color=style.STEEL),
             plt.Line2D([0], [0], color=style.AMBER, marker="o")]
    ax1.legend(lines, ["營收", "YoY %"], prop=style.fp(), loc="upper left")
    return _save(fig, _out(f"{ticker}_revenue_yoy.png"))


def margins_chart(ticker: str, fin: FinancialsData) -> str:
    quarters = fin.quarters
    gm = [q.gross_margin * 100 if q.gross_margin is not None else None for q in quarters]
    fcf = [q.fcf_margin * 100 if q.fcf_margin is not None else None for q in quarters]
    if not any(v is not None for v in gm) and not any(v is not None for v in fcf):
        return ""
    style.apply_style()
    periods = [q.period for q in quarters]
    x = np.arange(len(periods))
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))

    def _plot(vals, color, label):
        xs = [i for i, v in enumerate(vals) if v is not None]
        ys = [v for v in vals if v is not None]
        if xs:
            ax.plot(xs, ys, color=color, marker="o", linewidth=1.8, label=label)

    _plot(gm, style.NAVY, "毛利率 (Gross Margin)")
    _plot(fcf, style.TEAL, "FCF 利潤率 (FCF Margin)")
    ax.set_xticks(x)
    ax.set_xticklabels(periods, rotation=30, ha="right")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))
    ax.axhline(0, color=style.MUTED, linewidth=0.6)
    style.apply_cjk(ax, title=f"{ticker} 季度利潤率趨勢", ylabel="百分比 (%)")
    style.legend_cjk(ax, loc="best")
    return _save(fig, _out(f"{ticker}_margins.png"))


def eps_chart(ticker: str, fin: FinancialsData) -> str:
    quarters = [q for q in fin.quarters if q.eps_actual is not None or q.eps_estimate is not None]
    if len(quarters) < 2:
        return ""
    style.apply_style()
    periods = [q.period for q in quarters]
    actual = [q.eps_actual for q in quarters]
    est = [q.eps_estimate for q in quarters]
    x = np.arange(len(periods))
    w = 0.38
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))

    est_vals = [e if e is not None else 0 for e in est]
    ax.bar(x - w / 2, est_vals, w, color=style.LIGHT_BLUE, label="市場預估 EPS")

    # 實際：Beat 綠、Miss 紅、其他 navy
    colors = []
    for q in quarters:
        if q.beat_miss == "Beat":
            colors.append(style.GREEN)
        elif q.beat_miss == "Miss":
            colors.append(style.RED)
        else:
            colors.append(style.NAVY)
    act_vals = [a if a is not None else 0 for a in actual]
    ax.bar(x + w / 2, act_vals, w, color=colors, label="實際 EPS")

    ax.set_xticks(x)
    ax.set_xticklabels(periods, rotation=30, ha="right")
    style.apply_cjk(ax, title=f"{ticker} 季度 EPS：實際 vs 市場預估", ylabel="EPS (USD)")
    # 圖例（含 Beat/Miss 說明）
    handles = [
        plt.Rectangle((0, 0), 1, 1, color=style.LIGHT_BLUE),
        plt.Rectangle((0, 0), 1, 1, color=style.GREEN),
        plt.Rectangle((0, 0), 1, 1, color=style.RED),
    ]
    ax.legend(handles, ["市場預估", "實際 (Beat)", "實際 (Miss)"], prop=style.fp(), loc="best")
    return _save(fig, _out(f"{ticker}_eps.png"))


def price_candle_chart(ticker: str, price: PriceData) -> str:
    df = price.price_df
    if df is None or getattr(df, "empty", True):
        return ""
    try:
        import mplfinance as mpf
    except ImportError:
        return _price_line_fallback(ticker, price)

    style.apply_style()
    need = ["Open", "High", "Low", "Close", "Volume"]
    if not all(c in df.columns for c in need):
        return _price_line_fallback(ticker, price)

    path = _out(f"{ticker}_price.png")
    try:
        addplots = []
        if "MA50" in df.columns:
            addplots.append(mpf.make_addplot(df["MA50"], color=style.AMBER, width=1.0))
        if "MA200" in df.columns:
            addplots.append(mpf.make_addplot(df["MA200"], color=style.TEAL, width=1.0))

        mc = mpf.make_marketcolors(up=style.GREEN, down=style.RED, edge="inherit",
                                   wick="inherit", volume=style.LIGHT_BLUE)
        s = mpf.make_mpf_style(base_mpf_style="classic", marketcolors=mc,
                               facecolor="white", edgecolor=style.MUTED,
                               gridcolor=style.GRID, figcolor="white")
        fig, axes = mpf.plot(
            df, type="candle", style=s, addplot=addplots or None,
            volume=True, returnfig=True, figsize=(FIG_W, FIG_H_PRICE),
            warn_too_much_data=10000,
        )
        font = style.fp()
        title = f"{ticker} 近一年股價 K 線（含 50/200 日均線）"
        if font is not None:
            fig.suptitle(title, fontproperties=font, fontsize=13, fontweight="bold")
        else:
            fig.suptitle(title, fontsize=13, fontweight="bold")
        fig.savefig(path, dpi=CHART_DPI, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        return str(path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("K 線圖繪製失敗，改用折線圖: %s", exc)
        plt.close("all")
        return _price_line_fallback(ticker, price)


def _price_line_fallback(ticker: str, price: PriceData) -> str:
    df = price.price_df
    if df is None or getattr(df, "empty", True) or "Close" not in df.columns:
        return ""
    style.apply_style()
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(FIG_W, FIG_H_PRICE), sharex=True,
                                   gridspec_kw={"height_ratios": [3, 1], "hspace": 0.08})
    ax1.plot(df.index, df["Close"], color=style.NAVY, linewidth=1.4, label="收盤價")
    if "MA50" in df:
        ax1.plot(df.index, df["MA50"], color=style.AMBER, linewidth=1.0, label="50 日均線")
    if "MA200" in df:
        ax1.plot(df.index, df["MA200"], color=style.TEAL, linewidth=1.0, label="200 日均線")
    style.apply_cjk(ax1, title=f"{ticker} 近一年股價走勢", ylabel="股價 (USD)")
    style.legend_cjk(ax1, loc="best")
    if "Volume" in df:
        ax2.bar(df.index, df["Volume"], color=style.LIGHT_BLUE, width=1.0)
        ax2.yaxis.set_major_formatter(mticker.FuncFormatter(_millions))
        style.apply_cjk(ax2, ylabel="成交量")
    return _save(fig, _out(f"{ticker}_price.png"))


def pe_trend_chart(ticker: str, val: ValuationMultiples) -> str:
    series = val.pe_series
    if series is None or getattr(series, "empty", True):
        return ""
    style.apply_style()
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
    ax.plot(series.index, series.values, color=style.NAVY, linewidth=1.4, label="近似 P/E")
    if val.pe_mean_3y:
        ax.axhline(val.pe_mean_3y, color=style.AMBER, linestyle="--", linewidth=1.0,
                   label=f"3 年均值 {val.pe_mean_3y:.1f}")

    # 日期軸：限制刻度數量與格式，避免標籤重疊跑版
    try:
        ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=8))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        ax.set_xmargin(0.02)
    except Exception:  # noqa: BLE001 - 非日期索引時退回預設
        pass

    style.apply_cjk(ax, title=f"{ticker} 近 3 年近似本益比 (P/E) 趨勢", ylabel="P/E")
    # 旋轉需在套用字型之後，確保旋轉不被覆寫
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right", rotation_mode="anchor")
    style.legend_cjk(ax, loc="best")
    fig.subplots_adjust(bottom=0.22)
    return _save(fig, _out(f"{ticker}_pe.png"))


def peers_chart(ticker: str, peers: PeerComparison) -> str:
    rows = [r for r in peers.rows
            if r.gross_margin is not None or r.profit_margin is not None]
    if len(rows) < 2:
        return ""
    style.apply_style()
    labels = [r.ticker for r in rows]
    gross = [(r.gross_margin or 0) * 100 for r in rows]
    profit = [(r.profit_margin or 0) * 100 for r in rows]
    x = np.arange(len(labels))
    w = 0.38
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
    ax.bar(x - w / 2, gross, w, color=style.NAVY, label="毛利率")
    ax.bar(x + w / 2, profit, w, color=style.LIGHT_BLUE, label="淨利率")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))
    ax.axhline(0, color=style.MUTED, linewidth=0.6)
    style.apply_cjk(ax, title=f"{ticker} 與同業 毛利率 / 淨利率比較", ylabel="百分比 (%)")
    style.legend_cjk(ax, loc="best")
    return _save(fig, _out(f"{ticker}_peers.png"))
