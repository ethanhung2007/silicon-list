import hashlib
import os
import re
from typing import Any, List

import requests

from silicon_list.models import Listing
from silicon_list.providers.base import BaseProvider, ProviderError, RateLimitError


class GoogleSearchProvider(BaseProvider):
    """Fetches listings through Google's Programmable Search JSON API."""

    URL = "https://www.googleapis.com/customsearch/v1"

    def fetch_listings(self) -> List[Listing]:
        api_key = os.getenv(self.config.google_api_key_env)
        cse_id = os.getenv(self.config.google_cse_id_env)

        if not api_key or not cse_id:
            raise ProviderError(
                f"Google search provider requires {self.config.google_api_key_env} "
                f"and {self.config.google_cse_id_env} environment variables."
            )

        listings: list[Listing] = []
        for query in self.config.search_queries:
            listings.extend(self._fetch_query(query, api_key, cse_id))

        return listings

    def _fetch_query(self, query: str, api_key: str, cse_id: str) -> List[Listing]:
        params = {
            "key": api_key,
            "cx": cse_id,
            "q": query,
            "num": max(1, min(10, self.config.search_results_per_query)),
        }

        try:
            response = requests.get(self.URL, params=params, timeout=20)
        except requests.RequestException as e:
            raise ProviderError(f"Google search request failed for {query!r}: {e}")

        if response.status_code in (403, 429):
            raise RateLimitError(f"Google search quota or rate limit hit for {query!r}.")
        if response.status_code != 200:
            raise ProviderError(
                f"Google search returned status {response.status_code} for {query!r}: "
                f"{response.text[:300]}"
            )

        data = response.json()
        return [self._item_to_listing(item, query) for item in data.get("items", [])]

    def _item_to_listing(self, item: dict[str, Any], query: str) -> Listing:
        title = self._clean_text(item.get("title", ""))
        snippet = self._clean_text(item.get("snippet", ""))
        link = item.get("link", "").strip()
        company = self._infer_company(title, link)
        source_job_id = hashlib.md5(link.encode("utf-8")).hexdigest()[:16]

        return Listing(
            source="google_search",
            source_job_id=source_job_id,
            company=company,
            role=title or "Search result",
            location="",
            apply_url=link,
            description=snippet,
            cycle="",
            raw_metadata={"query": query},
        )

    def _clean_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    def _infer_company(self, title: str, link: str) -> str:
        for separator in (" | ", " - ", " at "):
            if separator in title:
                parts = [p.strip() for p in title.split(separator) if p.strip()]
                if parts:
                    return parts[-1]

        host_match = re.search(r"https?://(?:www\.)?([^/]+)", link)
        if host_match:
            host = host_match.group(1).split(".")[0]
            return host.replace("-", " ").title()

        return "Unknown"
