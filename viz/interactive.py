"""網頁用互動式圖表（Plotly）：可縮放、平移、滑鼠懸停看數值。

僅供 Streamlit 前端使用；PDF 報告仍使用 viz/charts.py 的高解析靜態圖（利於列印）。
每個函式回傳 plotly Figure；資料不足回傳 None。配色與整體商務主題一致。
"""
from __future__ import annotations

import logging

from core.models import FinancialsData, PeerComparison, PriceData, ScoreCard, ValuationMultiples
from viz import style

logger = logging.getLogger(__name__)

_FONT = "Noto Sans TC, PingFang TC, Microsoft JhengHei, Heiti TC, sans-serif"


def _base(fig, title: str, height: int = 430, unified: bool = True):
    fig.update_layout(
        title=dict(text=title, font=dict(size=17, color=style.NAVY)),
        template="plotly_white",
        font=dict(family=_FONT, size=13, color=style.TEXT),
        margin=dict(l=55, r=30, t=110, b=45),
        height=height,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        hovermode="x unified" if unified else "closest",
        colorway=[style.NAVY, style.STEEL, style.AMBER, style.TEAL, style.LIGHT_BLUE],
        plot_bgcolor="white",
        paper_bgcolor="white",
    )
    fig.update_xaxes(showgrid=True, gridcolor=style.GRID)
    fig.update_yaxes(showgrid=True, gridcolor=style.GRID)
    return fig


def price_fig(ticker: str, price: PriceData):
    df = price.price_df
    if df is None or getattr(df, "empty", True) or "Close" not in df.columns:
        return None
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except ImportError:
        return None

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        row_heights=[0.72, 0.28], vertical_spacing=0.04)
    if all(c in df.columns for c in ("Open", "High", "Low")):
        fig.add_trace(go.Candlestick(
            x=df.index, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
            name="K 線", increasing_line_color=style.GREEN, decreasing_line_color=style.RED,
            showlegend=False), row=1, col=1)
    else:
        fig.add_trace(go.Scatter(x=df.index, y=df["Close"], name="收盤價",
                                 line=dict(color=style.NAVY)), row=1, col=1)
    if "MA50" in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df["MA50"], name="50 日均線",
                                 line=dict(color=style.AMBER, width=1.3)), row=1, col=1)
    if "MA200" in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df["MA200"], name="200 日均線",
                                 line=dict(color=style.TEAL, width=1.3)), row=1, col=1)
    if "Volume" in df.columns:
        fig.add_trace(go.Bar(x=df.index, y=df["Volume"], name="成交量",
                             marker_color=style.LIGHT_BLUE, showlegend=False), row=2, col=1)

    _base(fig, f"{ticker} 近一年股價 K 線（含 50/200 日均線）", height=520, unified=False)
    fig.update_layout(xaxis_rangeslider_visible=False, hovermode="x")
    fig.update_yaxes(title_text="股價 (USD)", row=1, col=1)
    fig.update_yaxes(title_text="成交量", row=2, col=1)
    return fig


def revenue_yoy_fig(ticker: str, fin: FinancialsData):
    qs = [q for q in fin.quarters if q.revenue is not None]
    if len(qs) < 2:
        return None
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except ImportError:
        return None

    periods = [q.period for q in qs]
    revenue = [q.revenue for q in qs]
    yoy = [(q.revenue_yoy * 100 if q.revenue_yoy is not None else None) for q in qs]

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=periods, y=revenue, name="營收", marker_color=style.STEEL,
                         hovertemplate="%{x}<br>營收 %{y:$,.0f}<extra></extra>"), secondary_y=False)
    fig.add_trace(go.Scatter(x=periods, y=yoy, name="YoY %", mode="lines+markers",
                             line=dict(color=style.AMBER, width=2),
                             hovertemplate="%{x}<br>YoY %{y:.1f}%<extra></extra>"), secondary_y=True)
    _base(fig, f"{ticker} 季度營收與年增率 (YoY)")
    fig.update_yaxes(title_text="營收 (USD)", secondary_y=False)
    fig.update_yaxes(title_text="YoY (%)", secondary_y=True, showgrid=False)
    return fig


def margins_fig(ticker: str, fin: FinancialsData):
    qs = fin.quarters
    gm = [(q.gross_margin * 100 if q.gross_margin is not None else None) for q in qs]
    fcf = [(q.fcf_margin * 100 if q.fcf_margin is not None else None) for q in qs]
    if not any(v is not None for v in gm) and not any(v is not None for v in fcf):
        return None
    try:
        import plotly.graph_objects as go
    except ImportError:
        return None

    periods = [q.period for q in qs]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=periods, y=gm, name="毛利率", mode="lines+markers",
                             line=dict(color=style.NAVY, width=2),
                             hovertemplate="%{x}<br>毛利率 %{y:.1f}%<extra></extra>"))
    fig.add_trace(go.Scatter(x=periods, y=fcf, name="FCF 利潤率", mode="lines+markers",
                             line=dict(color=style.TEAL, width=2),
                             hovertemplate="%{x}<br>FCF 利潤率 %{y:.1f}%<extra></extra>"))
    _base(fig, f"{ticker} 季度利潤率趨勢")
    fig.update_yaxes(title_text="百分比 (%)", ticksuffix="%")
    return fig


