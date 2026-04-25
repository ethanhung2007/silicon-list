from __future__ import annotations

import datetime
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, List

from silicon_list.models import Listing
from silicon_list.pipeline.normalize import select_best_url
from silicon_list.providers.base import BaseProvider, ProviderError

_DEFAULT_OUTPUT_PATH = Path.home() / ".silicon-list" / "openclaw-listings.json"
_STALENESS_HOURS = 6


class CoworkProvider(BaseProvider):
    """
    Runs a Claude research session (via the claude CLI) to browse the web for
    hardware internship listings, writes results to
    ~/.silicon-list/openclaw-listings.json, then parses and returns them.

    Set skip_run=True (or pass --skip-cowork-run) to skip launching claude and
    just reload the existing export file.
    """

    def __init__(self, config, output_path: Path | None = None, skip_run: bool = False):
        super().__init__(config)
        configured = getattr(config, "cowork_export_path", str(_DEFAULT_OUTPUT_PATH))
        self.output_path: Path = output_path or Path(configured).expanduser()
        self.skip_run = skip_run
        self.timeout: int = int(getattr(config, "cowork_timeout_seconds", 900))
        self.max_listings: int = int(getattr(config, "cowork_max_listings", 80))

    # ──────────────────────────────────────────────────────────────────────────
    # Public interface
    # ──────────────────────────────────────────────────────────────────────────

    def fetch_listings(self) -> List[Listing]:
        if not self.skip_run:
            self._run_cowork()

        if not self.output_path.exists():
            raise ProviderError(
                f"Cowork output not found at {self.output_path}. "
                "Run silicon-list with --skip-cowork-run to use an existing export, "
                "or ensure the claude CLI is installed and accessible."
            )

        mtime = datetime.datetime.fromtimestamp(self.output_path.stat().st_mtime)
        age_hours = (datetime.datetime.now() - mtime).total_seconds() / 3600
        if age_hours > _STALENESS_HOURS:
            print(
                f"[cowork] Warning: export is {age_hours:.0f}h old (> {_STALENESS_HOURS}h). "
                "Re-run to get fresh data.",
                file=sys.stderr,
            )

        try:
            with open(self.output_path) as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ProviderError(f"Cowork output is invalid JSON: {e}")
        except OSError as e:
            raise ProviderError(f"Could not read Cowork output: {e}")

        rows = data.get("listings", data) if isinstance(data, dict) else data
        if not isinstance(rows, list):
            raise ProviderError(
                "Cowork output must be a JSON object with a 'listings' key or a JSON array."
            )

        return [self._row_to_listing(row) for row in rows if isinstance(row, dict)]

    # ──────────────────────────────────────────────────────────────────────────
    # Claude invocation
    # ──────────────────────────────────────────────────────────────────────────

    def _run_cowork(self) -> None:
        """Launch claude with a web-research prompt; write JSON to self.output_path."""
        claude_bin = shutil.which("claude")
        if not claude_bin:
            print(
                "[cowork] claude CLI not found in PATH; loading existing export if present.",
                file=sys.stderr,
            )
            return

        prompt = self._build_prompt()
        cmd = [
            claude_bin,
            "--dangerously-skip-permissions",
            "-p",
            prompt,
        ]

        print(
            f"[cowork] Starting Claude research session (timeout: {self.timeout}s) …",
            file=sys.stderr,
        )
        try:
            result = subprocess.run(cmd, timeout=self.timeout)
            if result.returncode != 0:
                print(
                    f"[cowork] claude exited with code {result.returncode}; "
                    "using existing export if present.",
                    file=sys.stderr,
                )
        except subprocess.TimeoutExpired:
            print(
                f"[cowork] Research session timed out after {self.timeout}s; "
                "using partial results.",
                file=sys.stderr,
            )
        except Exception as e:
            print(f"[cowork] Unexpected error running claude: {e}", file=sys.stderr)

    def _build_prompt(self) -> str:
        queries = self.config.search_queries or []
        keywords = ", ".join(self.config.target_keywords[:20]) if self.config.target_keywords else ""
        exclusions = ", ".join(self.config.hard_exclusions[:8]) if self.config.hard_exclusions else ""
        output_file = str(self.output_path)
        max_listings = self.max_listings
        priority = ", ".join(self.config.priority_companies[:20]) if self.config.priority_companies else ""

        query_lines = "\n".join(f"  - {q}" for q in queries)
        return f"""You are an expert hardware job researcher. Your goal is to find as many currently open hardware engineering internship, co-op, and new-grad listings in the United States as possible for 2026-2027. Be thorough and systematic — more unique listings is better.

═══════════════════════════════════════
WHAT TO FIND
═══════════════════════════════════════
Roles in: FPGA, RTL, ASIC, design verification, firmware, embedded systems, physical design, analog/mixed-signal, EDA, silicon engineering, computer architecture, electrical engineering, signal integrity, semiconductor.

Level: internship, co-op, or new-grad only. US locations only (including US-based Remote).

Keywords to match: {keywords}

Exclude any listing mentioning: {exclusions}
Also exclude roles requiring US citizenship, security clearance, or ITAR eligibility.

═══════════════════════════════════════
PRIORITY COMPANIES (search these first)
═══════════════════════════════════════
{priority}

For each priority company: go directly to their careers site and search for hardware/firmware/silicon/FPGA/ASIC intern and co-op openings. Collect every matching open role.

═══════════════════════════════════════
SEARCH STRATEGY (run all of these)
═══════════════════════════════════════
STEP 1 — Priority company career portals (direct ATS searches):
  - Search each company's Greenhouse / Lever / Ashby / Workday / iCIMS portal
  - Filter by: intern, co-op, internship, hardware, firmware, FPGA, ASIC, RTL, silicon

STEP 2 — Run every search query below (do not skip any):
{query_lines}

STEP 3 — Job board sweeps:
  - Handshake: search hardware intern 2026, FPGA intern 2026, firmware intern 2026
  - Simplify (simplify.jobs): filter by hardware engineering, firmware, FPGA, ASIC
  - LinkedIn Jobs: hardware engineering intern 2026, ASIC verification intern
  - Indeed: FPGA intern 2026 United States, firmware intern summer 2026

STEP 4 — ATS portal direct searches:
  - boards.greenhouse.io: search fpga, asic, rtl, firmware, embedded, silicon
  - jobs.lever.co: same keywords
  - jobs.ashbyhq.com: same keywords
  - myworkdayjobs.com: search hardware intern, firmware intern, silicon intern

═══════════════════════════════════════
QUALITY REQUIREMENTS
═══════════════════════════════════════
Each listing MUST have:
1. A direct ATS application URL (Greenhouse, Lever, Ashby, Workday, SmartRecruiters, etc.)
   — NOT a search results page, NOT a careers landing page
2. A US location (city + state, or "Remote" for US-based remote roles)
3. The position must currently be open (check the page loads and shows an apply button)

If you find a careers landing page, click through to find the specific open role URL.

═══════════════════════════════════════
OUTPUT FORMAT
═══════════════════════════════════════
Write a JSON file to: {output_file}

Use exactly this structure (no extra keys required):
{{
  "listings": [
    {{
      "company": "Company Name",
      "role": "Exact Job Title from posting",
      "location": "City, ST  or  Remote",
      "apply_url": "https://exact-ats-url.com/job/12345",
      "description": "1-2 sentences: role focus and key skills/tools",
      "posted_at": "YYYY-MM-DD or relative like '3d' or 'today'",
      "cycle": "Summer 2026",
      "source_url": "URL where you found this listing"
    }}
  ]
}}

Target at least {max_listings} unique listings. Cast a wide net — it is better to return more listings than fewer. After completing your research, write all results to {output_file}.
"""

    # ──────────────────────────────────────────────────────────────────────────
    # Row parsing
    # ──────────────────────────────────────────────────────────────────────────

    def _row_to_listing(self, row: dict[str, Any]) -> Listing:
        company = self._str(row, "company", "employer", "organization") or "Unknown"
        role = self._str(row, "role", "title", "job_title", "position") or "Unknown role"
        location = self._str(row, "location", "city") or ""
        url_candidates = self._url_candidates(row)
        apply_url, canonical_url, alternate_urls = select_best_url(url_candidates)
        original_url = self._str(row, "apply_url", "url", "link", "application_url", "source_url", "discovered_url") or ""
        source_url = self._str(row, "source_url", "source", "discovered_url", "result_url") or original_url
        description = self._description(row)
        posted_at = self._str(row, "posted_at", "posted", "posted_date", "date", "age") or None
        cycle = self._str(row, "cycle", "term", "season") or ""
        source_job_id = self._str(row, "source_job_id", "id", "job_id")

        if not source_job_id:
            source_job_id = hashlib.md5(
                f"{company}-{role}-{location}-{apply_url}".lower().encode("utf-8")
            ).hexdigest()[:16]

        return Listing(
            source="cowork",
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
                "cowork_export": str(self.output_path),
                "url_candidates": url_candidates,
                **row,
            },
        )

    def _str(self, row: dict[str, Any], *keys: str) -> str:
        for key in keys:
            value = row.get(key)
            if value is not None:
                return str(value).strip()
        return ""

    def _description(self, row: dict[str, Any]) -> str:
        description = self._str(row, "description", "snippet", "summary")
        if description:
            return description

        pieces: list[str] = []
        for key in ("type", "employment_type"):
            value = self._str(row, key)
            if value:
                pieces.append(value)

        focus_areas = row.get("focus_areas") or row.get("keywords") or row.get("skills")
        if isinstance(focus_areas, list):
            areas = [str(item).strip() for item in focus_areas if item is not None and str(item).strip()]
            if areas:
                pieces.append(", ".join(areas))

        return ". ".join(pieces)

    def _url_candidates(self, row: dict[str, Any]) -> list[str]:
        candidates: list[str] = []
        for key in (
            "direct_apply_url", "apply_url", "application_url", "posting_url",
            "job_url", "canonical_url", "url", "link", "source_url",
            "discovered_url", "result_url",
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
                        for nested_key in (
                            "direct_apply_url", "apply_url", "application_url",
                            "posting_url", "job_url", "url", "href", "link",
                        ):
                            nested_value = item.get(nested_key)
                            if isinstance(nested_value, str):
                                candidates.append(nested_value)

        return candidates
