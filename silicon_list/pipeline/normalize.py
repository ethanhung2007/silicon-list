import re
from typing import List
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
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
}

def normalize_listings(listings: List[Listing]) -> List[Listing]:
    """Normalizes string fields in listings for consistency."""
    normalized = []
    
    for lst in listings:
        company = re.sub(r'\s+', ' ', lst.company).strip()
        role = re.sub(r'\s+', ' ', lst.role).strip()
        location = re.sub(r'\s+', ' ', lst.location).strip()
        
        apply_url = normalize_apply_url(lst.apply_url)
        
        normalized.append(Listing(
            source=lst.source,
            source_job_id=lst.source_job_id,
            company=company,
            role=role,
            location=location,
            apply_url=apply_url,
            description=lst.description,
            posted_at=lst.posted_at,
            cycle=lst.cycle.strip(),
            tools_found=lst.tools_found,
            raw_metadata=lst.raw_metadata
        ))
        
    return normalized

def normalize_apply_url(url: str) -> str:
    """Removes tracking params and rewrites known apply-action URLs to stable job pages."""
    url = url.strip()
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return url

    path = parsed.path
    path = re.sub(r"/apply/(?:autofillWithResume|applyManually|useMyLastApplication)/?$", "", path)
    path = re.sub(r"/apply/?$", "", path)
    path = re.sub(r"/application/?$", "", path)

    params = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith(TRACKING_PARAM_PREFIXES)
        and key.lower() not in TRACKING_PARAM_NAMES
    ]

    return urlunparse(parsed._replace(path=path, query=urlencode(params), fragment=""))
