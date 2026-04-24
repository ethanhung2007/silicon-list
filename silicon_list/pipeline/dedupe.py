import hashlib
import re
from difflib import SequenceMatcher
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
    run_fingerprints: list[tuple[str, Listing]] = []
    
    for lst in listings:
        normalized_url = lst.apply_url.strip().lower()
        if normalized_url and normalized_url in run_urls:
            seen.append(lst)
            continue
        if normalized_url:
            run_urls.add(normalized_url)

        fingerprint = _fuzzy_fingerprint(lst)
        if any(_same_listing_fuzzy(fingerprint, existing_fp) for existing_fp, _ in run_fingerprints):
            seen.append(lst)
            continue

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
            run_fingerprints.append((fingerprint, lst))
            # We don't add to state_manager here, we add after a successful run in main
            
    return new_listings, seen


def _fuzzy_fingerprint(listing: Listing) -> str:
    company = _normalize(listing.company)
    role = _normalize_role(listing.role)
    location = _normalize_location(listing.location)
    return f"{company}|{role}|{location}"


def _same_listing_fuzzy(left: str, right: str) -> bool:
    left_company, left_role, left_location = left.split("|", 2)
    right_company, right_role, right_location = right.split("|", 2)
    if not left_company or not right_company or left_company != right_company:
        return False
    if left_location and right_location and left_location != right_location:
        return False
    return SequenceMatcher(None, left_role, right_role).ratio() >= 0.82


def _normalize(value: str) -> str:
    value = value.lower()
    value = re.sub(r"\b(?:inc|llc|ltd|corp|corporation|company|co)\b\.?", " ", value)
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def _normalize_role(value: str) -> str:
    value = _normalize(value)
    value = re.sub(r"\b(?:summer|fall|spring|winter|internship|intern|co op|coop|co-op|new grad|new college grad|2026|2027)\b", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _normalize_location(value: str) -> str:
    value = _normalize(value)
    value = value.replace("united states", "us").replace("usa", "us")
    return value
