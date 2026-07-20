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
from core.models import (
    FinancialsData,
    InstitutionalFlow,
    MonthlyRevenue,
    PeerComparison,
    PriceData,
    RevenueSegments,
    ScoreCard,
    ValuationMultiples,
)
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


def _yi(v, _pos=None):
    """台股金額（元）→ 億 / 兆 標示。"""
    if abs(v) >= 1e12:
        return f"{v/1e12:.2f}兆"
    if abs(v) >= 1e8:
        return f"{v/1e8:.0f}億"
    if abs(v) >= 1e4:
        return f"{v/1e4:.0f}萬"
    return f"{v:.0f}"


# 貨幣模式（由 pdf_builder 於產圖前設定）：影響營收類圖表的單位與軸標題
_CUR_MODE = "US"


def set_currency(market: str) -> None:
    global _CUR_MODE
    _CUR_MODE = "TW" if market in ("TWSE", "TPEX") else "US"


def _rev_fmt():
    """依市場回傳（金額格式化函式, 軸標題）。"""
    if _CUR_MODE == "TW":
        return _yi, "營收 (NT$)"
    return _millions, "營收 (USD)"


def scorecard_radar(ticker: str, card: ScoreCard) -> str:
    """五維綜合體質評分雷達圖。"""
    dims = card.dimensions
    if not dims or card.overall is None:
        return ""
    style.apply_style()
    font = style.fp()

    labels = [d.name.split(" ")[0] for d in dims]         # 取中文名（如「價值」）
    values = [d.score if d.score is not None else 0 for d in dims]
    N = len(dims)
    angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
    v_closed = values + values[:1]
    a_closed = angles + angles[:1]

    fig, ax = plt.subplots(figsize=(6.4, 6.4), subplot_kw=dict(polar=True))
    ax.set_facecolor("white")
    ax.plot(a_closed, v_closed, color=style.NAVY, linewidth=2.2)
    ax.fill(a_closed, v_closed, color=style.STEEL, alpha=0.28)

    ax.set_xticks(angles)
    ax.set_xticklabels(labels)
    for lbl in ax.get_xticklabels():
        if font is not None:
            lbl.set_fontproperties(font)
        lbl.set_fontsize(12)
    ax.set_ylim(0, 100)
    ax.set_yticks([20, 40, 60, 80])
    ax.set_yticklabels(["20", "40", "60", "80"], color=style.MUTED, fontsize=8)
    ax.set_rlabel_position(18)
    ax.grid(color=style.GRID, linewidth=0.8)

    for a, v in zip(angles, values):
        ax.text(a, min(v + 8, 104), f"{v:.0f}", ha="center", va="center",
                color=style.NAVY, fontsize=11, fontweight="bold",
                fontproperties=font)

    title = f"{ticker} 綜合體質評分（總分 {card.overall:.0f} · {card.verdict}）"
    ax.set_title(title, fontproperties=font, fontsize=13, fontweight="bold", pad=24, color=style.NAVY)
    fig.subplots_adjust(top=0.85, bottom=0.08)
    return _save(fig, _out(f"{ticker}_scorecard.png"))


