import datetime
import re
from typing import List, Tuple
from silicon_list.models import Listing
from silicon_list.config import Config
from silicon_list.pipeline.link_validation import (
    is_generic_url,
    is_specific_job_posting_url,
    validate_listing_link,
)

_US_STATE_ABBREVS = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
}

_US_STATE_NAMES = {
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana",
    "maine", "maryland", "massachusetts", "michigan", "minnesota",
    "mississippi", "missouri", "montana", "nebraska", "nevada",
    "new hampshire", "new jersey", "new mexico", "new york",
    "north carolina", "north dakota", "ohio", "oklahoma", "oregon",
    "pennsylvania", "rhode island", "south carolina", "south dakota",
    "tennessee", "texas", "utah", "vermont", "virginia", "washington",
    "west virginia", "wisconsin", "wyoming", "district of columbia",
}

_NON_US_PATTERN = re.compile(
    r"\b(?:"
    r"canada|ontario|british columbia|alberta|quebec|manitoba|saskatchewan|"
    r"nova scotia|new brunswick|"
    r"united kingdom|u\.k\.|england|scotland|wales|"
    r"germany|france|ireland|netherlands|sweden|denmark|norway|finland|"
    r"switzerland|austria|belgium|spain|italy|poland|czech republic|"
    r"india|china|japan|taiwan|south korea|singapore|"
    r"australia|new zealand|brazil|mexico|israel|"
    r"amsterdam|london|toronto|vancouver|munich|berlin|paris|dublin|"
    r"stockholm|oslo|copenhagen|bangalore|bengaluru|hyderabad|pune|"
    r"tel aviv|sydney|melbourne"
    r")\b",
    re.IGNORECASE,
)


def is_us_location(location: str) -> bool:
    """
    Returns True when the location is US-based or genuinely unknown.
    Returns False only when a clearly non-US location is detected.
    """
    if not location or not location.strip():
        return True  # unknown → keep

    loc_lower = location.strip().lower()

    # Plain "Remote" or "Remote (US)" — keep
    if re.match(r"^remote\b", loc_lower):
        # Only exclude if a non-US country is also mentioned
        return not _NON_US_PATTERN.search(location)

    # Explicit non-US indicator → exclude
    if _NON_US_PATTERN.search(location):
        return False

    # "USA" / "United States" / "US" → keep
    if re.search(r"\b(?:usa|united states|u\.s\.a?\.)\b", loc_lower):
        return True

    # "City, ST" where ST is a US state abbreviation → keep
    parts = [p.strip() for p in location.split(",")]
    for part in reversed(parts):
        token = part.strip().upper().split()[0] if part.strip() else ""
        if token in _US_STATE_ABBREVS:
            return True
        if token in ("USA", "US"):
            return True

    # Full US state name present → keep
    if any(state in loc_lower for state in _US_STATE_NAMES):
        return True

    # Multiple / nationwide / flexible → keep
    if re.search(r"\b(?:multiple|various|flexible|nationwide)\b", loc_lower):
        return True

    # Can't determine — keep conservatively
    return True

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

