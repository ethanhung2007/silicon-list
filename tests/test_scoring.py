import pytest
from silicon_list.models import Listing
from silicon_list.config import Config
from silicon_list.pipeline.scoring import score_listings

@pytest.fixture
def config():
    return Config()

def test_score_listings(config):
    listings = [
        Listing(source="mock", source_job_id="1", company="NVIDIA", role="ASIC Design Intern", location="CA", apply_url="https://jobs.lever.co/nvidia/abc123", description="Verilog required", cycle="Summer 2026"),
        Listing(source="mock", source_job_id="2", company="Random", role="Intern", location="New York", apply_url="https://jobs.lever.co/random/abc123", description="Stuff", cycle="Winter"),
    ]
    
    scored = score_listings(listings, config)
    
    assert len(scored) == 2
    assert scored[0].score == 100
    assert scored[0].tier == 1

    assert scored[1].score == 51
    assert scored[1].tier == 3
