"""新聞聚合器：依序執行各 provider，聚合、去重、排序。

任一來源失敗只記錄於 provider_errors，不影響其他來源；
最終彙整所有成功抓到的新聞。
"""
from __future__ import annotations

import logging

from config import NEWS_MAX_ITEMS
from core.models import NewsBundle, NewsItem
from news.providers.base import NewsProvider
from news.providers.google_news_rss import GoogleNewsRSSProvider
from news.providers.stockanalysis import StockAnalysisNewsProvider
from news.providers.yfinance_news import YFinanceNewsProvider

logger = logging.getLogger(__name__)


def _default_providers() -> list[NewsProvider]:
    # 順序即優先序：yfinance → stockanalysis → Google News RSS
    return [
        YFinanceNewsProvider(),
        StockAnalysisNewsProvider(),
        GoogleNewsRSSProvider(),
    ]


def _dedup_key(item: NewsItem) -> str:
    title = "".join(ch.lower() for ch in item.title if ch.isalnum())
    return title[:60]


def fetch_news(
    ticker: str,
    company_name: str = "",
    providers: list[NewsProvider] | None = None,
) -> NewsBundle:
    providers = providers or _default_providers()
    bundle = NewsBundle()
    seen: set[str] = set()

    for provider in providers:
        try:
            items = provider.fetch(ticker, company_name)
        except Exception as exc:  # noqa: BLE001 - provider 內應自理，此處為最後防線
            bundle.provider_errors[provider.name] = str(exc)
            logger.warning("新聞來源 %s 失敗: %s", provider.name, exc)
            continue

        if not items:
            bundle.provider_errors.setdefault(provider.name, "無資料或抓取失敗")
            continue

        added = 0
        for item in items:
            key = _dedup_key(item)
            if not key or key in seen:
                continue
            seen.add(key)
            bundle.items.append(item)
            added += 1

        if added:
            bundle.providers_used.append(provider.name)
        logger.info("新聞來源 %s 取得 %d 則（新增 %d）", provider.name, len(items), added)

    # 依日期新到舊排序（無日期者排後）
    bundle.items.sort(key=lambda x: x.publish_date or "", reverse=True)
    bundle.items = bundle.items[:NEWS_MAX_ITEMS]
    return bundle
