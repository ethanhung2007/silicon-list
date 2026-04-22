import re
from typing import List, Tuple
from silicon_list.models import Listing
from silicon_list.config import Config

ELIGIBILITY_EXCLUSION_PATTERNS = [
    re.compile(r"\bclearance\b", re.IGNORECASE),
    re.compile(r"\bitar\b", re.IGNORECASE),
    re.compile(r"\bu\.?s\.?\s+persons?\b", re.IGNORECASE),
    re.compile(r"\bunited\s+states\s+persons?\b", re.IGNORECASE),
    re.compile(r"\bu\.?s\.?\s+citizenship\b", re.IGNORECASE),
    re.compile(r"\bus\s+citizenship\b", re.IGNORECASE),
    re.compile(r"\bexport\s+control(?:led|s| restrictions?)?\b", re.IGNORECASE),
    re.compile(r"🇺🇸"),
]

GENERIC_OPENCLAW_URL_PATTERNS = [
    re.compile(r"/careers?/?(?:$|[?#])", re.IGNORECASE),
    re.compile(r"/jobs?/?(?:$|[?#])", re.IGNORECASE),
    re.compile(r"/search/?(?:$|[?#])", re.IGNORECASE),
    re.compile(r"/internships?/?(?:$|[?#])", re.IGNORECASE),
    re.compile(r"/(?:jobs?|careers?)/search", re.IGNORECASE),
    re.compile(r"/(?:jobs?|careers?)/internships?", re.IGNORECASE),
    re.compile(r"optiver\.com/working-at-optiver/career-opportunities/", re.IGNORECASE),
]

GENERIC_OPENCLAW_DOMAINS = [
    "applybolt.app",
]

GENERIC_OPENCLAW_ROLE_PHRASES = [
    "hardware engineering internships",
    "internship program",
    "internships program",
    "early careers",
    "student careers",
]

def has_hard_exclusion(text: str, config: Config) -> bool:
    """Returns true when a listing has eligibility restrictions we should skip."""
    text_lower = text.lower()
    if any(ex.lower() in text_lower for ex in config.hard_exclusions):
        return True
    return any(pattern.search(text) for pattern in ELIGIBILITY_EXCLUSION_PATTERNS)

def is_generic_openclaw_listing(listing: Listing) -> bool:
    """Returns true for broad OpenClaw results that are not specific job postings."""
    if listing.source != "openclaw":
        return False

    url_lower = listing.apply_url.lower()
    role_lower = listing.role.lower()
    text_lower = f"{listing.role} {listing.description}".lower()

    if any(domain in url_lower for domain in GENERIC_OPENCLAW_DOMAINS):
        return True
    if any(phrase in text_lower for phrase in GENERIC_OPENCLAW_ROLE_PHRASES):
        return True
    if any(pattern.search(url_lower) for pattern in GENERIC_OPENCLAW_URL_PATTERNS):
        return True

    generic_role = role_lower in {
        "hardware engineering intern",
        "hardware engineering internship",
        "hardware intern",
        "internships",
    }
    has_specific_url = any(token in url_lower for token in ["/job/", "/jobs/", "jobid=", "gh_jid=", "lever.co", "greenhouse.io", "ashbyhq.com", "workdayjobs.com"])
    return generic_role and not has_specific_url

def filter_listings(listings: List[Listing], config: Config) -> Tuple[List[Listing], List[Tuple[Listing, str]]]:
    """
    Filters listings.
    Returns a tuple of (kept_listings, skipped_listings_with_reasons).
    """
    kept = []
    skipped = []
    
    # Pre-compile lowercased rules
    target_keywords = [kw.lower() for kw in config.target_keywords]
    
    senior_keywords = ["senior", "sr", "principal", "staff", "lead", "manager", "director", "full-time", "full time", "postgrad", "new grad", "new college grad", "graduate"]
    
    for lst in listings:
        text_to_search = f"{lst.role} {lst.description}".lower()
        role_lower = lst.role.lower()
        
        # 1. Hard exclusions
        if has_hard_exclusion(text_to_search, config):
            skipped.append((lst, "hard_exclusion"))
            continue

        if is_generic_openclaw_listing(lst):
            skipped.append((lst, "generic_listing"))
            continue

        if lst.source == "openclaw":
            is_student_role = "intern" in role_lower or "co-op" in role_lower or "coop" in role_lower
            is_student_desc = "intern" in text_to_search or "co-op" in text_to_search or "coop" in text_to_search
            if not is_student_role and not is_student_desc:
                skipped.append((lst, "not_student_role"))
                continue
            
        # 2. Check if it's an internship or co-op
        # The role OR description should mention intern, internship, or co-op/coop.
        # But if the repo is specifically for internships (like Github Simplify), we might trust it.
        # Still, let's enforce it locally:
        is_student_role = "intern" in role_lower or "co-op" in role_lower or "coop" in role_lower or "student" in role_lower
        is_student_desc = "intern" in text_to_search or "co-op" in text_to_search or "coop" in text_to_search or "student" in text_to_search
        
        # We will keep if it's a student role OR if it comes from a trusted student source where title might just be "Hardware Engineer"
        # Since SimplifyJobs is exclusively internships, we should lean towards keeping. 
        # But let's check for "full-time" or senior explicitly.
        
        if any(snr in role_lower for snr in senior_keywords):
            skipped.append((lst, "senior_or_fulltime"))
            continue
            
        # 3. Irrelevance check
        # Must have at least one target keyword in title or description to be considered hardware/low-level
        has_hardware_keyword = any(kw in text_to_search for kw in target_keywords)
        if not has_hardware_keyword:
            skipped.append((lst, "irrelevant"))
            continue
            
        kept.append(lst)
        
    return kept, skipped
