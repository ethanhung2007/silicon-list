import pytest
from pathlib import Path
from silicon_list.models import Listing, ScoredListing
from silicon_list.pipeline.report import generate_report, generate_html_report

def test_generate_report(tmp_path: Path):
    out_file = tmp_path / "results.md"
    
    scored = [
        ScoredListing(listing=Listing(source="x", source_job_id="1", company="NVIDIA", role="A", location="CA", apply_url="http://x"), score=9, tier=1),
        ScoredListing(listing=Listing(source="x", source_job_id="2", company="Apple", role="B", location="CA", apply_url="http://y"), score=6, tier=2),
    ]
    
    skipped = [
        (Listing(source="x", source_job_id="3", company="SecretCo", role="C", location="CA", apply_url="http://z"), "hard_exclusion")
    ]
    
    generate_report(scored, skipped, out_file)
    
    content = out_file.read_text()
    
    assert "2 new listings found" in content
    assert "## Tier 1 (score 8–10)" in content
    assert "| NVIDIA | A | CA | 9 | [Apply](http://x) |" in content
    assert "| Apple | B | CA | 6 | [Apply](http://y) |" in content
    assert "1 listings skipped — SecretCo" in content

def test_generate_html_report(tmp_path: Path):
    out_file = tmp_path / "results.html"

    scored = [
        ScoredListing(listing=Listing(source="github_simplify", source_job_id="1", company="NVIDIA", role="ASIC Design Intern", location="CA", apply_url="http://x"), score=9, tier=1),
    ]
    skipped = [
        (Listing(source="x", source_job_id="2", company="SecretCo", role="C", location="CA", apply_url="http://z"), "hard_exclusion")
    ]

    generate_html_report(scored, skipped, out_file)

    content = out_file.read_text()

    assert "<title>Silicon List" in content
    assert "NVIDIA" in content
    assert "ASIC Design Intern" in content
    assert 'href="http://x"' in content
    assert "SecretCo" in content