BAD_APPLY_URL_PATTERNS = [
    re.compile(r"/apply/(?:autofillWithResume|useMyLastApplication)/?$", re.IGNORECASE),
    re.compile(r"linkedin\.com/jobs/search", re.IGNORECASE),
    re.compile(r"indeed\.com/jobs(?:/)?(?:$|[?#])", re.IGNORECASE),
    re.compile(r"indeed\.com/career", re.IGNORECASE),
    re.compile(r"glassdoor\.com/(?:Job|job-search|Jobs)(?:/)?(?:$|[?#])", re.IGNORECASE),
    re.compile(r"glassdoor\.com/Job/jobs\.htm", re.IGNORECASE),
    re.compile(r"(?:app\.)?joinhandshake\.com/stu/postings(?:$|[?#])", re.IGNORECASE),
    re.compile(r"ev\.careers/jobs/", re.IGNORECASE),
    re.compile(r"gradconnection\.com/", re.IGNORECASE),
    re.compile(r"careers\.smartrecruiters\.com/[^/?#]+/?(?:$|[?#])", re.IGNORECASE),
    re.compile(r"/about/job-post(?:$|[?#])", re.IGNORECASE),
    re.compile(r"/career-details/?(?:$|[?#])", re.IGNORECASE),
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
    """Returns true for broad OpenClaw/Cowork results that are not specific job postings."""
    if listing.source not in ("openclaw", "cowork"):
        return False

    role_lower = listing.role.lower()
    text_lower = f"{listing.role} {listing.description}".lower()

    if any(phrase in text_lower for phrase in GENERIC_OPENCLAW_ROLE_PHRASES):
        return True
    if is_generic_url(listing.apply_url):
        return True
    if not is_specific_job_posting_url(listing.apply_url):
        return True

    generic_role = role_lower in {
        "hardware engineering intern",
        "hardware engineering internship",
        "hardware intern",
        "internships",
    }
    has_specific_url = is_specific_job_posting_url(listing.apply_url)
    return generic_role and not has_specific_url

def has_bad_apply_url(listing: Listing) -> bool:
    url_lower = listing.apply_url.lower()
    return any(pattern.search(url_lower) for pattern in BAD_APPLY_URL_PATTERNS)

def posted_age_days(posted_at: str | None, today: datetime.date | None = None) -> int | None:
    if not posted_at:
        return None

    today = today or datetime.date.today()
    text = posted_at.strip().lower()
    if not text:
        return None
    if text in {"today", "just posted", "new"}:
        return 0
    if text == "yesterday":
        return 1

    match = re.fullmatch(r"(\d+)\s*d(?:ays?)?", text)
    if match:
        return int(match.group(1))
    match = re.fullmatch(r"(\d+)\s*w(?:eeks?)?", text)
    if match:
        return int(match.group(1)) * 7
    match = re.fullmatch(r"(\d+)\s*mo(?:nths?)?", text)
    if match:
        return int(match.group(1)) * 30

    for fmt in ("%Y-%m-%d", "%b %d, %Y", "%B %d, %Y"):
        try:
            posted_date = datetime.datetime.strptime(posted_at.strip(), fmt).date()
            return max((today - posted_date).days, 0)
        except ValueError:
            pass

    for fmt in ("%b %d", "%B %d"):
        try:
            parsed = datetime.datetime.strptime(posted_at.strip(), fmt)
            posted_date = datetime.date(today.year, parsed.month, parsed.day)
            if posted_date > today:
                posted_date = datetime.date(today.year - 1, parsed.month, parsed.day)
            return max((today - posted_date).days, 0)
        except ValueError:
            pass

    return None

def is_too_old(listing: Listing, config: Config) -> bool:
    max_age = getattr(config, "max_listing_age_days", 0)
    if not max_age:
        return False

    age = posted_age_days(listing.posted_at)
    if age is None:
        return not getattr(config, "keep_unknown_posted_at", True)
    return age > max_age

def has_wrong_explicit_cycle(listing: Listing, config: Config) -> bool:
    text = f"{listing.role} {listing.description} {listing.cycle}".lower()
    if not re.search(r"\b20\d{2}\b", text):
        return False
    target_cycles = [cycle.lower() for cycle in getattr(config, "target_cycle_keywords", [])]
    return not any(cycle in text for cycle in target_cycles)

def filter_listings(listings: List[Listing], config: Config) -> Tuple[List[Listing], List[Tuple[Listing, str]]]:
    """
    Filters listings.
    Returns a tuple of (kept_listings, skipped_listings_with_reasons).
    """
    kept = []
    skipped = []
    
    # Pre-compile lowercased rules
    target_keywords = [kw.lower() for kw in config.target_keywords]
    
    senior_keywords = ["senior", "sr", "principal", "staff", "lead", "manager", "director", "full-time", "full time", "postgrad"]
    
    for lst in listings:
        text_to_search = f"{lst.role} {lst.description}".lower()
        role_lower = lst.role.lower()
        
        # 1. Hard exclusions
        if has_hard_exclusion(text_to_search, config):
            skipped.append((lst, "hard_exclusion"))
            continue

        if is_too_old(lst, config):
            skipped.append((lst, "too_old"))
            continue

        if has_wrong_explicit_cycle(lst, config):
            skipped.append((lst, "wrong_cycle"))
            continue

        link_validation = validate_listing_link(lst)
        if not link_validation.valid:
            skipped.append((lst, link_validation.reason))
            continue

        if lst.source in ("openclaw", "cowork"):
            is_student_role = (
                "intern" in role_lower
                or "co-op" in role_lower
                or "coop" in role_lower
                or "new grad" in role_lower
                or "new college grad" in role_lower
                or "graduate" in role_lower
            )
            is_student_desc = (
                "intern" in text_to_search
                or "co-op" in text_to_search
                or "coop" in text_to_search
                or "new grad" in text_to_search
                or "new college grad" in text_to_search
            )
            if not is_student_role and not is_student_desc:
                skipped.append((lst, "not_student_role"))
                continue

        # US-only filter
        if getattr(config, "require_us_locations", True) and not is_us_location(lst.location):
            skipped.append((lst, "non_us_location"))
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
