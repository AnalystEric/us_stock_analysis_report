"""新聞 provider 介面。每個來源實作 fetch()，回傳 NewsItem 清單；不得拋出例外。"""
from __future__ import annotations

import abc
import logging

from core.models import NewsItem

logger = logging.getLogger(__name__)


class NewsProvider(abc.ABC):
    name: str = "base"

    @abc.abstractmethod
    def fetch(self, ticker: str, company_name: str = "") -> list[NewsItem]:
        """回傳該來源的新聞清單。實作內部應自行 try/except，失敗回傳空清單。"""
        raise NotImplementedError
