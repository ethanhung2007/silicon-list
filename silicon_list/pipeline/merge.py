import hashlib
import re
from dataclasses import replace
from typing import Iterable

from silicon_list.models import Listing
from silicon_list.pipeline.normalize import select_best_url
from silicon_list.pipeline.link_validation import is_specific_job_posting_url


def merge_stage_listings(listings: Iterable[Listing]) -> list[Listing]:
    """Merge duplicate listings found across discovery stages without dropping metadata."""
    merged: dict[str, Listing] = {}

    for listing in listings:
        key = _merge_key(listing)
        existing_key = next(
            (
                candidate_key
                for candidate_key, candidate in merged.items()
                if _compatible_listing(candidate, listing)
            ),
            None,
        )
        if existing_key:
            key = existing_key

        existing = merged.get(key)
        if existing is None:
            merged[key] = _with_stage_metadata(listing)
        else:
            merged[key] = merge_listing_records(existing, listing)

    return list(merged.values())


def merge_listing_records(primary: Listing, incoming: Listing) -> Listing:
    urls = [
        primary.apply_url,
        primary.canonical_url,
        primary.source_url,
        primary.original_url,
        *primary.alternate_urls,
        incoming.apply_url,
        incoming.canonical_url,
        incoming.source_url,
        incoming.original_url,
        *incoming.alternate_urls,
    ]
    apply_url, canonical_url, alternate_urls = select_best_url(urls)

    raw_metadata = {
        **primary.raw_metadata,
        "merged_sources": sorted({
            *_metadata_sources(primary),
            *_metadata_sources(incoming),
        }),
        "merged_providers": sorted({primary.source, incoming.source}),
    }
    if incoming.raw_metadata:
        raw_metadata.setdefault("merged_records", [])
        raw_metadata["merged_records"].append(incoming.raw_metadata)

    return replace(
        primary,
        source=primary.source if primary.source == incoming.source else "merged",
        source_job_id=primary.source_job_id or incoming.source_job_id or _hash_key(apply_url),
        company=_prefer_longer(primary.company, incoming.company),
        role=_prefer_longer(primary.role, incoming.role),
        location=primary.location or incoming.location,
        apply_url=apply_url,
        original_url=primary.original_url or incoming.original_url,
        canonical_url=canonical_url,
        source_url=primary.source_url or incoming.source_url,
        alternate_urls=alternate_urls,
        description=_prefer_longer(primary.description, incoming.description),
        posted_at=primary.posted_at or incoming.posted_at,
        cycle=primary.cycle or incoming.cycle,
        raw_metadata=raw_metadata,
    )


def _with_stage_metadata(listing: Listing) -> Listing:
    raw_metadata = {
        **listing.raw_metadata,
        "merged_sources": sorted({_metadata_source(listing)}),
    }
    return replace(listing, raw_metadata=raw_metadata)


def _merge_key(listing: Listing) -> str:
    url = (listing.canonical_url or listing.apply_url or listing.source_url).strip().lower()
    if _looks_specific_url(url):
        return f"url:{url}"

    company = _normalize_text(listing.company)
    role = _normalize_role(listing.role)
    if company and role:
        return f"role:{company}:{role}"

    return f"src:{listing.source}:{listing.source_job_id or _hash_key(url)}"


def _looks_specific_url(url: str) -> bool:
    return is_specific_job_posting_url(url)


def _normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _normalize_role(value: str) -> str:
    text = _normalize_text(value)
    text = re.sub(r"\b(?:summer|fall|spring|internship|intern|co op|coop|co-op|2026|2027)\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _prefer_longer(left: str, right: str) -> str:
    left = left or ""
    right = right or ""
    return right if len(right) > len(left) else left


def _metadata_source(listing: Listing) -> str:
    return str(listing.raw_metadata.get("stage") or listing.source)


def _metadata_sources(listing: Listing) -> set[str]:
    sources = listing.raw_metadata.get("merged_sources")
    if isinstance(sources, list):
        return {str(source) for source in sources}
    return {_metadata_source(listing)}


def _compatible_listing(left: Listing, right: Listing) -> bool:
    left_company = _normalize_text(left.company)
    right_company = _normalize_text(right.company)
    if not left_company or left_company != right_company:
        return False

    left_role = _normalize_role(left.role)
    right_role = _normalize_role(right.role)
    if not left_role or not right_role:
        return False

    return left_role in right_role or right_role in left_role


def _hash_key(value: str) -> str:
    return hashlib.md5(value.encode("utf-8")).hexdigest()[:16]
