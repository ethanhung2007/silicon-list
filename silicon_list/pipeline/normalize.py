import re
from typing import List
from silicon_list.models import Listing

def normalize_listings(listings: List[Listing]) -> List[Listing]:
    """Normalizes string fields in listings for consistency."""
    normalized = []
    
    for lst in listings:
        company = re.sub(r'\s+', ' ', lst.company).strip()
        role = re.sub(r'\s+', ' ', lst.role).strip()
        location = re.sub(r'\s+', ' ', lst.location).strip()
        
        # Lowercase for consistency in processing, but maybe keep original for display?
        # Actually it's better to keep original for display but normalize for dedupe
        # Let's clean up apply url as well
        apply_url = lst.apply_url.strip()
        if '?' in apply_url and ('linkedin.com' in apply_url or 'greenhouse.io' in apply_url):
            # Try to strip tracking params if possible, but safely
            base, params = apply_url.split('?', 1)
            # Just keep base if it's a known cleanable board, else keep full to not break
            if 'greenhouse.io' in base:
                apply_url = base
        
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
