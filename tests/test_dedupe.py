import pytest
from pathlib import Path
from silicon_list.models import Listing
from silicon_list.storage.state import StateManager
from silicon_list.pipeline.dedupe import dedupe_listings, generate_dedupe_keys

def test_dedupe(tmp_path: Path):
    state_file = tmp_path / "seen.json"
    manager = StateManager(state_file)
    
    listing1 = Listing(source="mock", source_job_id="1", company="A", role="B", location="C", apply_url="D")
    listing2 = Listing(source="mock", source_job_id="2", company="E", role="F", location="G", apply_url="H")
    
    # First run, both new
    new, seen = dedupe_listings([listing1, listing2], manager)
    assert len(new) == 2
    assert len(seen) == 0
    
    # Simulate saving state
    for l in new:
        for k in generate_dedupe_keys(l):
            manager.add(k)
            
    # Second run, listing1 is seen, listing3 is new
    listing3 = Listing(source="mock", source_job_id="3", company="I", role="J", location="K", apply_url="L")
    new, seen = dedupe_listings([listing1, listing3], manager)
    
    assert len(new) == 1
    assert len(seen) == 1
    assert new[0] == listing3
    assert seen[0] == listing1

def test_dedupe_duplicate_urls_in_same_run(tmp_path: Path):
    manager = StateManager(tmp_path / "seen.json")
    listings = [
        Listing(source="searxng", source_job_id="1", company="Intel", role="Silicon Hardware Engineering Intern", location="", apply_url="https://intel.example/job/123", description="Verilog internship"),
        Listing(source="searxng", source_job_id="2", company="Intel", role="Silicon Hardware Engineering - Intern", location="", apply_url="https://intel.example/job/123", description="Verilog internship"),
    ]

    new, seen = dedupe_listings(listings, manager)

    assert len(new) == 1
    assert len(seen) == 1
