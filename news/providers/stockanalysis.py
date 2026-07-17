"""新聞來源 2：stockanalysis.com。

優先嘗試其公開 JSON news 端點；失敗則退回解析股票頁 HTML 的新聞區塊。
兩者皆失敗時回傳空清單（由聚合器記錄錯誤）。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from config import NEWS_PER_PROVIDER
from core.models import NewsItem
from news.providers.base import NewsProvider
from utils.http import get_session, safe_get

logger = logging.getLogger(__name__)


class StockAnalysisNewsProvider(NewsProvider):
    name = "stockanalysis"

    def fetch(self, ticker: str, company_name: str = "") -> list[NewsItem]:
        items = self._from_api(ticker)
        if items:
            return items
        return self._from_html(ticker)

    # --- JSON API ---
    def _from_api(self, ticker: str) -> list[NewsItem]:
        session = get_session()
        url = f"https://stockanalysis.com/api/symbol/s/{ticker.lower()}/news"
        resp = safe_get(session, url, attempts=2,
                        headers={"Accept": "application/json"})
        if resp is None:
            return []
        try:
            payload = resp.json()
        except ValueError:
            return []

        rows = payload.get("data") if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            return []

        items: list[NewsItem] = []
        for row in rows[:NEWS_PER_PROVIDER]:
            if not isinstance(row, dict):
                continue
            title = row.get("title") or row.get("t") or ""
            if not title:
                continue
            items.append(
                NewsItem(
                    title=title,
                    publish_date=_norm_date(row.get("date") or row.get("d") or ""),
                    source=row.get("source") or row.get("publisher") or "StockAnalysis",
                    url=row.get("url") or row.get("link") or row.get("u") or "",
                    snippet=(row.get("text") or row.get("summary") or "")[:280],
                    provider=self.name,
                )
            )
        return items

    # --- HTML fallback ---
    def _from_html(self, ticker: str) -> list[NewsItem]:
        session = get_session()
        url = f"https://stockanalysis.com/stocks/{ticker.lower()}/"
        resp = safe_get(session, url, attempts=2)
        if resp is None:
            return []

        try:
            soup = BeautifulSoup(resp.text, "lxml")
        except Exception:  # noqa: BLE001
            soup = BeautifulSoup(resp.text, "html.parser")

        items: list[NewsItem] = []
        seen: set[str] = set()
        # 新聞區塊常見容器：class 含 "news"；退而抓所有含標題文字的外部連結
        containers = soup.select('[class*="news"] a, div.gap-2 a, article a')
        for a in containers:
            title = a.get_text(strip=True)
            href = a.get("href", "")
            if not title or len(title) < 25:
                continue
            if href in seen:
                continue
            seen.add(href)
            if href.startswith("/"):
                href = "https://stockanalysis.com" + href
            items.append(
                NewsItem(
                    title=title,
                    publish_date="",
                    source="StockAnalysis",
                    url=href,
                    snippet="",
                    provider=self.name,
                )
            )
            if len(items) >= NEWS_PER_PROVIDER:
                break
        return items


def _norm_date(text) -> str:
    if not text:
        return ""
    if isinstance(text, (int, float)):
        try:
            return datetime.fromtimestamp(int(text), tz=timezone.utc).strftime("%Y-%m-%d")
        except (ValueError, OSError):
            return ""
    txt = str(text).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(txt).strftime("%Y-%m-%d")
    except ValueError:
        return str(text)[:10]
