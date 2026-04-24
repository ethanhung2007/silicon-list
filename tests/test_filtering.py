import datetime
import pytest
from silicon_list.models import Listing
from silicon_list.config import Config
from silicon_list.pipeline.filtering import filter_listings, posted_age_days

@pytest.fixture
def config():
    return Config()

def test_filter_hard_exclusions(config):
    listings = [
        Listing(source="test", source_job_id="1", company="A", role="Intern", location="US", apply_url="https://jobs.lever.co/a/123", description="Active security clearance required.", cycle=""),
        Listing(source="test", source_job_id="2", company="B", role="Intern", location="US", apply_url="https://jobs.lever.co/b/123", description="Normal job here using Verilog.", cycle="")
    ]
    kept, skipped = filter_listings(listings, config)
    assert len(kept) == 1
    assert len(skipped) == 1
    assert kept[0].company == "B"
    assert skipped[0][1] == "hard_exclusion"

def test_filter_hard_exclusions_catches_clearance_without_exact_phrase(config):
    listings = [
        Listing(source="test", source_job_id="1", company="A", role="FPGA Intern", location="US", apply_url="https://jobs.lever.co/a/123", description="Candidates need the ability to obtain a clearance.", cycle=""),
        Listing(source="test", source_job_id="2", company="B", role="FPGA Intern", location="US", apply_url="https://jobs.lever.co/b/123", description="Normal Verilog internship.", cycle="")
    ]
    kept, skipped = filter_listings(listings, config)
    assert len(kept) == 1
    assert kept[0].company == "B"
    assert skipped[0][0].company == "A"
    assert skipped[0][1] == "hard_exclusion"

def test_filter_hard_exclusions_catches_itar_us_person_wording(config):
    listings = [
        Listing(source="test", source_job_id="1", company="SpaceX", role="Avionics Embedded Software Co-op", location="CA", apply_url="https://jobs.lever.co/a/123", description="Must be a US person due to ITAR restrictions. Embedded work.", cycle=""),
        Listing(source="test", source_job_id="2", company="B", role="Embedded Intern", location="US", apply_url="https://jobs.lever.co/b/123", description="Normal firmware internship.", cycle="")
    ]
    kept, skipped = filter_listings(listings, config)
    assert len(kept) == 1
    assert kept[0].company == "B"
    assert skipped[0][0].company == "SpaceX"
    assert skipped[0][1] == "hard_exclusion"

def test_filter_hard_exclusions_catches_us_citizenship_marker(config):
    listings = [
        Listing(source="test", source_job_id="1", company="A", role="Hardware Intern 🇺🇸", location="US", apply_url="https://jobs.lever.co/a/123", description="Verilog.", cycle=""),
        Listing(source="test", source_job_id="2", company="B", role="Embedded Intern", location="US", apply_url="https://jobs.lever.co/b/123", description="Normal firmware internship.", cycle="")
    ]
    kept, skipped = filter_listings(listings, config)
    assert len(kept) == 1
    assert kept[0].company == "B"
    assert skipped[0][0].company == "A"
    assert skipped[0][1] == "hard_exclusion"

def test_filter_senior_roles(config):
    listings = [
        Listing(source="test", source_job_id="1", company="A", role="Senior ASIC Intern", location="US", apply_url="https://jobs.lever.co/a/123", description="Verilog.", cycle=""),
        Listing(source="test", source_job_id="2", company="B", role="Hardware Intern", location="US", apply_url="https://jobs.lever.co/b/123", description="Verilog.", cycle="")
    ]
    kept, skipped = filter_listings(listings, config)
    assert len(kept) == 1
    assert kept[0].company == "B"

def test_filter_irrelevant(config):
    listings = [
        Listing(source="test", source_job_id="1", company="A", role="Software Intern", location="US", apply_url="https://jobs.lever.co/a/123", description="React, Node, CSS", cycle=""),
        Listing(source="test", source_job_id="2", company="B", role="Hardware Intern", location="US", apply_url="https://jobs.lever.co/b/123", description="Verilog, SystemVerilog", cycle="")
    ]
    kept, skipped = filter_listings(listings, config)
    assert len(kept) == 1
    assert kept[0].company == "B"
    assert skipped[0][1] == "irrelevant"

