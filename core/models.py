"""跨模組共用的資料結構（投行等級深度報告版）。

所有欄位皆可為空 / 帶預設；任一資料源失敗只讓對應欄位留白，不影響整份報告。
DataFrame / Series 以 object 型別標註以避免在型別註記層強制相依 pandas。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


# ---------------------------------------------------------------------------
# 個股基本資訊
# ---------------------------------------------------------------------------
@dataclass
class CompanyProfile:
    ticker: str
    company_name: str = ""
    exchange: str = ""
    exchange_name: str = ""
    sector: str = ""
    industry: str = ""
    market_cap: float | None = None
    currency: str = "USD"
    website: str = ""
    long_summary: str = ""
    country: str = ""
    employees: int | None = None
    warning: str = ""


# ---------------------------------------------------------------------------
# 關鍵數據一覽（首頁表）
# ---------------------------------------------------------------------------
@dataclass
class KeyMetrics:
    current_price: float | None = None
    market_cap: float | None = None
    latest_quarter: str = ""
    latest_revenue: float | None = None
    latest_revenue_yoy: float | None = None
    gross_margin: float | None = None       # 毛利率（比例 0~1）
    net_margin: float | None = None
    consensus_rating: str = ""
    target_mean: float | None = None
    implied_upside_pct: float | None = None
    week52_high: float | None = None
    week52_low: float | None = None
    trailing_pe: float | None = None
    forward_pe: float | None = None
    dividend_yield: float | None = None


# ---------------------------------------------------------------------------
# 股價與技術面
# ---------------------------------------------------------------------------
@dataclass
class PriceData:
    price_df: object | None = None
    current_price: float | None = None
    ma50: float | None = None
    ma200: float | None = None
    week52_high: float | None = None
    week52_low: float | None = None
    pct_from_high: float | None = None
    pct_from_low: float | None = None
    recent_high_date: date | None = None
    recent_low_date: date | None = None
    warning: str = ""


# ---------------------------------------------------------------------------
# 季度財務（近 8 季）
# ---------------------------------------------------------------------------
@dataclass
class QuarterPoint:
    period: str                    # "2024Q1"
    revenue: float | None = None
    revenue_yoy: float | None = None
    gross_margin: float | None = None      # 比例
    fcf: float | None = None
    fcf_margin: float | None = None        # 比例
    eps_actual: float | None = None
    eps_estimate: float | None = None
    eps_surprise_pct: float | None = None
    beat_miss: str = ""


@dataclass
class FinancialsData:
    quarters: list[QuarterPoint] = field(default_factory=list)   # 由舊到新
    revenue_cagr_3y: float | None = None
    warning: str = ""


# ---------------------------------------------------------------------------
# 營收結構（部門 / 地區）
# ---------------------------------------------------------------------------
@dataclass
class RevenueSegments:
    labels: list[str] = field(default_factory=list)
    values: list[float] = field(default_factory=list)
    basis: str = ""                # 例如 "年度營收結構" / "業務部門"
    warning: str = ""


# ---------------------------------------------------------------------------
# 估值倍數
# ---------------------------------------------------------------------------
@dataclass
class ValuationMultiples:
    trailing_pe: float | None = None
    forward_pe: float | None = None
    ps_ratio: float | None = None
    ev_sales: float | None = None
    ev_ebitda: float | None = None
    ev_fcf: float | None = None
    peg: float | None = None
    price_to_book: float | None = None
    pe_series: object | None = None
    pe_mean_3y: float | None = None
    pe_current: float | None = None
    pe_context_note: str = ""
    warning: str = ""


# ---------------------------------------------------------------------------
# 華爾街評等與目標價（含情境）
# ---------------------------------------------------------------------------
@dataclass
class PriceScenario:
    name: str          # 樂觀 / 基準 / 保守
    target: float | None = None
    implied_pct: float | None = None
    rationale: str = ""


@dataclass
class RatingData:
    consensus: str = ""
    num_analysts: int | None = None
    target_mean: float | None = None
    target_high: float | None = None
    target_low: float | None = None
    current_price: float | None = None
    implied_upside_pct: float | None = None
    scenarios: list[PriceScenario] = field(default_factory=list)
    source: str = ""
    warning: str = ""


# ---------------------------------------------------------------------------
# 選擇權情緒
# ---------------------------------------------------------------------------
@dataclass
class OptionsSentiment:
    expiry: str = ""
    put_oi: int | None = None
    call_oi: int | None = None
    put_call_ratio: float | None = None
    sentiment_note: str = ""
    warning: str = ""


# ---------------------------------------------------------------------------
# 內部人與機構動向
# ---------------------------------------------------------------------------
@dataclass
class SmartMoneyData:
    insider_summary: list[str] = field(default_factory=list)
    institutional_ownership_pct: float | None = None
    insider_ownership_pct: float | None = None
    warning: str = ""


# ---------------------------------------------------------------------------
# 同業比較
# ---------------------------------------------------------------------------
@dataclass
class PeerRow:
    ticker: str
    name: str = ""
    market_cap: float | None = None
    revenue_growth: float | None = None    # 比例
    gross_margin: float | None = None
    profit_margin: float | None = None
    ev_sales: float | None = None
    forward_pe: float | None = None
    is_self: bool = False


@dataclass
class PeerComparison:
    rows: list[PeerRow] = field(default_factory=list)
    basis_note: str = ""
    warning: str = ""


# ---------------------------------------------------------------------------
# 新聞
# ---------------------------------------------------------------------------
@dataclass
class NewsItem:
    title: str
    publish_date: str = ""
    source: str = ""
    url: str = ""
    snippet: str = ""
    provider: str = ""


@dataclass
class NewsBundle:
    items: list[NewsItem] = field(default_factory=list)
    provider_errors: dict[str, str] = field(default_factory=dict)
    providers_used: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# AI 質化分析內容
# ---------------------------------------------------------------------------
@dataclass
class AIContent:
    core_view: str = ""            # 首頁執行摘要 / 核心觀點
    business_overview: str = ""    # 業務模式
    moat: str = ""                 # 護城河分析
    risks: str = ""                # 風險提示
    conclusion: str = ""           # 結論
    ai_generated: bool = False     # True = LLM 生成；False = 模板 fallback
    provider: str = ""             # anthropic / openai / template
    notice: str = ""               # fallback 時的提示語


# ---------------------------------------------------------------------------
# 圖表路徑（產出後填入）
# ---------------------------------------------------------------------------
@dataclass
class ChartPaths:
    revenue_segments: str = ""
    revenue_yoy: str = ""
    margins: str = ""
    eps: str = ""
    price_candle: str = ""
    pe_trend: str = ""
    peers: str = ""


# ---------------------------------------------------------------------------
# 彙整
# ---------------------------------------------------------------------------
@dataclass
class ReportData:
    profile: CompanyProfile
    generated_on: date
    key_metrics: KeyMetrics
    price: PriceData
    financials: FinancialsData
    segments: RevenueSegments
    valuation: ValuationMultiples
    rating: RatingData
    options: OptionsSentiment
    smart_money: SmartMoneyData
    peers: PeerComparison
    news: NewsBundle
    ai: AIContent
    charts: ChartPaths = field(default_factory=ChartPaths)
