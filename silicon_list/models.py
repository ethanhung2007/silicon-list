from dataclasses import dataclass, field
from typing import Any, Optional

@dataclass
class Listing:
    source: str
    source_job_id: str
    company: str
    role: str
    location: str
    apply_url: str
    description: str = ""
    posted_at: Optional[str] = None
    cycle: str = ""
    tools_found: list[str] = field(default_factory=list)
    raw_metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class ScoredListing:
    listing: Listing
    score: int
    tier: int

@dataclass
class ReportSection:
    tier_name: str
    listings: list[ScoredListing]