def revenue_segments_chart(ticker: str, seg: RevenueSegments) -> str:
    if not seg.values or len(seg.values) < 2:
        return ""
    style.apply_style()
    mfmt, ylabel = _rev_fmt()
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
    bars = ax.bar(seg.labels, seg.values, color=style.SERIES[: len(seg.values)], width=0.6)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(mfmt))
    style.apply_cjk(ax, title=f"{ticker} 年度營收規模", ylabel=ylabel)
    for b, v in zip(bars, seg.values):
        ax.annotate(mfmt(v), (b.get_x() + b.get_width() / 2, v),
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

    mfmt, ylabel = _rev_fmt()
    fig, ax1 = plt.subplots(figsize=(FIG_W, FIG_H))
    x = np.arange(len(periods))
    ax1.bar(x, revenue, color=style.STEEL, width=0.6, label="營收")
    ax1.yaxis.set_major_formatter(mticker.FuncFormatter(mfmt))
    ax1.set_xticks(x)
    ax1.set_xticklabels(periods, rotation=30, ha="right")
    style.apply_cjk(ax1, title=f"{ticker} 季度營收與年增率 (YoY)", ylabel=ylabel)

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

    # 合併圖例（置於圖表下方，避免覆蓋長條 / 折線）
    lines = [plt.Rectangle((0, 0), 1, 1, color=style.STEEL),
             plt.Line2D([0], [0], color=style.AMBER, marker="o")]
    style.legend_below(ax1, handles=lines, labels=["營收", "YoY %"], ncol=2)
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
    style.legend_below(ax, ncol=2)
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
    style.apply_cjk(ax, title=f"{ticker} 季度 EPS：實際 vs 市場預估",
                    ylabel="EPS (元)" if _CUR_MODE == "TW" else "EPS (USD)")
    # 圖例（含 Beat/Miss 說明）
    handles = [
        plt.Rectangle((0, 0), 1, 1, color=style.LIGHT_BLUE),
        plt.Rectangle((0, 0), 1, 1, color=style.GREEN),
        plt.Rectangle((0, 0), 1, 1, color=style.RED),
    ]
    style.legend_below(ax, handles=handles, labels=["市場預估", "實際 (Beat)", "實際 (Miss)"], ncol=3)
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

        # 均線圖例（置於整張圖下方，不覆蓋 K 線與成交量）
        ma_handles, ma_labels = [], []
        if "MA50" in df.columns:
            ma_handles.append(plt.Line2D([0], [0], color=style.AMBER, lw=1.4))
            ma_labels.append("50 日均線")
        if "MA200" in df.columns:
            ma_handles.append(plt.Line2D([0], [0], color=style.TEAL, lw=1.4))
            ma_labels.append("200 日均線")
        if ma_handles:
            fig.legend(ma_handles, ma_labels, loc="upper center",
                       ncol=len(ma_handles), frameon=False, prop=font,
                       bbox_to_anchor=(0.5, 0.02))

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
    _h, _l = ax1.get_legend_handles_labels()
    fig.legend(_h, _l, loc="upper center", ncol=3, frameon=False, prop=style.fp(),
               bbox_to_anchor=(0.5, 0.02))
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
    style.legend_below(ax, ncol=2)
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
    style.legend_below(ax, ncol=2)
    return _save(fig, _out(f"{ticker}_peers.png"))


# ---------------------------------------------------------------------------
# 台股專屬圖表
# ---------------------------------------------------------------------------
def monthly_revenue_chart(ticker: str, mr: MonthlyRevenue) -> str:
    """近 ~15 個月月營收（長條，單位億）+ 年增率 YoY（折線）雙軸圖。"""
    pts = [p for p in mr.points if p.revenue is not None]
    if len(pts) < 2:
        return ""
    style.apply_style()
    periods = [p.period[2:] for p in pts]          # '2026-06' → '26-06'
    revenue = [p.revenue for p in pts]
    yoy = [p.yoy * 100 if p.yoy is not None else None for p in pts]

    fig, ax1 = plt.subplots(figsize=(FIG_W, FIG_H))
    x = np.arange(len(periods))
    ax1.bar(x, revenue, color=style.STEEL, width=0.62, label="月營收")
    ax1.yaxis.set_major_formatter(mticker.FuncFormatter(_yi))
    ax1.set_xticks(x)
    ax1.set_xticklabels(periods, rotation=45, ha="right", fontsize=7)
    style.apply_cjk(ax1, title=f"{ticker} 月營收與年增率 (YoY)", ylabel="月營收 (NT$)")

    ax2 = ax1.twinx()
    xs = [i for i, v in enumerate(yoy) if v is not None]
    ys = [v for v in yoy if v is not None]
    if xs:
        ax2.plot(xs, ys, color=style.AMBER, marker="o", linewidth=1.8, label="YoY %")
        ax2.axhline(0, color=style.MUTED, linewidth=0.6, linestyle="--")
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))
    ax2.yaxis.set_major_locator(mticker.MaxNLocator(nbins=5))
    ax2.set_ylabel("YoY (%)", fontproperties=style.fp())
    ax2.grid(False)

    lines = [plt.Rectangle((0, 0), 1, 1, color=style.STEEL),
             plt.Line2D([0], [0], color=style.AMBER, marker="o")]
    style.legend_below(ax1, handles=lines, labels=["月營收", "YoY %"], ncol=2)
    return _save(fig, _out(f"{ticker}_monthly_revenue.png"))


def institutional_chart(ticker: str, inst: InstitutionalFlow) -> str:
    """近 ~20 交易日三大法人單日買賣超（張）分組長條 + 外資累計折線。"""
    days = [d for d in inst.days if any(v is not None for v in (d.foreign, d.trust, d.dealer))]
    if len(days) < 2:
        return ""
    style.apply_style()
    labels = [d.date[5:] for d in days]            # 'MM-DD'
    to_lots = lambda v: (v or 0) / 1000            # 股 → 張
    foreign = [to_lots(d.foreign) for d in days]
    trust = [to_lots(d.trust) for d in days]
    dealer = [to_lots(d.dealer) for d in days]
    x = np.arange(len(labels))
    w = 0.27

    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
    ax.bar(x - w, foreign, w, color=style.NAVY, label="外資")
    ax.bar(x, trust, w, color=style.AMBER, label="投信")
    ax.bar(x + w, dealer, w, color=style.TEAL, label="自營商")
    ax.axhline(0, color=style.MUTED, linewidth=0.7)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=7)
    style.apply_cjk(ax, title=f"{ticker} 三大法人單日買賣超（張）", ylabel="買賣超 (張)")
    style.legend_below(ax, ncol=3)
    return _save(fig, _out(f"{ticker}_institutional.png"))
