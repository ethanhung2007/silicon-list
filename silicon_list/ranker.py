from __future__ import annotations

import re
from typing import List, Optional

from silicon_list.models import Listing, ScoredListing
from silicon_list.pipeline.filtering import posted_age_days
from silicon_list.pipeline.link_validation import is_specific_job_posting_url
from silicon_list.pipeline.scoring import listing_tags, listing_type


SEMICONDUCTOR_COMPANIES: frozenset[str] = frozenset({
    "nvidia", "amd", "intel", "qualcomm", "apple", "broadcom", "marvell",
    "texas instruments", "analog devices", "micron", "globalfoundries", "tsmc",
    "samsung semiconductor", "samsung", "mediatek", "nxp", "infineon", "renesas",
    "synaptics", "arm", "cadence", "synopsys", "siemens eda", "anduril", "spacex",
    "tesla", "google", "amazon", "meta", "rivian",
})

PRIMARY_HW_KEYWORDS: tuple[str, ...] = (
    "asic", "rtl", "fpga", "verilog", "systemverilog", "vhdl", "firmware",
    "embedded", "verification", "design verification", "dv", "uvm",
    "physical design", "vlsi", "silicon", "semiconductor", "computer architecture",
    "eda", "analog", "mixed-signal", "mixed signal", "digital design",
    "signal integrity", "pcb",
)

SOFTWARE_ONLY_SIGNALS: tuple[str, ...] = (
    "frontend", "backend", "full stack", "full-stack", "fullstack",
    "react", "node.js", "nodejs", "django", "rails", "ios", "android", "mobile",
    "web developer", "ui/ux",
)

CLEARANCE_SIGNALS: tuple[str, ...] = (
    "clearance", "itar", "us person", "u.s. person", "us citizenship",
    "u.s. citizenship", "export control",
)

_DIRECT_ATS_RE = re.compile(
    r"(?:workdayjobs\.com|myworkdayjobs\.com"
    r"|boards\.greenhouse\.io|job-boards\.greenhouse\.io"
    r"|jobs\.lever\.co"
    r"|jobs\.ashbyhq\.com"
    r"|smartrecruiters\.com"
    r"|icims\.com"
    r"|oraclecloud\.com"
    r"|successfactors\.com)",
    re.IGNORECASE,
)

_US_TOKENS: frozenset[str] = frozenset({
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga",
    "hi", "id", "il", "in", "ia", "ks", "ky", "la", "me", "md",
    "ma", "mi", "mn", "ms", "mo", "mt", "ne", "nv", "nh", "nj",
    "nm", "ny", "nc", "nd", "oh", "ok", "or", "pa", "ri", "sc",
    "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv", "wi", "wy",
    "dc", "usa", "us", "united states", "remote",
})


def rank_listings(listings: List[Listing], config=None) -> List[ScoredListing]:
    """
    Score each listing 0–100 using the spec scoring table.

    Tiers:
      Tier 1 >= 75
      Tier 2 50–74
      Tier 3 25–49
      Tier 4 < 25  (suppressed from report)
    """
    results: List[ScoredListing] = []

    for lst in listings:
        score = _compute_score(lst)
        score = max(0, min(100, score))

        if score >= 75:
            tier = 1
        elif score >= 50:
            tier = 2
        elif score >= 25:
            tier = 3
        else:
            tier = 4  # suppressed

        meta = lst.raw_metadata or {}
        ltype = listing_type(lst)
        tags = listing_tags(lst, config) if config is not None else []
        lst.raw_metadata = {
            **meta,
            "listing_type": ltype,
            "tags": tags,
        }

        results.append(ScoredListing(listing=lst, score=score, tier=tier))

    return results


def _compute_score(lst: Listing) -> int:
    score = 0
    meta = lst.raw_metadata or {}
    url = (lst.apply_url or "").strip()
    text = f"{lst.role} {lst.description}".lower()
    role_lower = lst.role.lower()

    # +15: US location
    if _is_us_location(lst.location):
        score += 15

    # +20: Exact validated URL
    if is_specific_job_posting_url(url):
        score += 20

    # +10: Known semiconductor company
    company_lower = lst.company.lower()
    if any(sc in company_lower for sc in SEMICONDUCTOR_COMPANIES):
        score += 10

    # +10: Internship / co-op / new grad
    if _is_student_role(text, role_lower):
        score += 10

    # +10: Posted within 14 days
    age = posted_age_days(lst.posted_at)
    if age is not None and age <= 14:
        score += 10

    # +15: Title contains primary hardware keyword
    if any(kw in role_lower for kw in PRIMARY_HW_KEYWORDS):
        score += 15

    # +5: Has req ID
    req_id = (
        meta.get("req_id")
        or meta.get("requisition_id")
        or meta.get("job_req_id")
        or meta.get("req_id")
    )
    if req_id or _url_has_req_id(url):
        score += 5

    # +5: Source is direct ATS
    if _DIRECT_ATS_RE.search(url):
        score += 5

    # +10: Hermes-validated source
    if lst.source == "hermes" or bool(meta.get("hermes_source")):
        score += 10

    # Penalty: clearance required
    if any(sig in text for sig in CLEARANCE_SIGNALS):
        score -= 50

    # Penalty: software-only signals in title
    if any(sig in role_lower for sig in SOFTWARE_ONLY_SIGNALS):
        score -= 20

    # Penalty: broken/uncertain link
    validation_status = str(
        meta.get("validation_status") or meta.get("link_validation") or ""
    ).lower()
    if validation_status in ("uncertain", "broken", "invalid", "generic", "not_found"):
        score -= 15

    # Penalty: stale > 60 days
    if age is not None and age > 60:
        score -= 20

    return score


def _is_us_location(location: str) -> bool:
    lower = location.lower()
    words = {w.strip(",.") for w in lower.split()}
    # Also check for multi-word phrases
    return bool(words & _US_TOKENS) or "united states" in lower


def _is_student_role(text: str, role_lower: str) -> bool:
    student_tokens = ("intern", "co-op", "co op", "coop", "new grad", "new college grad")
    return any(tok in text for tok in student_tokens)


def _url_has_req_id(url: str) -> bool:
    from silicon_list.pipeline.link_validation import _url_has_req_id as _impl
    return _impl(url)
