import pytest
from pathlib import Path
from silicon_list.config import Config
from silicon_list.models import Listing, ScoredListing
from silicon_list.pipeline.report import generate_report, generate_html_report

def test_generate_report(tmp_path: Path):
    out_file = tmp_path / "results.md"
    
    scored = [
        ScoredListing(listing=Listing(source="x", source_job_id="1", company="NVIDIA", role="ASIC Design Intern", location="CA", apply_url="http://x", description="SystemVerilog verification.", posted_at="2d"), score=9, tier=1),
        ScoredListing(listing=Listing(source="x", source_job_id="2", company="Apple", role="Firmware Intern", location="CA", apply_url="http://y", description="Embedded firmware.", posted_at="Oct 1"), score=6, tier=2),
    ]
    
    skipped = [
        (Listing(source="x", source_job_id="3", company="SecretCo", role="C", location="CA", apply_url="http://z"), "hard_exclusion")
    ]
    
    generate_report(scored, skipped, out_file)
    
    content = out_file.read_text()
    
    assert "2 listings shown from 2 new listings found" in content
    assert "## FPGA / RTL / ASIC / DV" in content
    assert "## Firmware / Embedded" in content
    assert "| Company | Role | Location | Posted | Score | Apply |" in content
    assert "| NVIDIA | ASIC Design Intern | CA | 2d | 9 | [Apply](http://x) |" in content
    assert "| Apple | Firmware Intern | CA | Oct 1 | 6 | [Apply](http://y) |" in content
    assert "1 listings skipped — SecretCo" in content

def test_generate_html_report(tmp_path: Path):
    out_file = tmp_path / "results.html"

    scored = [
        ScoredListing(listing=Listing(source="github_simplify", source_job_id="1", company="NVIDIA", role="ASIC Design Intern", location="CA", apply_url="http://x", description="ASIC verification.", posted_at="1d"), score=9, tier=1),
    ]
    skipped = [
        (Listing(source="x", source_job_id="2", company="SecretCo", role="C", location="CA", apply_url="http://z"), "hard_exclusion")
    ]

    generate_html_report(scored, skipped, out_file)

    content = out_file.read_text()

    assert "<title>Silicon List" in content
    assert "NVIDIA" in content
    assert "ASIC Design Intern" in content
    assert "FPGA / RTL / ASIC / DV" in content
    assert "1d" in content
    assert 'href="http://x"' in content
    assert "SecretCo" in content

def test_generate_report_respects_max_report_listings(tmp_path: Path):
    out_file = tmp_path / "results.md"
    config = Config(max_report_listings=1)
    scored = [
        ScoredListing(listing=Listing(source="x", source_job_id="1", company="A", role="FPGA Intern", location="CA", apply_url="http://x", description="Verilog"), score=9, tier=1),
        ScoredListing(listing=Listing(source="x", source_job_id="2", company="B", role="Firmware Intern", location="CA", apply_url="http://y", description="Embedded"), score=4, tier=3),
    ]

    generate_report(scored, [], out_file, config)

    content = out_file.read_text()
    assert "1 listings shown from 2 new listings found" in content
    assert "A" in content
    assert "B" not in content
