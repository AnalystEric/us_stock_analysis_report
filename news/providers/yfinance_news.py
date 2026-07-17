"""新聞來源 1：yfinance 自帶 ticker.news。

yfinance 不同版本的 news 結構不同：
  * 新版：每筆為 {'content': {'title', 'pubDate', 'provider': {...}, 'canonicalUrl': {...}, 'summary'}}
  * 舊版：扁平 {'title', 'publisher', 'link', 'providerPublishTime'}
本 provider 同時支援兩種格式。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from config import NEWS_PER_PROVIDER
from core.models import NewsItem
from data_sources.yf_client import get_ticker, safe_call
from news.providers.base import NewsProvider

logger = logging.getLogger(__name__)


class YFinanceNewsProvider(NewsProvider):
    name = "yfinance"

    def fetch(self, ticker: str, company_name: str = "") -> list[NewsItem]:
        tk = get_ticker(ticker)
        raw = safe_call(lambda: tk.news, default=[], label="ticker.news")
        if not isinstance(raw, list):
            return []

        items: list[NewsItem] = []
        for entry in raw[: NEWS_PER_PROVIDER * 2]:
            item = self._parse(entry)
            if item and item.title:
                items.append(item)
            if len(items) >= NEWS_PER_PROVIDER:
                break
        return items

    def _parse(self, entry: dict) -> NewsItem | None:
        if not isinstance(entry, dict):
            return None

        # 新版巢狀結構
        content = entry.get("content")
        if isinstance(content, dict):
            title = content.get("title", "")
            summary = content.get("summary", "") or content.get("description", "")
            provider = (content.get("provider") or {}).get("displayName", "")
            url = ""
            for key in ("canonicalUrl", "clickThroughUrl"):
                sub = content.get(key)
                if isinstance(sub, dict) and sub.get("url"):
                    url = sub["url"]
                    break
            pub = content.get("pubDate") or content.get("displayTime") or ""
            return NewsItem(
                title=title,
                publish_date=_norm_date(pub),
                source=provider or "Yahoo Finance",
                url=url,
                snippet=(summary or "")[:280],
                provider=self.name,
            )

        # 舊版扁平結構
        title = entry.get("title", "")
        ts = entry.get("providerPublishTime")
        return NewsItem(
            title=title,
            publish_date=_from_epoch(ts),
            source=entry.get("publisher", "Yahoo Finance"),
            url=entry.get("link", ""),
            snippet="",
            provider=self.name,
        )


def _from_epoch(ts) -> str:
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OSError):
        return ""


def _norm_date(text: str) -> str:
    if not text:
        return ""
    txt = str(text).replace("Z", "+00:00")
    for fmt in None, "%Y-%m-%dT%H:%M:%S%z":
        try:
            if fmt is None:
                return datetime.fromisoformat(txt).strftime("%Y-%m-%d")
            return datetime.strptime(txt, fmt).strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            continue
    return str(text)[:10]