def test_filter_discards_imperfect_apply_urls_before_reporting(config):
    listings = [
        Listing(source="test", source_job_id="1", company="Intel", role="Silicon Hardware Engineering Intern", location="US", apply_url="https://intel.wd1.myworkdayjobs.com/en-US/External/job/Silicon-Hardware-Engineering----Intern--Bachelor-s_JR0281132/apply/useMyLastApplication", description="Silicon hardware internship.", cycle=""),
        Listing(source="test", source_job_id="2", company="Plexus", role="Intern - Analog Engineer", location="US", apply_url="https://www.linkedin.com/jobs/search?keywords=analog%20intern", description="Analog hardware internship.", cycle=""),
        Listing(source="test", source_job_id="3", company="B", role="FPGA Intern", location="US", apply_url="https://jobs.lever.co/example/123", description="Verilog internship.", cycle=""),
    ]

    kept, skipped = filter_listings(listings, config)

    assert len(kept) == 2
    assert kept[0].company == "Intel"
    assert kept[1].company == "B"
    assert skipped[0][1] == "generic_or_search_url"

def test_filter_old_posted_dates(config):
    config.max_listing_age_days = 31
    listings = [
        Listing(source="test", source_job_id="1", company="A", role="FPGA Intern", location="US", apply_url="https://jobs.lever.co/a/1", description="Verilog internship.", posted_at="45d", cycle=""),
        Listing(source="test", source_job_id="2", company="B", role="FPGA Intern", location="US", apply_url="https://jobs.lever.co/b/2", description="Verilog internship.", posted_at="7d", cycle=""),
    ]

    kept, skipped = filter_listings(listings, config)

    assert len(kept) == 1
    assert kept[0].company == "B"
    assert skipped[0][1] == "too_old"

def test_filter_wrong_explicit_cycle(config):
    listings = [
        Listing(source="test", source_job_id="1", company="A", role="FPGA Intern Summer 2025", location="US", apply_url="https://jobs.lever.co/a/1", description="Verilog internship.", cycle=""),
        Listing(source="test", source_job_id="2", company="B", role="FPGA Intern Summer 2026", location="US", apply_url="https://jobs.lever.co/b/2", description="Verilog internship.", cycle=""),
    ]

    kept, skipped = filter_listings(listings, config)

    assert len(kept) == 1
    assert kept[0].company == "B"
    assert skipped[0][1] == "wrong_cycle"

def test_posted_age_days_parses_common_formats():
    assert posted_age_days("today") == 0
    assert posted_age_days("2w") == 14
    assert posted_age_days("2026-04-01", today=datetime.date(2026, 4, 22)) == 21

def test_filter_openclaw_discards_generic_links_before_reporting(config):
    listings = [
        Listing(source="openclaw", source_job_id="1", company="ApplyBolt", role="Hardware Engineering Intern", location="Various", apply_url="https://www.applybolt.app/jobs/2026-hardware-engineering-internships", description="A collection of hardware engineering internships using Verilog.", cycle="2026"),
        Listing(source="openclaw", source_job_id="2", company="Synopsys", role="Hardware Design Intern", location="Various", apply_url="https://www.synopsys.com/careers/internships.html", description="Internship program for chip design and verification.", cycle="2026"),
        Listing(source="openclaw", source_job_id="3", company="Optiver", role="FPGA Developer Internship", location="Amsterdam, NL", apply_url="https://optiver.com/working-at-optiver/career-opportunities/7985975002/", description="FPGA Developer Internship - 2026-27.", cycle="2026"),
        Listing(source="openclaw", source_job_id="4", company="Motorola Solutions", role="R&D Intern - FPGA/RTL Design Engineer", location="Irvine, CA", apply_url="https://builtin.com/job/r-d-intern-fpga-rtl-design-engineer-2026/8546698", description="RTL coding, simulation, FPGA synthesis, and hardware verification.", cycle="2026"),
    ]

    kept, skipped = filter_listings(listings, config)

    assert len(kept) == 2
    assert {listing.company for listing in kept} == {"Optiver", "Motorola Solutions"}
    assert [reason for _, reason in skipped] == ["generic_job_collection", "not_exact_posting_url"]

