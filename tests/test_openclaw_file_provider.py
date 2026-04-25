"""Tests for CoworkProvider's file-parsing logic (skip_run=True skips the claude invocation)."""
import json

from silicon_list.config import Config
from silicon_list.providers.cowork import CoworkProvider


def test_cowork_provider_imports_listings(tmp_path):
    export_file = tmp_path / "openclaw-listings.json"
    export_file.write_text(json.dumps({
        "listings": [
            {
                "company": "Example Robotics",
                "title": "Embedded Firmware Intern",
                "location": "Austin, TX",
                "url": "https://jobs.lever.co/example-robotics/abc123",
                "source_url": "https://example.com/careers",
                "alternate_urls": ["https://www.linkedin.com/jobs/view/123456789"],
                "snippet": "Work on RTOS firmware and embedded systems.",
                "posted": "today",
                "term": "Summer 2026",
            }
        ]
    }))

    provider = CoworkProvider(Config(), export_file, skip_run=True)
    listings = provider.fetch_listings()

    assert len(listings) == 1
    assert listings[0].source == "cowork"
    assert listings[0].company == "Example Robotics"
    assert listings[0].role == "Embedded Firmware Intern"
    assert listings[0].apply_url == "https://jobs.lever.co/example-robotics/abc123"
    assert listings[0].source_url == "https://example.com/careers"
    assert "https://www.linkedin.com/jobs/view/123456789" in listings[0].alternate_urls
    assert listings[0].description == "Work on RTOS firmware and embedded systems."
    assert listings[0].posted_at == "today"
    assert listings[0].cycle == "Summer 2026"


def test_cowork_provider_selects_best_url_from_candidates(tmp_path):
    export_file = tmp_path / "openclaw-listings.json"
    export_file.write_text(json.dumps({
        "listings": [
            {
                "company": "Chip Co",
                "role": "FPGA Intern",
                "source_url": "https://chip.example/careers",
                "links": [
                    {"url": "https://chip.example/careers"},
                    {"url": "https://jobs.lever.co/chipco/abc123?utm_source=openclaw"},
                ],
                "description": "Summer 2026 internship using Verilog and FPGA tooling.",
            }
        ]
    }))

    provider = CoworkProvider(Config(), export_file, skip_run=True)
    listing = provider.fetch_listings()[0]

    assert listing.apply_url == "https://jobs.lever.co/chipco/abc123"
    assert listing.canonical_url == "https://jobs.lever.co/chipco/abc123"
    assert "https://chip.example/careers" in listing.alternate_urls


def test_cowork_provider_reads_agent_schema_aliases(tmp_path):
    export_file = tmp_path / "openclaw-listings.json"
    export_file.write_text(json.dumps({
        "metadata": {"search_date": "2026-04-23"},
        "listings": [
            {
                "company": "Silicon Co",
                "title": "ASIC Verification Intern",
                "location": "Austin, TX",
                "season": "Summer 2026",
                "posted_date": "2026-04-22",
                "focus_areas": ["ASIC", "SystemVerilog", "UVM"],
                "links": [
                    {"href": "https://silicon.example/careers"},
                    {"application_url": "https://jobs.ashbyhq.com/siliconco/abc12345-1234-1234-1234-123456789abc"},
                ],
            }
        ],
    }))

    listing = CoworkProvider(Config(), export_file, skip_run=True).fetch_listings()[0]

    assert listing.company == "Silicon Co"
    assert listing.role == "ASIC Verification Intern"
    assert listing.apply_url == "https://jobs.ashbyhq.com/siliconco/abc12345-1234-1234-1234-123456789abc"
    assert listing.posted_at == "2026-04-22"
    assert listing.cycle == "Summer 2026"
    assert "ASIC, SystemVerilog, UVM" in listing.description
