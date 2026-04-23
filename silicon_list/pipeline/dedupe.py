import hashlib
from typing import List, Tuple
from silicon_list.models import Listing
from silicon_list.storage.state import StateManager

def generate_dedupe_keys(listing: Listing) -> List[str]:
    """Generates dedupe keys in priority order."""
    
    def hash_str(s: str) -> str:
        return hashlib.md5(s.encode('utf-8')).hexdigest()
        
    keys = []
    
    # 1. source + source_job_id
    if listing.source_job_id:
        keys.append(f"src_{listing.source}_{listing.source_job_id}")
        
    # Normalize strings for composite keys
    company = listing.company.lower().strip()
    role = listing.role.lower().strip()
    location = listing.location.lower().strip()
    apply_url = listing.apply_url.strip()
    
    # 2. company + role + location + apply_url
    if apply_url:
        k2 = f"{company}_{role}_{location}_{apply_url}"
        keys.append(f"comp_{hash_str(k2)}")
        
    # 3. company + role + location
    k3 = f"{company}_{role}_{location}"
    keys.append(f"base_{hash_str(k3)}")
    
    return keys

def dedupe_listings(listings: List[Listing], state_manager: StateManager) -> Tuple[List[Listing], List[Listing]]:
    """
    Dedupes against StateManager.
    Returns (new_listings, seen_listings).
    """
    new_listings = []
    seen = []
    run_urls = set()
    
    for lst in listings:
        normalized_url = lst.apply_url.strip().lower()
        if normalized_url and normalized_url in run_urls:
            seen.append(lst)
            continue
        if normalized_url:
            run_urls.add(normalized_url)

        keys = generate_dedupe_keys(lst)
        is_seen = False
        
        for key in keys:
            if state_manager.is_seen(key):
                is_seen = True
                break
                
        if is_seen:
            seen.append(lst)
        else:
            new_listings.append(lst)
            # We don't add to state_manager here, we add after a successful run in main
            
    return new_listings, seen
