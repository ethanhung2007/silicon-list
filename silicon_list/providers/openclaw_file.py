import hashlib
import json
from pathlib import Path
from typing import Any, List

from silicon_list.models import Listing
from silicon_list.pipeline.normalize import select_best_url
from silicon_list.providers.base import BaseProvider, ProviderError


class OpenClawFileProvider(BaseProvider):
    """Imports listings exported by OpenClaw or another browser agent."""

    def __init__(self, config, export_path: Path | None = None):
        super().__init__(config)
        configured_path = Path(config.openclaw_export_path).expanduser()
        self.export_path = export_path or configured_path

    def fetch_listings(self) -> List[Listing]:
        if not self.export_path.exists():
            raise ProviderError(
                f"OpenClaw export file not found at {self.export_path}. "
                "Run a browser agent to create it, or pass --openclaw-file."
            )

        try:
            with open(self.export_path, "r") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ProviderError(f"OpenClaw export is invalid JSON: {e}")
        except OSError as e:
            raise ProviderError(f"Could not read OpenClaw export: {e}")

        rows = data.get("listings", data) if isinstance(data, dict) else data
        if not isinstance(rows, list):
            raise ProviderError("OpenClaw export must be a JSON list or an object with a listings list.")

        return [self._row_to_listing(row) for row in rows if isinstance(row, dict)]

    def _row_to_listing(self, row: dict[str, Any]) -> Listing:
        company = self._string(row, "company", "employer", "organization") or "Unknown"
        role = self._string(row, "role", "title", "job_title", "position") or "Unknown role"
        location = self._string(row, "location", "city") or ""
        url_candidates = self._url_candidates(row)
        apply_url, canonical_url, alternate_urls = select_best_url(url_candidates)
        original_url = self._string(row, "apply_url", "url", "link", "application_url", "source_url", "discovered_url") or ""
        source_url = self._string(row, "source_url", "source", "discovered_url", "result_url") or original_url
        description = self._string(row, "description", "snippet", "summary") or ""
        posted_at = self._string(row, "posted_at", "posted", "date", "age") or None
        cycle = self._string(row, "cycle", "term", "season") or ""
        source_job_id = self._string(row, "source_job_id", "id", "job_id")

        if not source_job_id:
            source_job_id = hashlib.md5(
                f"{company}-{role}-{location}-{apply_url}".lower().encode("utf-8")
            ).hexdigest()[:16]

        return Listing(
            source="openclaw",
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
                "openclaw_export": str(self.export_path),
                "url_candidates": url_candidates,
                **row,
            },
        )

    def _string(self, row: dict[str, Any], *keys: str) -> str:
        for key in keys:
            value = row.get(key)
            if value is not None:
                return str(value).strip()
        return ""

    def _url_candidates(self, row: dict[str, Any]) -> list[str]:
        candidates: list[str] = []
        for key in (
            "direct_apply_url",
            "apply_url",
            "application_url",
            "posting_url",
            "job_url",
            "canonical_url",
            "url",
            "link",
            "source_url",
            "discovered_url",
            "result_url",
        ):
            value = row.get(key)
            if isinstance(value, str):
                candidates.append(value)

        for key in ("alternate_urls", "alternates", "links", "urls"):
            value = row.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        candidates.append(item)
                    elif isinstance(item, dict):
                        for nested_key in ("direct_apply_url", "apply_url", "url", "href", "link"):
                            nested_value = item.get(nested_key)
                            if isinstance(nested_value, str):
                                candidates.append(nested_value)

        return candidates
