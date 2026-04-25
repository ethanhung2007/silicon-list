from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

import requests

from silicon_list.models import Listing
from silicon_list.pipeline.link_validation import is_generic_url


class ValidationStatus(str, Enum):
    VALID = "valid"
    INVALID = "invalid"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True)
class ValidationResult:
    status: ValidationStatus
    confidence: float  # 0.0–1.0
    final_url: str
    notes: str


_EXPIRY_SIGNALS = [
    "no longer accepting",
    "position filled",
    "requisition closed",
    "job is no longer available",
    "this job has expired",
    "this position has been filled",
    "posting has expired",
    "no longer available",
    "this job posting has been removed",
    "this posting has been removed",
]

_OPEN_SIGNALS = [
    "apply now",
    "apply for this job",
    "submit application",
    "submit your application",
    "start application",
    "apply to this job",
]


class ListingValidator:
    """
    Validates that a listing URL points to an actual open job posting.
    Does NOT use headless browsers — uses requests + heuristics only.
    Falls back gracefully on JS-heavy pages.
    """

    USER_AGENT = (
        "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0"
    )
    TIMEOUT = 10

    def validate(self, listing: Listing) -> ValidationResult:
        url = (listing.apply_url or "").strip()
        if not url:
            return ValidationResult(ValidationStatus.INVALID, 0.0, "", "no_url")

        if is_generic_url(url):
            return ValidationResult(ValidationStatus.INVALID, 0.0, url, "generic_url")

        try:
            resp = requests.get(
                url,
                headers={
                    "User-Agent": self.USER_AGENT,
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                },
                timeout=self.TIMEOUT,
                allow_redirects=True,
            )
        except requests.RequestException as exc:
            return ValidationResult(
                ValidationStatus.UNCERTAIN,
                0.3,
                url,
                f"request_failed:{type(exc).__name__}",
            )

        final_url = resp.url

        if resp.status_code >= 400:
            return ValidationResult(
                ValidationStatus.INVALID, 0.0, url, f"http_{resp.status_code}"
            )

        if resp.status_code == 200:
            if is_generic_url(final_url):
                return ValidationResult(
                    ValidationStatus.INVALID, 0.1, final_url, "redirected_to_generic"
                )

            body = resp.text
            body_lower = body.lower()

            # JS-heavy SPA: many script tags but almost no visible HTML structure
            visible_tags = (
                body.count("<p") + body.count("<h1") + body.count("<h2")
                + body.count("<h3") + body.count("<li") + body.count("<button")
                + body.count("<div") + body.count("<span")
            )
            is_js_heavy = body.count("<script") > 8 and visible_tags < 3
            if is_js_heavy:
                return ValidationResult(
                    ValidationStatus.UNCERTAIN, 0.5, final_url, "js_heavy_page"
                )

            # Expiry signals
            if any(sig in body_lower for sig in _EXPIRY_SIGNALS):
                return ValidationResult(
                    ValidationStatus.INVALID, 0.9, final_url, "expired_posting"
                )

            # Title keyword match against listing role
            role_tokens = [
                t for t in re.split(r"\W+", listing.role.lower()) if len(t) > 3
            ]
            has_title = bool(role_tokens) and any(tok in body_lower for tok in role_tokens[:4])

            # Apply button / form signal
            has_apply = any(sig in body_lower for sig in _OPEN_SIGNALS) or (
                "apply" in body_lower
                and any(
                    tag in body_lower
                    for tag in ('<form', '<button', 'type="submit"', "data-apply")
                )
            )

            if has_title and has_apply:
                confidence, notes = 0.9, "title_and_apply_found"
            elif has_title:
                return ValidationResult(
                    ValidationStatus.UNCERTAIN, 0.5, final_url, "title_found_without_apply"
                )
            elif has_apply:
                return ValidationResult(
                    ValidationStatus.UNCERTAIN, 0.5, final_url, "apply_found_without_title"
                )
            else:
                return ValidationResult(
                    ValidationStatus.UNCERTAIN, 0.4, final_url, "http_200_no_job_signal"
                )

            return ValidationResult(ValidationStatus.VALID, confidence, final_url, notes)

        return ValidationResult(
            ValidationStatus.UNCERTAIN, 0.3, final_url, f"http_{resp.status_code}"
        )
