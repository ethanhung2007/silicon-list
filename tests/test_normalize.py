import pytest
from silicon_list.models import Listing
from silicon_list.pipeline.normalize import normalize_listings

def test_normalize_whitespace():
    listings = [
        Listing(source="x", source_job_id="1", company=" NVIDIA  ", role=" ASIC   Design ", location=" CA \n ", apply_url="http://x", cycle=" Summer 2026 ")
    ]
    
    normalized = normalize_listings(listings)
    assert normalized[0].company == "NVIDIA"
    assert normalized[0].role == "ASIC Design"
    assert normalized[0].location == "CA"
    assert normalized[0].cycle == "Summer 2026"

def test_normalize_url():
    listings = [
        Listing(source="x", source_job_id="1", company="NVIDIA", role="ASIC Design", location="CA", apply_url="https://boards.greenhouse.io/nvidia/jobs/1234?gh_jid=1234&tracking=xyz")
    ]
    
    normalized = normalize_listings(listings)
    assert normalized[0].apply_url == "https://boards.greenhouse.io/nvidia/jobs/1234"
