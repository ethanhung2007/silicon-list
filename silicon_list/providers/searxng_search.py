import hashlib
import os
import re
from typing import Any, List
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests

from silicon_list.models import Listing
from silicon_list.pipeline.normalize import normalize_apply_url
from silicon_list.providers.base import BaseProvider, ProviderError, RateLimitError


class SearXNGSearchProvider(BaseProvider):
    """Fetches listings through a local SearXNG JSON API."""

    DIRECT_URL_TOKENS = [
        "greenhouse.io",
        "lever.co",
        "ashbyhq.com",
        "workdayjobs.com",
        "myworkdayjobs.com",
        "smartrecruiters.com",
        "icims.com",
        "oraclecloud.com",
        "successfactors.com",
        "indeed.com/viewjob",
        "indeed.com/jobs/view",
        "glassdoor.com/job-listing",
        "linkedin.com/jobs/view",
        "joinhandshake.com/stu/jobs",
        "app.joinhandshake.com/stu/jobs",
        "simplify.jobs/p/",
        "/stu/postings",
        "jobs.",
        "/job/",
        "/jobs/",
        "/careers/",
        "/career/",
        "gh_jid=",
        "jobid=",
    ]

    JUNK_URL_TOKENS = [
        "linkedin.com/jobs/search",
        "indeed.com/jobs?q=",
        "indeed.com/jobs?",
        "indeed.com/career",
        "glassdoor.com/job-search",
        "glassdoor.com/jobs",
        "ziprecruiter.com",
        "monster.com",
        "simplyhired.com",
        "builtin.com/jobs",
        "reddit.com",
        "youtube.com",
        "medium.com",
        "substack.com",
        "levels.fyi",
        "teamblind.com",
        "applybolt.app",
    ]

    JUNK_TITLE_TOKENS = [
        "salary",
        "interview",
        "resume",
        "reddit",
        "reddit comments",
        "courses",
        "bootcamp",
        "job search",
        "jobs in ",
    ]

    STUDENT_TOKENS = ["intern", "internship", "co-op", "co op", "coop"]
    HARDWARE_TOKENS = [
        "hardware",
        "silicon",
        "fpga",
        "rtl",
        "asic",
        "verification",
        "design verification",
        "dv",
        "firmware",
        "embedded",
        "vlsi",
        "physical design",
        "eda",
        "verilog",
        "systemverilog",
    ]
    SENIOR_TOKENS = ["senior", "sr.", "staff", "principal", "manager", "director", "new grad", "full-time", "full time"]

    def __init__(self, config):
        super().__init__(config)
        configured_url = getattr(config, "searxng_url", "http://localhost:8080")
        self.base_url = os.getenv(getattr(config, "searxng_url_env", "SEARXNG_URL"), configured_url).rstrip("/")

    def fetch_listings(self) -> List[Listing]:
        listings: list[Listing] = []
        seen: set[tuple[str, str, str]] = set()

        for query in self._search_queries():
            for item in self._fetch_query(query):
                listing = self._item_to_listing(item, query)
                if not listing or not self._looks_useful(listing):
                    continue

                dedupe_key = (
                    self._normalize_url(listing.apply_url).lower(),
                    listing.company.lower(),
                    listing.role.lower(),
                )
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                listings.append(listing)

        return listings

    def _search_queries(self) -> list[str]:
        queries = [
            *getattr(self.config, "searxng_search_queries", []),
            *getattr(self.config, "searxng_job_board_search_queries", []),
        ]
        return list(dict.fromkeys(query for query in queries if query))

    def _fetch_query(self, query: str) -> list[dict[str, Any]]:
        params = {
            "q": query,
            "format": "json",
        }

        try:
            response = requests.get(f"{self.base_url}/search", params=params, timeout=20)
        except requests.RequestException as e:
            raise ProviderError(f"SearXNG search request failed for {query!r}: {e}")

        if response.status_code == 429:
            raise RateLimitError(f"SearXNG rate limit hit for {query!r}.")
        if response.status_code != 200:
            raise ProviderError(
                f"SearXNG search returned status {response.status_code} for {query!r}: "
                f"{response.text[:300]}"
            )

        try:
            data = response.json()
        except ValueError as e:
            raise ProviderError(f"SearXNG search returned invalid JSON for {query!r}: {e}")

        results = data.get("results", [])
        if not isinstance(results, list):
            raise ProviderError(f"SearXNG search returned an invalid results list for {query!r}.")
        return results

    def _item_to_listing(self, item: dict[str, Any], query: str) -> Listing | None:
        title = self._clean_text(item.get("title", ""))
        snippet = self._clean_text(item.get("content") or item.get("snippet") or "")
        raw_link = str(item.get("url", "")).strip()
        link = normalize_apply_url(self._normalize_url(raw_link))

        if not title or not link.startswith(("http://", "https://")):
            return None

        company = self._infer_company(title, link)
        source_job_id = hashlib.md5(link.encode("utf-8")).hexdigest()[:16]

        return Listing(
            source="searxng",
            source_job_id=source_job_id,
            company=company,
            role=title,
            location="",
            apply_url=link,
            original_url=raw_link,
            canonical_url=link,
            source_url=link,
            description=snippet,
            cycle=self._infer_cycle(f"{title} {snippet} {query}"),
            raw_metadata={
                "query": query,
                "engine": item.get("engine") or item.get("engines"),
            },
        )

    def _looks_useful(self, listing: Listing) -> bool:
        text = f"{listing.role} {listing.description}".lower()
        url = listing.apply_url.lower()

        if any(token in url for token in self.JUNK_URL_TOKENS):
            return False
        if any(token in text for token in self.JUNK_TITLE_TOKENS):
            return False
        if any(token in text for token in self.SENIOR_TOKENS):
            return False
        if not any(token in text for token in self.STUDENT_TOKENS):
            return False
        if not any(token in text for token in self.HARDWARE_TOKENS):
            return False

        return any(token in url for token in self.DIRECT_URL_TOKENS)

    def _clean_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", str(text)).strip()

    def _infer_company(self, title: str, link: str) -> str:
        for separator in (" | ", " - ", " at ", " @ "):
            if separator in title:
                parts = [p.strip() for p in title.split(separator) if p.strip()]
                if separator in (" at ", " @ ") and len(parts) > 1:
                    return parts[-1]
                if parts:
                    return parts[-1]

        host = urlparse(link).netloc.lower()
        host = host.removeprefix("www.")
        for suffix in (
            ".greenhouse.io",
            ".lever.co",
            ".ashbyhq.com",
            ".myworkdayjobs.com",
            ".wd1.myworkdayjobs.com",
            ".wd5.myworkdayjobs.com",
        ):
            if host.endswith(suffix):
                return host.removesuffix(suffix).replace("-", " ").title()

        return host.split(".")[0].replace("-", " ").title() if host else "Unknown"

    def _infer_cycle(self, text: str) -> str:
        text_lower = text.lower()
        for season in ("summer", "fall", "spring"):
            for year in ("2026", "2027"):
                if season in text_lower and year in text_lower:
                    return f"{season.title()} {year}"
        for year in ("2026", "2027"):
            if year in text_lower:
                return year
        return ""

    def _normalize_url(self, url: str) -> str:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return url

        tracking_prefixes = ("utm_",)
        tracking_names = {"gh_src", "ref", "source", "src"}
        params = [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.lower().startswith(tracking_prefixes) and key.lower() not in tracking_names
        ]
        return urlunparse(parsed._replace(query=urlencode(params), fragment=""))
