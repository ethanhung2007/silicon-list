from typing import List
from silicon_list.models import Listing, ScoredListing
from silicon_list.config import Config
from silicon_list.pipeline.link_validation import validate_listing_link


def listing_tags(listing: Listing, config: Config) -> list[str]:
    text = f"{listing.role} {listing.description}".lower()
    tags: list[str] = []
    tag_keywords = {
        "ASIC": ["asic"],
        "FPGA": ["fpga"],
        "RTL": ["rtl", "verilog", "systemverilog", "vhdl"],
        "Verification": ["verification", "design verification", "dv", "uvm"],
        "Physical Design": ["physical design", "vlsi", "timing closure", "layout"],
        "Firmware": ["firmware", "rtos", "device driver"],
        "Embedded": ["embedded", "microcontroller"],
        "Analog": ["analog"],
        "Mixed-Signal": ["mixed signal", "mixed-signal"],
        "Silicon": ["silicon", "semiconductor"],
        "Computer Architecture": ["computer architecture", "risc-v", "architecture"],
        "EDA": ["eda", "cadence", "synopsys"],
        "PCB": ["pcb", "signal integrity"],
    }
    for tag, keywords in tag_keywords.items():
        if any(keyword in text for keyword in keywords):
            tags.append(tag)

    if not tags:
        for keyword in config.target_keywords:
            if keyword.lower() in text:
                tags.append(keyword)
                break
    return tags[:5]


def listing_type(listing: Listing) -> str:
    text = f"{listing.role} {listing.description}".lower()
    if "co-op" in text or "co op" in text or "coop" in text:
        return "Co-op"
    if "new grad" in text or "new college grad" in text or "graduate" in text:
        return "New Grad"
    if "intern" in text or "internship" in text:
        return "Intern"
    return "Student"

def score_listings(listings: List[Listing], config: Config) -> List[ScoredListing]:
    """Scores listings from 1 to 100 and assigns confidence tiers."""
    scored = []
    
    priority_companies = [c.lower() for c in config.priority_companies]
    known_tools = [t.lower() for t in config.known_tools]
    target_cycles = [cycle.lower() for cycle in config.target_cycle_keywords]
    hardware_bias = getattr(config, "hardware_bias", True)
    
    for lst in listings:
        score = 35
        text_lower = f"{lst.role} {lst.description}".lower()
        role_lower = lst.role.lower()
        
        # Rule: Role title exactly matches or strongly aligns with target category: +3
        # Hardware, ASIC, FPGA, RTL, Physical Design, Verification, Firmware, Embedded
        strong_roles = [
            "hardware", "asic", "fpga", "rtl", "physical design", "verification",
            "design verification", "dv", "firmware", "embedded", "silicon",
            "chip design", "computer architecture", "semiconductor", "vlsi",
            "digital design", "mixed signal", "analog", "validation", "robotics",
            "electrical",
        ]
        if hardware_bias and any(r in role_lower for r in strong_roles):
            score += 18
            
        # Rule: Company is in priority list: +2
        if lst.company.lower() in priority_companies:
            score += 12
            
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
            score += 10
            
        # Rule: Cycle is target cycle: +1
        if any(c in lst.cycle.lower() for c in target_cycles):
            score += 6
            
        # Rule: Mention known tools: +1
        found_tools = [t for t in known_tools if t in text_lower]
        if found_tools:
            score += 6
            lst.tools_found = found_tools
            
        # Rule: Specifically a co-op in a relevant area: +1
        role_type = listing_type(lst)
        if role_type in {"Intern", "Co-op", "New Grad"}:
            score += 8
        if role_type == "Co-op":
            score += 3

        link_validation = validate_listing_link(lst)
        if link_validation.valid:
            score += link_validation.confidence_bonus
            lst.raw_metadata = {
                **lst.raw_metadata,
                "link_validation": link_validation.reason,
                "listing_type": role_type,
                "tags": listing_tags(lst, config),
            }
            
        score = min(score, 100)
        score = max(score, 1)
        
        # Tiering
        if score >= 85:
            tier = 1
        elif score >= 65:
            tier = 2
        else:
            tier = 3
            
        scored.append(ScoredListing(listing=lst, score=score, tier=tier))
        
    return scored
