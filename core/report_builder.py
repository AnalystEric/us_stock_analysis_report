"""報告資料組裝：解析代號 → 逐一呼叫各資料 / 分析模組 → 回傳 ReportData。

每個模組獨立 try/except，任一失敗只讓對應區塊留白，不影響整份報告。
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from ai.analyst import generate_ai_content
from analytics.metrics import assemble_key_metrics, build_scenarios
from analytics.scoring import build_scorecard
from core.models import (
    AIContent,
    CompanyProfile,
    FinancialsData,
    Fundamentals,
    InstitutionalFlow,
    MarginData,
    MonthlyRevenue,
    NewsBundle,
    OptionsSentiment,
    PeerComparison,
    PriceData,
    RatingData,
    ReportData,
    RevenueSegments,
    ScoreCard,
    SmartMoneyData,
    ValuationMultiples,
)
from core.market import is_tw_market
from core.ticker_resolver import resolve_stock
from data_sources.financials_fetcher import fetch_financials
from data_sources.fundamentals_fetcher import fetch_fundamentals
from data_sources.options_fetcher import fetch_options_sentiment
from data_sources.ownership_fetcher import fetch_smart_money
from data_sources.peers_fetcher import fetch_peers
from data_sources.price_fetcher import fetch_price
from data_sources.profile_fetcher import fetch_profile
from data_sources.rating_fetcher import fetch_rating
from data_sources.segments_fetcher import fetch_segments
from data_sources.valuation_fetcher import fetch_valuation
from news.aggregator import fetch_news

logger = logging.getLogger(__name__)


def _safe(step: str, func, fallback):
    try:
        logger.info("擷取：%s ...", step)
        return func()
    except Exception as exc:  # noqa: BLE001
        logger.warning("模組 %s 失敗（使用空白區塊）: %s", step, exc)
        return fallback


def build_report_data(user_input: str) -> ReportData:
    stock = resolve_stock(user_input)
    ticker = stock.symbol
    is_tw = is_tw_market(stock.market)

    profile: CompanyProfile = _safe(
        "個股基本資訊", lambda: fetch_profile(ticker),
        CompanyProfile(ticker=ticker, company_name=ticker, warning="基本資料擷取失敗。"))
    # 標記市場別；台股補上官方清單名稱、幣別與純代號
    profile.market = stock.market
    profile.stock_code = stock.code
    if is_tw:
        profile.currency = profile.currency or "TWD"
        if profile.currency == "USD":
            profile.currency = "TWD"
        # 台股優先採用官方清單的中文簡稱（yfinance 回傳英文長名）
        if stock.name:
            profile.company_name = stock.name
    price: PriceData = _safe(
        "股價與技術面", lambda: fetch_price(ticker), PriceData(warning="股價資料擷取失敗。"))
    financials: FinancialsData = _safe(
        "季度財務(近8季)", lambda: fetch_financials(ticker),
        FinancialsData(warning="財務資料擷取失敗。"))
    segments: RevenueSegments = _safe(
        "營收結構", lambda: fetch_segments(ticker), RevenueSegments(warning="營收結構擷取失敗。"))
    valuation: ValuationMultiples = _safe(
        "估值倍數", lambda: fetch_valuation(ticker), ValuationMultiples(warning="估值資料擷取失敗。"))
    rating: RatingData = _safe(
        "華爾街評等/目標價", lambda: fetch_rating(ticker, price.current_price),
        RatingData(warning="評等資料擷取失敗。"))
    options: OptionsSentiment = _safe(
        "選擇權情緒", lambda: fetch_options_sentiment(ticker),
        OptionsSentiment(warning="查無選擇權數據。"))
    smart_money: SmartMoneyData = _safe(
        "內部人與機構動向", lambda: fetch_smart_money(ticker),
        SmartMoneyData(warning="內部人/機構資料擷取失敗。"))
    peers: PeerComparison = _safe(
        "同業比較", lambda: fetch_peers(ticker), PeerComparison(warning="同業比較擷取失敗。"))
    news: NewsBundle = _safe(
        "新聞", lambda: fetch_news(ticker, profile.company_name), NewsBundle())
    fundamentals: Fundamentals = _safe(
        "基本面指標", lambda: fetch_fundamentals(ticker),
        Fundamentals(warning="基本面資料擷取失敗。"))

    # 補齊評等的目前股價與隱含空間、情境
    if rating.current_price is None:
        rating.current_price = price.current_price
    if rating.current_price and rating.target_mean and rating.implied_upside_pct is None:
        rating.implied_upside_pct = (rating.target_mean - rating.current_price) / rating.current_price * 100
    rating.scenarios = build_scenarios(rating)

    # 關鍵數據彙整
    key_metrics = assemble_key_metrics(profile, price, financials, valuation, rating)

    # 綜合體質評分（純數據，不需 API Key）
    scorecard = _safe(
        "綜合體質評分",
        lambda: build_scorecard(key_metrics, price, financials, valuation, rating, fundamentals),
        ScoreCard(warning="評分計算失敗。"))

    # 台股專屬區塊（月營收 / 三大法人 / 融資融券）——僅台股擷取
    monthly_revenue = MonthlyRevenue()
    institutional = InstitutionalFlow()
    margin = MarginData()
    if is_tw and stock.code:
        from data_sources.tw.institutional import fetch_institutional
        from data_sources.tw.margin import fetch_margin
        from data_sources.tw.monthly_revenue import fetch_monthly_revenue
        monthly_revenue = _safe(
            "月營收", lambda: fetch_monthly_revenue(stock.code, stock.market),
            MonthlyRevenue(warning="月營收擷取失敗。"))
        institutional = _safe(
            "三大法人買賣超", lambda: fetch_institutional(stock.code, stock.market),
            InstitutionalFlow(warning="三大法人資料擷取失敗。"))
        margin = _safe(
            "融資融券", lambda: fetch_margin(stock.code, stock.market),
            MarginData(warning="融資融券資料擷取失敗。"))
        # 月營收最新 YoY 補進關鍵數據（台股以月營收為即時營運指標）
        if monthly_revenue.latest_yoy is not None and key_metrics.latest_revenue_yoy is None:
            key_metrics.latest_revenue_yoy = monthly_revenue.latest_yoy

    # AI 質化分析（含 fallback）
    ai = _safe(
        "AI 質化分析",
        lambda: generate_ai_content(profile, key_metrics, financials, valuation, rating, peers, news),
        AIContent(provider="template", notice="AI 分析模組失敗，僅呈現數據。"))

    return ReportData(
        profile=profile,
        generated_on=_today(),
        key_metrics=key_metrics,
        price=price,
        financials=financials,
        segments=segments,
        valuation=valuation,
        rating=rating,
        options=options,
        smart_money=smart_money,
        peers=peers,
        news=news,
        ai=ai,
        fundamentals=fundamentals,
        scorecard=scorecard,
        monthly_revenue=monthly_revenue,
        institutional=institutional,
        margin=margin,
    )


def _today() -> date:
    return datetime.now(tz=timezone.utc).astimezone().date()
