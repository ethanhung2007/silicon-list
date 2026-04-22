from typing import List
from silicon_list.models import Listing, ScoredListing
from silicon_list.config import Config

def score_listings(listings: List[Listing], config: Config) -> List[ScoredListing]:
    """Scores listings from 1 to 10 and assigns tiers."""
    scored = []
    
    priority_companies = [c.lower() for c in config.priority_companies]
    known_tools = [t.lower() for t in config.known_tools]
    target_cycles = ["summer 2026", "fall 2026", "spring 2027", "summer 2027"]
    
    for lst in listings:
        score = 0
        text_lower = f"{lst.role} {lst.description}".lower()
        role_lower = lst.role.lower()
        
        # Rule: Role title exactly matches or strongly aligns with target category: +3
        # Hardware, ASIC, FPGA, RTL, Physical Design, Verification, Firmware, Embedded
        strong_roles = ["hardware", "asic", "fpga", "rtl", "physical design", "verification", "firmware", "embedded", "silicon", "chip design", "computer architecture"]
        if any(r in role_lower for r in strong_roles):
            score += 3
            
        # Rule: Company is in priority list: +2
        if lst.company.lower() in priority_companies:
            score += 2
            
        # Rule: Location is US: +2
        # Remote, US locations, or empty (assuming US if not specified otherwise, but strict says US only)
        # We will give +2 if US state or generic US is mentioned.
        # Actually, the requirement says "Location is US: +2"
        # We can look for states like CA, TX, OR, MA, NY, WA, or "United States", "USA", "Remote, US", etc.
        # A simple check:
        us_locations = ["ca", "tx", "or", "ma", "ny", "wa", "nc", "co", "az", "united states", "usa", "us"]
        loc_lower = lst.location.lower()
        
        # Check if the location contains any exact state code word or country
        words = [w.strip(',') for w in loc_lower.split()]
        if any(w in us_locations for w in words):
            score += 2
            
        # Rule: Cycle is target cycle: +1
        if any(c in lst.cycle.lower() for c in target_cycles):
            score += 1
            
        # Rule: Mention known tools: +1
        found_tools = [t for t in known_tools if t in text_lower]
        if found_tools:
            score += 1
            lst.tools_found = found_tools
            
        # Rule: Specifically a co-op in a relevant area: +1
        if "co-op" in role_lower or "coop" in role_lower:
            score += 1
            
        # Clamp to 10 max
        score = min(score, 10)
        # Ensure minimum score of 1 if it made it this far
        score = max(score, 1)
        
        # Tiering
        if score >= 8:
            tier = 1
        elif score >= 5:
            tier = 2
        else:
            tier = 3
            
        scored.append(ScoredListing(listing=lst, score=score, tier=tier))
        
    return scored
