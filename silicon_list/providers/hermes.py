from __future__ import annotations

import datetime
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, List

from silicon_list.models import Listing
from silicon_list.pipeline.normalize import select_best_url
from silicon_list.providers.base import BaseProvider, ProviderError


_DEFAULT_HERMES_PATH = Path.home() / ".silicon-list" / "hermes-listings.json"
_STALENESS_HOURS = 24


class HermesProvider(BaseProvider):
    """
    Reads listings from a Hermes Agent JSON export.

    Hermes Agent browses the web like a human researcher and writes results to
    ~/.silicon-list/hermes-listings.json in the same schema as openclaw-listings.json.

    If the file is fresh (< 24 h old) it is loaded and returned. If it is stale or
    missing, a clear message explains how to regenerate it. The provider never
    crashes the main run — a missing file raises ProviderError which main.py
    catches and continues.

    To regenerate:
        ./scripts/run_hermes_silicon_list.sh
    """

    def __init__(self, config, export_path: Path | None = None):
        super().__init__(config)
        configured = getattr(config, "hermes_export_path", str(_DEFAULT_HERMES_PATH))
        self.export_path: Path = export_path or Path(configured).expanduser()

    def fetch_listings(self) -> List[Listing]:
        path = self.export_path

        if not path.exists():
            raise ProviderError(
                f"Hermes export not found at {path}. "
                "Run ./scripts/run_hermes_silicon_list.sh to generate it, "
                "or pass --hermes-file <path>."
            )

        mtime = datetime.datetime.fromtimestamp(path.stat().st_mtime)
        age_hours = (datetime.datetime.now() - mtime).total_seconds() / 3600
        if age_hours > _STALENESS_HOURS:
            print(
                f"[hermes] Warning: export is {age_hours:.0f}h old (> {_STALENESS_HOURS}h limit). "
                "Re-run ./scripts/run_hermes_silicon_list.sh for fresh data.",
                file=sys.stderr,
            )

        try:
            with open(path, "r") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ProviderError(f"Hermes export is invalid JSON: {e}")
        except OSError as e:
            raise ProviderError(f"Could not read Hermes export: {e}")

        rows = data.get("listings", data) if isinstance(data, dict) else data
        if not isinstance(rows, list):
            raise ProviderError(
                "Hermes export must be a JSON object with a 'listings' list."
            )

        return [self._row_to_listing(row) for row in rows if isinstance(row, dict)]

    def _row_to_listing(self, row: dict[str, Any]) -> Listing:
        company = self._str(row, "company", "employer", "organization") or "Unknown"
        role = self._str(row, "role", "title", "job_title", "position") or "Unknown role"
        location = self._str(row, "location", "city") or ""

        url_keys = (
            "direct_apply_url", "apply_url", "application_url",
            "posting_url", "job_url", "canonical_url", "url", "link",
            "source_url", "discovered_url", "result_url",
        )
        url_candidates = [row[k] for k in url_keys if isinstance(row.get(k), str)]
        for list_key in ("alternate_urls", "alternates", "links", "urls"):
            val = row.get(list_key)
            if isinstance(val, list):
                url_candidates += [v for v in val if isinstance(v, str)]

        apply_url, canonical_url, alternate_urls = select_best_url(url_candidates)
        original_url = self._str(row, "apply_url", "url", "link") or ""
        source_url = self._str(row, "source_url", "source", "discovered_url") or original_url
        description = self._str(row, "description", "snippet", "summary") or ""
        posted_at = self._str(row, "posted_at", "posted", "date", "age") or None
        cycle = self._str(row, "cycle", "term", "season") or ""
        req_id = self._str(row, "req_id", "requisition_id", "job_req_id") or ""
        source_job_id = self._str(row, "source_job_id", "id", "job_id")

        if not source_job_id:
            source_job_id = hashlib.md5(
                f"{company}-{role}-{location}-{apply_url}".lower().encode("utf-8")
            ).hexdigest()[:16]

        return Listing(
            source="hermes",
            source_job_id=source_job_id,
            company=company,
            role=role,
            location=location,
            apply_url=apply_url,
            original_url=original_url,
            canonical_url=canonical_url,
            source_url=source_url,
            alternate_urls=alternate_urls,
            description=description,
            posted_at=posted_at,
            cycle=cycle,
            raw_metadata={
                "hermes_source": True,
                "hermes_export": str(self.export_path),
                "req_id": req_id,
                **{k: v for k, v in row.items() if k != "description"},
            },
        )

    def _str(self, row: dict[str, Any], *keys: str) -> str:
        for key in keys:
            value = row.get(key)
            if value is not None:
                return str(value).strip()
        return ""
