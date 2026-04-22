import pytest
from silicon_list.models import Listing
from silicon_list.config import Config
from silicon_list.pipeline.filtering import filter_listings

@pytest.fixture
def config():
    return Config()

def test_filter_hard_exclusions(config):
    listings = [
        Listing(source="test", source_job_id="1", company="A", role="Intern", location="US", apply_url="x", description="Active security clearance required.", cycle=""),
        Listing(source="test", source_job_id="2", company="B", role="Intern", location="US", apply_url="x", description="Normal job here using Verilog.", cycle="")
    ]
    kept, skipped = filter_listings(listings, config)
    assert len(kept) == 1
    assert len(skipped) == 1
    assert kept[0].company == "B"
    assert skipped[0][1] == "hard_exclusion"

def test_filter_hard_exclusions_catches_clearance_without_exact_phrase(config):
    listings = [
        Listing(source="test", source_job_id="1", company="A", role="FPGA Intern", location="US", apply_url="x", description="Candidates need the ability to obtain a clearance.", cycle=""),
        Listing(source="test", source_job_id="2", company="B", role="FPGA Intern", location="US", apply_url="x", description="Normal Verilog internship.", cycle="")
    ]
    kept, skipped = filter_listings(listings, config)
    assert len(kept) == 1
    assert kept[0].company == "B"
    assert skipped[0][0].company == "A"
    assert skipped[0][1] == "hard_exclusion"

def test_filter_hard_exclusions_catches_itar_us_person_wording(config):
    listings = [
        Listing(source="test", source_job_id="1", company="SpaceX", role="Avionics Embedded Software Co-op", location="CA", apply_url="x", description="Must be a US person due to ITAR restrictions. Embedded work.", cycle=""),
        Listing(source="test", source_job_id="2", company="B", role="Embedded Intern", location="US", apply_url="x", description="Normal firmware internship.", cycle="")
    ]
    kept, skipped = filter_listings(listings, config)
    assert len(kept) == 1
    assert kept[0].company == "B"
    assert skipped[0][0].company == "SpaceX"
    assert skipped[0][1] == "hard_exclusion"

def test_filter_hard_exclusions_catches_us_citizenship_marker(config):
    listings = [
        Listing(source="test", source_job_id="1", company="A", role="Hardware Intern 🇺🇸", location="US", apply_url="x", description="Verilog.", cycle=""),
        Listing(source="test", source_job_id="2", company="B", role="Embedded Intern", location="US", apply_url="x", description="Normal firmware internship.", cycle="")
    ]
    kept, skipped = filter_listings(listings, config)
    assert len(kept) == 1
    assert kept[0].company == "B"
    assert skipped[0][0].company == "A"
    assert skipped[0][1] == "hard_exclusion"

def test_filter_senior_roles(config):
    listings = [
        Listing(source="test", source_job_id="1", company="A", role="Senior ASIC Intern", location="US", apply_url="x", description="Verilog.", cycle=""), # Wait, "senior" is a skip keyword
        Listing(source="test", source_job_id="2", company="B", role="Hardware Intern", location="US", apply_url="x", description="Verilog.", cycle="")
    ]
    kept, skipped = filter_listings(listings, config)
    assert len(kept) == 1
    assert kept[0].company == "B"

def test_filter_irrelevant(config):
    listings = [
        Listing(source="test", source_job_id="1", company="A", role="Software Intern", location="US", apply_url="x", description="React, Node, CSS", cycle=""),
        Listing(source="test", source_job_id="2", company="B", role="Hardware Intern", location="US", apply_url="x", description="Verilog, SystemVerilog", cycle="")
    ]
    kept, skipped = filter_listings(listings, config)
    assert len(kept) == 1
    assert kept[0].company == "B"
    assert skipped[0][1] == "irrelevant"

def test_filter_openclaw_generic_collection_pages(config):
    listings = [
        Listing(source="openclaw", source_job_id="1", company="ApplyBolt", role="Hardware Engineering Intern", location="Various", apply_url="https://www.applybolt.app/jobs/2026-hardware-engineering-internships", description="A collection of hardware engineering internships using Verilog.", cycle="2026"),
        Listing(source="openclaw", source_job_id="2", company="Synopsys", role="Hardware Design Intern", location="Various", apply_url="https://www.synopsys.com/careers/internships.html", description="Internship program for chip design and verification.", cycle="2026"),
        Listing(source="openclaw", source_job_id="3", company="Optiver", role="FPGA Developer Internship", location="Amsterdam, NL", apply_url="https://optiver.com/working-at-optiver/career-opportunities/7985975002/", description="FPGA Developer Internship - 2026-27.", cycle="2026"),
        Listing(source="openclaw", source_job_id="4", company="Motorola Solutions", role="R&D Intern - FPGA/RTL Design Engineer", location="Irvine, CA", apply_url="https://builtin.com/job/r-d-intern-fpga-rtl-design-engineer-2026/8546698", description="RTL coding, simulation, FPGA synthesis, and hardware verification.", cycle="2026"),
    ]

    kept, skipped = filter_listings(listings, config)

    assert len(kept) == 1
    assert kept[0].company == "Motorola Solutions"
    assert [reason for _, reason in skipped] == ["generic_listing", "generic_listing", "generic_listing"]

def test_filter_openclaw_requires_student_role(config):
    listings = [
        Listing(source="openclaw", source_job_id="1", company="NVIDIA", role="ASIC Clocks Verification Engineer - New College Grad 2026", location="CA", apply_url="https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/job/ASIC-Clocks-Verification-Engineer---New-College-Grad-2026_JR2013336", description="Verification engineer role.", cycle="2026"),
        Listing(source="openclaw", source_job_id="2", company="Motorola Solutions", role="R&D Intern - FPGA/RTL Design Engineer", location="Irvine, CA", apply_url="https://builtin.com/job/r-d-intern-fpga-rtl-design-engineer-2026/8546698", description="RTL coding, simulation, FPGA synthesis, and hardware verification.", cycle="2026"),
    ]

    kept, skipped = filter_listings(listings, config)

    assert len(kept) == 1
    assert kept[0].company == "Motorola Solutions"
    assert skipped[0][1] == "not_student_role"
