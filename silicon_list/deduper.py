from __future__ import annotations

import datetime
import logging
import re
from difflib import SequenceMatcher
from typing import List

from silicon_list.models import Listing

logger = logging.getLogger(__name__)

_TITLE_SIMILARITY_THRESHOLD = 0.85


class Deduper:
    """
    Intra-batch deduplication using URL matching and fuzzy title comparison.
    Complements pipeline/dedupe.py (which handles cross-run seen.json dedup).
    Merges duplicates within a single fetch batch, keeping the best entry.
    Logs every merge to the silicon_list logger.
    """

    def deduplicate(self, listings: List[Listing]) -> List[Listing]:
        """Return deduplicated list, keeping the best entry per group."""
        groups: list[list[Listing]] = []

        for listing in listings:
            placed = False
            for group in groups:
                if _same_group(group[0], listing):
                    group.append(listing)
                    placed = True
                    break
            if not placed:
                groups.append([listing])

        result: list[Listing] = []
        for group in groups:
            if len(group) == 1:
                result.append(group[0])
                continue

            best = _pick_best(group)
            for duplicate in group:
                if duplicate is not best:
                    logger.info(
                        "Deduped '%s / %s' into '%s / %s' (url=%s)",
                        duplicate.company,
                        duplicate.role,
                        best.company,
                        best.role,
                        best.apply_url,
                    )
            result.append(best)

        return result


def _same_group(a: Listing, b: Listing) -> bool:
    url_a = (a.apply_url or "").strip().lower()
    url_b = (b.apply_url or "").strip().lower()
    if url_a and url_a == url_b:
        return True

    if _normalize_company(a.company) != _normalize_company(b.company):
        return False

    loc_a = (a.location or "").lower().strip()
    loc_b = (b.location or "").lower().strip()
    if loc_a and loc_b and loc_a != loc_b:
        return False

    ratio = SequenceMatcher(None, _normalize_role(a.role), _normalize_role(b.role)).ratio()
    return ratio > _TITLE_SIMILARITY_THRESHOLD


def _pick_best(group: List[Listing]) -> Listing:
    """Pick the listing with the highest validation confidence and most recent posted_at."""

    def sort_key(lst: Listing) -> tuple:
        meta = lst.raw_metadata or {}
        confidence = float(meta.get("validation_confidence", 0))
        posted = lst.posted_at or ""
        try:
            date_val = datetime.date.fromisoformat(posted)
        except (ValueError, TypeError):
            date_val = datetime.date.min
        return (confidence, date_val)

    return max(group, key=sort_key)


def _normalize_company(value: str) -> str:
    value = value.lower()
    value = re.sub(r"\b(?:inc|llc|ltd|corp|corporation|company|co)\b\.?", " ", value)
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def _normalize_role(value: str) -> str:
    value = value.lower()
    value = re.sub(r"\b(?:summer|fall|spring|winter|internship|intern|co op|coop|co-op|new grad|new college grad|2026|2027)\b", " ", value)
    return re.sub(r"[^a-z0-9]+", " ", value).strip()
