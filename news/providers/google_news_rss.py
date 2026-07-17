"""新聞來源 3：Google News RSS 搜尋 "{ticker} stock"。

Google News RSS 為公開端點、無需 API key，穩定度高，作為最後備援。
"""
from __future__ import annotations

import logging
from urllib.parse import quote_plus

import feedparser

from config import HTTP_USER_AGENT, NEWS_PER_PROVIDER
from core.models import NewsItem
from news.providers.base import NewsProvider
from utils.http import get_session, safe_get

logger = logging.getLogger(__name__)


class GoogleNewsRSSProvider(NewsProvider):
    name = "googlenews"

    def fetch(self, ticker: str, company_name: str = "") -> list[NewsItem]:
        query = f"{ticker} stock"
        if company_name:
            query = f"{ticker} {company_name} stock"
        url = (
            "https://news.google.com/rss/search?q="
            + quote_plus(query)
            + "&hl=en-US&gl=US&ceid=US:en"
        )

        # 用共用 session 抓取（含 retry），再交給 feedparser 解析內容
        resp = safe_get(get_session(), url, attempts=2)
        if resp is None:
            # 直接讓 feedparser 試（它有自己的抓取邏輯）
            feed = feedparser.parse(url, request_headers={"User-Agent": HTTP_USER_AGENT})
        else:
            feed = feedparser.parse(resp.content)

        entries = getattr(feed, "entries", []) or []
        items: list[NewsItem] = []
        for entry in entries[:NEWS_PER_PROVIDER]:
            title = getattr(entry, "title", "")
            if not title:
                continue
            # Google News 標題常為 "標題 - 來源"，拆出來源
            source = ""
            src_obj = getattr(entry, "source", None)
            if src_obj is not None:
                source = getattr(src_obj, "title", "") or ""
            if not source and " - " in title:
                source = title.rsplit(" - ", 1)[-1]
                title = title.rsplit(" - ", 1)[0]

            items.append(
                NewsItem(
                    title=title,
                    publish_date=_norm_date(getattr(entry, "published", "")),
                    source=source or "Google News",
                    url=getattr(entry, "link", ""),
                    snippet="",
                    provider=self.name,
                )
            )
        return items


def _norm_date(text: str) -> str:
    if not text:
        return ""
    from email.utils import parsedate_to_datetime

    try:
        return parsedate_to_datetime(text).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return str(text)[:16]
