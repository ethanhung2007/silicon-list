import hashlib
import json
from pathlib import Path
from typing import Any, List

from silicon_list.models import Listing
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
        apply_url = self._string(row, "apply_url", "url", "link", "application_url") or ""
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
            description=description,
            posted_at=posted_at,
            cycle=cycle,
            raw_metadata={"openclaw_export": str(self.export_path), **row},
        )

    def _string(self, row: dict[str, Any], *keys: str) -> str:
        for key in keys:
            value = row.get(key)
            if value is not None:
                return str(value).strip()
        return ""