def test_filter_openclaw_allows_new_grad_roles(config):
    listings = [
        Listing(source="openclaw", source_job_id="1", company="NVIDIA", role="ASIC Clocks Verification Engineer - New College Grad 2026", location="CA", apply_url="https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/job/ASIC-Clocks-Verification-Engineer---New-College-Grad-2026_JR2013336", description="Verification engineer role.", cycle="2026"),
        Listing(source="openclaw", source_job_id="2", company="Motorola Solutions", role="R&D Intern - FPGA/RTL Design Engineer", location="Irvine, CA", apply_url="https://builtin.com/job/r-d-intern-fpga-rtl-design-engineer-2026/8546698", description="RTL coding, simulation, FPGA synthesis, and hardware verification.", cycle="2026"),
    ]

    kept, skipped = filter_listings(listings, config)

    assert len(kept) == 2
    assert skipped == []

def test_filter_allows_exact_job_board_postings(config):
    listings = [
        Listing(source="openclaw", source_job_id="1", company="NVIDIA", role="ASIC Verification Intern", location="CA", apply_url="https://www.linkedin.com/jobs/view/123456789", description="Summer 2026 internship using SystemVerilog and UVM.", cycle="2026"),
        Listing(source="openclaw", source_job_id="2", company="Search", role="Hardware intern jobs", location="", apply_url="https://www.linkedin.com/jobs/search?keywords=hardware%20intern", description="FPGA internship search results.", cycle="2026"),
    ]

    kept, skipped = filter_listings(listings, config)

    assert len(kept) == 1
    assert kept[0].company == "NVIDIA"
    assert skipped[0][1] == "generic_or_search_url"

def test_filter_openclaw_discards_general_company_links(config):
    listings = [
        Listing(source="openclaw", source_job_id="1", company="NVIDIA", role="ASIC Verification Intern", location="CA", apply_url="https://www.nvidia.com/en-us/about-nvidia/careers/", description="Summer 2026 internship using SystemVerilog and UVM.", cycle="2026"),
        Listing(source="openclaw", source_job_id="2", company="NVIDIA", role="ASIC Verification Intern", location="CA", apply_url="https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/job/ASIC-Verification-Intern_JR2012345", description="Summer 2026 internship using SystemVerilog and UVM.", cycle="2026"),
    ]

    kept, skipped = filter_listings(listings, config)

    assert len(kept) == 1
    assert kept[0].apply_url.endswith("JR2012345")
    assert skipped[0][1] == "generic_or_search_url"

def test_filter_openclaw_discards_ats_landing_pages(config):
    listings = [
        Listing(source="openclaw", source_job_id="1", company="Example", role="FPGA Intern", location="US", apply_url="https://jobs.lever.co/example", description="Summer 2026 internship using Verilog.", cycle="2026"),
        Listing(source="openclaw", source_job_id="2", company="Example", role="FPGA Intern", location="US", apply_url="https://jobs.lever.co/example/abc123", description="Summer 2026 internship using Verilog.", cycle="2026"),
    ]

    kept, skipped = filter_listings(listings, config)

    assert len(kept) == 1
    assert kept[0].apply_url == "https://jobs.lever.co/example/abc123"
    assert skipped[0][1] == "generic_or_search_url"

def test_filter_openclaw_allows_exact_greenhouse_and_ashby_links(config):
    listings = [
        Listing(source="openclaw", source_job_id="1", company="SpaceX", role="Silicon Hardware Engineering Internship", location="US", apply_url="https://job-boards.greenhouse.io/spacex/jobs/8190526002", description="Summer 2026 VLSI internship.", cycle="2026"),
        Listing(source="openclaw", source_job_id="2", company="Etched", role="DV Intern", location="US", apply_url="https://jobs.ashbyhq.com/Etched/dacedaca-c4ca-4964-857-8df1738005bb", description="Design verification internship using SystemVerilog.", cycle="2026"),
    ]

    kept, skipped = filter_listings(listings, config)

    assert len(kept) == 2
    assert skipped == []
