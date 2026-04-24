import re
from typing import List
from html import unescape
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlparse, urlunparse
from silicon_list.models import Listing

TRACKING_PARAM_PREFIXES = ("utm_",)
TRACKING_PARAM_NAMES = {
    "ref",
    "src",
    "source",
    "gh_src",
    "gh_jid",
    "lever-source",
    "isd_source",
    "tracking",
    "trk",
    "trkEmail",
    "redirectedFrom",
}

REDIRECT_PARAM_NAMES = {
    "url",
    "u",
    "q",
    "target",
    "redirect",
    "redirect_url",
    "redirectUrl",
    "destination",
    "dest",
}

WRAPPER_HOST_TOKENS = (
    "google.",
    "bing.",
    "duckduckgo.",
    "linkedin.com/safety/go",
    "indeed.com/rc/clk",
    "glassdoor.com/partner/jobListing.htm",
    "simplify.jobs/redirect",
)

def normalize_listings(listings: List[Listing]) -> List[Listing]:
    """Normalizes string fields in listings for consistency."""
    normalized = []
    
    for lst in listings:
        company = re.sub(r'\s+', ' ', lst.company).strip()
        role = re.sub(r'\s+', ' ', lst.role).strip()
        location = re.sub(r'\s+', ' ', lst.location).strip()
        
        selected_url, canonical_url, alternates = select_best_url(
            [
                lst.apply_url,
                lst.canonical_url,
                *lst.alternate_urls,
                lst.source_url,
                lst.original_url,
            ]
        )
        original_url = lst.original_url or lst.apply_url
        source_url = normalize_apply_url(lst.source_url) if lst.source_url else normalize_apply_url(original_url)
        
        normalized.append(Listing(
            source=lst.source,
            source_job_id=lst.source_job_id,
            company=company,
            role=role,
            location=location,
            apply_url=selected_url,
            original_url=normalize_apply_url(original_url),
            canonical_url=canonical_url,
            source_url=source_url,
            alternate_urls=alternates,
            description=lst.description,
            posted_at=lst.posted_at,
            cycle=lst.cycle.strip(),
            tools_found=lst.tools_found,
            raw_metadata=lst.raw_metadata
        ))
        
    return normalized

def normalize_apply_url(url: str) -> str:
    """Removes tracking params and rewrites known apply-action URLs to stable job pages."""
    url = _clean_url_text(url)
    url = unwrap_redirect_url(url)

    if url and not re.match(r"^[a-z][a-z0-9+.-]*://", url, flags=re.IGNORECASE):
        if url.startswith("//"):
            url = "https:" + url
        elif "." in url.split("/", 1)[0]:
            url = "https://" + url

    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return url

    path = parsed.path
    path = re.sub(r"/{2,}", "/", path)
    path = re.sub(r"/apply/(?:autofillWithResume|applyManually|useMyLastApplication)/?$", "", path)
    path = re.sub(r"/application/?$", "", path)

    params = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith(TRACKING_PARAM_PREFIXES)
        and key.lower() not in TRACKING_PARAM_NAMES
    ]

    safe_path = quote(unquote(path), safe="/:@-._~!$&'()*+,;=%")
    return urlunparse(parsed._replace(path=safe_path, query=urlencode(params), fragment=""))

def select_best_url(urls: list[str]) -> tuple[str, str, list[str]]:
    """Returns the best primary URL, its canonical form, and remaining normalized alternates."""
    normalized: list[str] = []
    seen: set[str] = set()
    for url in urls:
        candidate = normalize_apply_url(url)
        if not candidate:
            continue
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(candidate)

    if not normalized:
        return "", "", []

    primary = sorted(normalized, key=_url_priority)[0]
    alternates = [url for url in normalized if url != primary]
    return primary, primary, alternates

def unwrap_redirect_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return url

    host_path = f"{parsed.netloc.lower()}{parsed.path.lower()}"
    if not any(token in host_path for token in WRAPPER_HOST_TOKENS):
        return url

    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if key in REDIRECT_PARAM_NAMES and value.startswith(("http://", "https://")):
            return _clean_url_text(value)
    return url

def _clean_url_text(url: str) -> str:
    url = unescape(str(url or "")).strip()
    url = url.strip(" \t\r\n<>\"'")
    url = re.sub(r"[\]\),.;:]+$", "", url)
    return url

def _url_priority(url: str) -> tuple[int, int]:
    lower = url.lower()
    exact_direct_patterns = (
        r"(?:boards|job-boards)\.greenhouse\.io/[^/?#]+/jobs/\d+",
        r"jobs\.lever\.co/[^/?#]+/[^/?#]+",
        r"jobs\.ashbyhq\.com/[^/?#]+/[0-9a-f-]{20,}",
        r"(?:my)?workdayjobs\.com/.*/job/",
        r"smartrecruiters\.com/[^/?#]+/\d+",
        r"icims\.com/jobs/\d+",
        r"oraclecloud\.com/.*/job/",
        r"successfactors\.com/.*/job/",
    )
    exact_board_patterns = (
        r"linkedin\.com/jobs/view/(?:[^/?#]*-)?\d+",
        r"indeed\.com/viewjob\?.*[?&]?jk=[a-z0-9]+",
        r"glassdoor\.com/job-listing/",
        r"(?:app\.)?joinhandshake\.com/stu/jobs/\d+",
        r"simplify\.jobs/p/",
    )
    source_or_careers_tokens = (
        "boards.greenhouse.io/",
        "job-boards.greenhouse.io/",
        "jobs.lever.co/",
        "jobs.ashbyhq.com/",
        "careers",
        "/jobs",
        "/job",
        "/apply",
    )

    if any(re.search(pattern, lower) for pattern in exact_direct_patterns):
        bucket = 0
    elif any(re.search(pattern, lower) for pattern in exact_board_patterns):
        bucket = 1
    elif any(token in lower for token in source_or_careers_tokens):
        bucket = 2
    else:
        bucket = 3
    return bucket, len(url)
