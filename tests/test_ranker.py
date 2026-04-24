"""Tests for silicon_list.ranker — no network calls."""
import pytest
from silicon_list.config import Config
from silicon_list.models import Listing
from silicon_list.ranker import rank_listings


@pytest.fixture
def config():
    return Config()


def _listing(**kwargs):
    defaults = dict(
        source="test",
        source_job_id="1",
        company="SomeStartup",
        role="Intern",
        location="",
        apply_url="",
        description="",
        posted_at=None,
        cycle="",
    )
    defaults.update(kwargs)
    return Listing(**defaults)


# --- Bonus tests ---

def test_us_location_adds_15(config):
    lst = _listing(location="Santa Clara, CA")
    scored = rank_listings([lst], config)
    assert scored[0].score >= 15


def test_exact_ats_url_adds_20(config):
    lst = _listing(apply_url="https://boards.greenhouse.io/nvidia/jobs/123456")
    scored = rank_listings([lst], config)
    # Should get +20 for exact posting URL
    assert scored[0].score >= 20


def test_known_semiconductor_adds_10(config):
    lst = _listing(company="NVIDIA", apply_url="https://boards.greenhouse.io/nvidia/jobs/1")
    scored = rank_listings([lst], config)
    # NVIDIA: +10, exact URL: +20
    assert scored[0].score >= 30


def test_student_role_adds_10(config):
    lst = _listing(role="FPGA Intern Summer 2026")
    scored = rank_listings([lst], config)
    # intern: +10, hw keyword (fpga): +15
    assert scored[0].score >= 25


def test_hardware_keyword_in_title_adds_15(config):
    lst = _listing(role="ASIC Design Engineer")
    scored = rank_listings([lst], config)
    assert scored[0].score >= 15


def test_direct_ats_adds_5(config):
    lst = _listing(apply_url="https://jobs.lever.co/nvidia/abc-def-123")
    scored = rank_listings([lst], config)
    assert scored[0].score >= 5


def test_hermes_source_adds_10(config):
    lst = _listing(source="hermes", apply_url="https://jobs.lever.co/acme/123")
    scored = rank_listings([lst], config)
    # +10 hermes, +20 exact URL, +5 direct ATS = 35 minimum
    assert scored[0].score >= 35


# --- Penalty tests ---

def test_clearance_penalty_minus_50(config):
    lst = _listing(
        role="FPGA Intern",
        description="Must have active clearance.",
        apply_url="https://boards.greenhouse.io/corp/jobs/1",
        location="CA",
    )
    scored = rank_listings([lst], config)
    # Even with bonuses, -50 should push score very low
    assert scored[0].score < 30


def test_software_only_penalty_minus_20(config):
    lst = _listing(role="Frontend React Intern", apply_url="https://jobs.lever.co/co/123")
    scored = rank_listings([lst], config)
    # -20 for software signal in title
    assert scored[0].score < 20


def test_stale_listing_penalty_minus_20(config):
    lst = _listing(
        role="FPGA Intern",
        apply_url="https://boards.greenhouse.io/co/jobs/1",
        location="CA",
        posted_at="2025-10-01",  # > 60 days ago from 2026-04-23
    )
    scored = rank_listings([lst], config)
    # Stale penalty applies
    assert scored[0].score <= 70


# --- Tier tests ---

def test_tier1_score_gte_75(config):
    lst = _listing(
        company="NVIDIA",
        role="ASIC Design Intern",
        location="Santa Clara, CA",
        apply_url="https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/job/ASIC-Intern_JR123",
        cycle="Summer 2026",
        posted_at="2026-04-15",
        source="hermes",
    )
    scored = rank_listings([lst], config)
    assert scored[0].tier == 1
    assert scored[0].score >= 75


def test_tier4_suppressed_when_score_below_25(config):
    lst = _listing(role="Frontend React Engineer Full-Time")
    scored = rank_listings([lst], config)
    assert scored[0].tier == 4
    assert scored[0].score < 25


def test_empty_listings_returns_empty(config):
    assert rank_listings([], config) == []


def test_score_clamped_0_to_100(config):
    lst = _listing(
        company="NVIDIA",
        role="ASIC Design Intern",
        location="Santa Clara, CA",
        apply_url="https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/job/ASIC-Intern_JR123",
        cycle="Summer 2026",
        posted_at="2026-04-20",
        source="hermes",
        raw_metadata={"req_id": "JR123"},
    )
    scored = rank_listings([lst], config)
    assert 0 <= scored[0].score <= 100