def eps_fig(ticker: str, fin: FinancialsData):
    qs = [q for q in fin.quarters if q.eps_actual is not None or q.eps_estimate is not None]
    if len(qs) < 2:
        return None
    try:
        import plotly.graph_objects as go
    except ImportError:
        return None

    periods = [q.period for q in qs]
    est = [q.eps_estimate for q in qs]
    actual = [q.eps_actual for q in qs]
    colors = [style.GREEN if q.beat_miss == "Beat" else (style.RED if q.beat_miss == "Miss" else style.NAVY)
              for q in qs]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=periods, y=est, name="市場預估", marker_color=style.LIGHT_BLUE,
                         hovertemplate="%{x}<br>預估 EPS %{y:.2f}<extra></extra>"))
    fig.add_trace(go.Bar(x=periods, y=actual, name="實際 (綠=Beat/紅=Miss)",
                         marker_color=colors,
                         hovertemplate="%{x}<br>實際 EPS %{y:.2f}<extra></extra>"))
    _base(fig, f"{ticker} 季度 EPS：實際 vs 市場預估 (Beat/Miss)", unified=False)
    fig.update_layout(barmode="group", hovermode="closest")
    fig.update_yaxes(title_text="EPS (USD)")
    return fig


def pe_fig(ticker: str, val: ValuationMultiples):
    s = val.pe_series
    if s is None or getattr(s, "empty", True):
        return None
    try:
        import plotly.graph_objects as go
    except ImportError:
        return None
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=list(s.index), y=list(s.values), name="近似 P/E",
                             line=dict(color=style.NAVY, width=1.8),
                             hovertemplate="%{x|%Y-%m}<br>P/E %{y:.1f}<extra></extra>"))
    if val.pe_mean_3y:
        fig.add_hline(y=val.pe_mean_3y, line=dict(color=style.AMBER, dash="dash"),
                      annotation_text=f"3 年均值 {val.pe_mean_3y:.1f}", annotation_position="top left")
    _base(fig, f"{ticker} 近 3 年近似本益比 (P/E) 趨勢", unified=False)
    fig.update_layout(hovermode="x")
    fig.update_yaxes(title_text="P/E")
    return fig


def peers_fig(ticker: str, peers: PeerComparison):
    rows = [r for r in peers.rows if r.gross_margin is not None or r.profit_margin is not None]
    if len(rows) < 2:
        return None
    try:
        import plotly.graph_objects as go
    except ImportError:
        return None
    labels = [r.ticker for r in rows]
    gross = [(r.gross_margin or 0) * 100 for r in rows]
    profit = [(r.profit_margin or 0) * 100 for r in rows]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=labels, y=gross, name="毛利率", marker_color=style.NAVY,
                         hovertemplate="%{x}<br>毛利率 %{y:.1f}%<extra></extra>"))
    fig.add_trace(go.Bar(x=labels, y=profit, name="淨利率", marker_color=style.LIGHT_BLUE,
                         hovertemplate="%{x}<br>淨利率 %{y:.1f}%<extra></extra>"))
    _base(fig, f"{ticker} 與同業 毛利率 / 淨利率比較", unified=False)
    fig.update_layout(barmode="group", hovermode="closest")
    fig.update_yaxes(title_text="百分比 (%)", ticksuffix="%")
    return fig


def radar_fig(ticker: str, card: ScoreCard):
    dims = card.dimensions
    if not dims or card.overall is None:
        return None
    try:
        import plotly.graph_objects as go
    except ImportError:
        return None
    labels = [d.name.split(" ")[0] for d in dims]
    values = [d.score if d.score is not None else 0 for d in dims]
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=values + values[:1], theta=labels + labels[:1], fill="toself",
        line=dict(color=style.NAVY, width=2), fillcolor="rgba(74,123,167,0.30)",
        name="評分", hovertemplate="%{theta}：%{r:.0f}<extra></extra>"))
    fig.update_layout(
        title=dict(text=f"{ticker} 綜合體質評分（總分 {card.overall:.0f} · {card.verdict}）",
                   font=dict(size=16, color=style.NAVY)),
        template="plotly_white",
        font=dict(family=_FONT, size=13, color=style.TEXT),
        polar=dict(radialaxis=dict(range=[0, 100], tickvals=[20, 40, 60, 80], gridcolor=style.GRID),
                   angularaxis=dict(gridcolor=style.GRID)),
        showlegend=False, height=420, margin=dict(l=60, r=60, t=80, b=40),
        paper_bgcolor="white",
    )
    return fig
