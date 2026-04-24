import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlparse

from silicon_list.models import Listing


EXACT_POSTING_PATTERNS = [
    re.compile(r"(?:boards|job-boards)\.greenhouse\.io/[^/?#]+/jobs/\d+", re.IGNORECASE),
    re.compile(r"greenhouse\.io/[^/?#]+/jobs/\d+", re.IGNORECASE),
    re.compile(r"greenhouse\.io/.+[?&]gh_jid=\d+", re.IGNORECASE),
    re.compile(r"jobs\.lever\.co/[^/?#]+/[^/?#]+", re.IGNORECASE),
    re.compile(r"jobs\.ashbyhq\.com/[^/?#]+/[0-9a-f-]{12,}", re.IGNORECASE),
    re.compile(r"ashbyhq\.com/.*/jobs?/[^/?#]+", re.IGNORECASE),
    re.compile(r"(?:my)?workdayjobs\.com/.*/job/", re.IGNORECASE),
    re.compile(r"smartrecruiters\.com/[^/?#]+/\d+", re.IGNORECASE),
    re.compile(r"icims\.com/jobs/\d+", re.IGNORECASE),
    re.compile(r"oraclecloud\.com/.*/job/", re.IGNORECASE),
    re.compile(r"successfactors\.com/.*/job/", re.IGNORECASE),
    re.compile(r"builtin\.com/job/", re.IGNORECASE),
    re.compile(r"linkedin\.com/jobs/view/(?:[^/?#]*-)?\d+", re.IGNORECASE),
    re.compile(r"indeed\.com/viewjob\?.*[?&]?jk=[a-z0-9]+", re.IGNORECASE),
    re.compile(r"indeed\.com/jobs/view/", re.IGNORECASE),
    re.compile(r"glassdoor\.com/job-listing/", re.IGNORECASE),
    re.compile(r"(?:app\.)?joinhandshake\.com/stu/jobs/\d+", re.IGNORECASE),
    re.compile(r"simplify\.jobs/p/[^/?#]+", re.IGNORECASE),
]

GENERIC_URL_PATTERNS = [
    re.compile(r"/(?:en-us/|en/|us/)?(?:careers?|jobs?|internships?)/?(?:$|[?#])", re.IGNORECASE),
    re.compile(r"/(?:careers?|jobs?)/(?:search|students|university|early-careers|internships?)/?(?:$|[?#])", re.IGNORECASE),
    re.compile(r"(?:linkedin|indeed|glassdoor)\.com/jobs/search", re.IGNORECASE),
    re.compile(r"(?:app\.)?joinhandshake\.com/stu/(?:postings|jobs)(?:$|[?#])", re.IGNORECASE),
    re.compile(r"careers\.smartrecruiters\.com/[^/?#]+/?(?:$|[?#])", re.IGNORECASE),
    re.compile(r"jobs\.lever\.co/[^/?#]+/?(?:$|[?#])", re.IGNORECASE),
    re.compile(r"(?:boards|job-boards)\.greenhouse\.io/[^/?#]+/?(?:$|[?#])", re.IGNORECASE),
    re.compile(r"jobs\.ashbyhq\.com/[^/?#]+/?(?:$|[?#])", re.IGNORECASE),
]

GENERIC_HOSTS = {
    "applybolt.app",
}

VALIDATION_SUCCESS_VALUES = {
    "open",
    "valid",
    "validated",
    "verified",
    "active",
    "http_200",
    "ok",
}

VALIDATION_FAILURE_VALUES = {
    "closed",
    "expired",
    "broken",
    "invalid",
    "generic",
    "not_found",
    "redirect_loop",
    "blocked",
}


@dataclass(frozen=True)
class LinkValidationResult:
    valid: bool
    reason: str
    confidence_bonus: int = 0


def validate_listing_link(listing: Listing) -> LinkValidationResult:
    """Validate that the publishable URL is an exact posting, not a generic search page."""
    url = (listing.apply_url or listing.canonical_url or "").strip()
    if not url:
        return LinkValidationResult(False, "missing_apply_url")

    lower = url.lower()
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")

    if host in GENERIC_HOSTS:
        return LinkValidationResult(False, "generic_job_collection")

    metadata_result = _metadata_validation_result(listing)
    if metadata_result is not None and not metadata_result.valid:
        return metadata_result

    if any(pattern.search(lower) for pattern in GENERIC_URL_PATTERNS):
        return LinkValidationResult(False, "generic_or_search_url")

    if any(pattern.search(lower) for pattern in EXACT_POSTING_PATTERNS):
        bonus = 12 if metadata_result and metadata_result.valid else 8
        return LinkValidationResult(True, "exact_posting_url", bonus)

    if _has_req_id(url, listing):
        return LinkValidationResult(True, "company_posting_with_req_id", 6)

    if metadata_result is not None and metadata_result.valid:
        return metadata_result

    return LinkValidationResult(False, "not_exact_posting_url")


def is_specific_job_posting_url(url: str) -> bool:
    lower = url.lower()
    return any(pattern.search(lower) for pattern in EXACT_POSTING_PATTERNS) or _url_has_req_id(url)


def is_generic_url(url: str) -> bool:
    lower = url.lower()
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    return host in GENERIC_HOSTS or any(pattern.search(lower) for pattern in GENERIC_URL_PATTERNS)


def _metadata_validation_result(listing: Listing) -> LinkValidationResult | None:
    metadata = listing.raw_metadata or {}
    values = [
        metadata.get("validation_status"),
        metadata.get("link_status"),
        metadata.get("page_status"),
        metadata.get("status"),
    ]
    normalized = {str(value).strip().lower() for value in values if value is not None}

    if normalized & VALIDATION_FAILURE_VALUES:
        return LinkValidationResult(False, f"metadata_{sorted(normalized & VALIDATION_FAILURE_VALUES)[0]}")

    if bool(metadata.get("expired")) or bool(metadata.get("closed")):
        return LinkValidationResult(False, "metadata_expired_or_closed")

    success = bool(normalized & VALIDATION_SUCCESS_VALUES)
    http_status = metadata.get("http_status") or metadata.get("status_code")
    if http_status is not None:
        try:
            if int(http_status) != 200:
                return LinkValidationResult(False, "metadata_non_200")
            success = True
        except (TypeError, ValueError):
            pass

    if success:
        has_title = _metadata_bool(metadata, "title_found", "contains_job_title", "page_contains_title")
        has_apply = _metadata_bool(metadata, "apply_button_found", "has_apply_button")
        if has_title is False:
            return LinkValidationResult(False, "metadata_missing_title")
        if has_apply is False:
            return LinkValidationResult(False, "metadata_missing_apply_button")
        return LinkValidationResult(True, "metadata_validated", 12)

    return None


def _metadata_bool(metadata: dict, *keys: str) -> bool | None:
    for key in keys:
        if key in metadata:
            return bool(metadata[key])
    return None


def _has_req_id(url: str, listing: Listing) -> bool:
    metadata = listing.raw_metadata or {}
    req_id = metadata.get("requisition_id") or metadata.get("req_id") or metadata.get("job_req_id")
    return bool(req_id) or _url_has_req_id(url)


def _url_has_req_id(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.lower()
    if re.search(r"\b(?:jr|req|r|job)[-_]?\d{4,}\b", path, re.IGNORECASE):
        return True
    if re.search(r"[_/-](?:jr|req)?\d{5,}(?:$|[/?#_-])", path, re.IGNORECASE):
        return True
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if key.lower() in {"jobid", "job_id", "reqid", "req_id", "job", "jid"} and value:
            return True
    return False
