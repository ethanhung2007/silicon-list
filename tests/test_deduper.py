"""Tests for silicon_list.deduper — no network calls."""
import pytest
from silicon_list.models import Listing
from silicon_list.deduper import Deduper


def _listing(company="NVIDIA", role="ASIC Design Intern", location="CA", url="https://jobs.lever.co/nvidia/abc"):
    return Listing(
        source="test",
        source_job_id="x",
        company=company,
        role=role,
        location=location,
        apply_url=url,
    )


@pytest.fixture
def deduper():
    return Deduper()


def test_no_duplicates_returned_unchanged(deduper):
    listings = [
        _listing("NVIDIA", "ASIC Design Intern", "CA", "https://url1.com/jobs/1"),
        _listing("Intel", "RTL Engineer Intern", "OR", "https://url2.com/jobs/2"),
    ]
    result = deduper.deduplicate(listings)
    assert len(result) == 2


def test_exact_url_match_dedupes(deduper):
    url = "https://boards.greenhouse.io/nvidia/jobs/123"
    a = _listing("NVIDIA", "ASIC Design Intern", "CA", url)
    b = _listing("NVIDIA", "ASIC Design Intern - Summer", "CA", url)
    result = deduper.deduplicate([a, b])
    assert len(result) == 1


def test_fuzzy_title_same_company_dedupes(deduper):
    a = _listing("NVIDIA", "FPGA Design Intern Summer 2026", "CA", "https://x.com/job/1")
    b = _listing("NVIDIA", "FPGA Design Intern", "CA", "https://x.com/job/2")
    result = deduper.deduplicate([a, b])
    assert len(result) == 1


def test_different_company_not_deduped(deduper):
    a = _listing("NVIDIA", "ASIC Design Intern", "CA", "https://a.com/job/1")
    b = _listing("Intel", "ASIC Design Intern", "CA", "https://b.com/job/1")
    result = deduper.deduplicate([a, b])
    assert len(result) == 2


def test_different_location_not_deduped(deduper):
    a = _listing("NVIDIA", "ASIC Design Intern", "CA", "https://a.com/job/1")
    b = _listing("NVIDIA", "ASIC Design Intern", "OR", "https://b.com/job/2")
    result = deduper.deduplicate([a, b])
    assert len(result) == 2


def test_best_entry_is_kept_by_confidence(deduper):
    low = _listing("NVIDIA", "ASIC Design Intern", "CA", "https://url1.com/job/1")
    low.raw_metadata = {"validation_confidence": 0.3}
    high = _listing("NVIDIA", "ASIC Design Intern", "CA", "https://url1.com/job/1")
    high.raw_metadata = {"validation_confidence": 0.9}
    result = deduper.deduplicate([low, high])
    assert len(result) == 1
    assert result[0].raw_metadata.get("validation_confidence") == 0.9


def test_best_entry_kept_by_posted_date_when_confidence_equal(deduper):
    older = _listing("AMD", "RTL Intern", "CA", "https://url.com/job/1")
    older.posted_at = "2026-01-01"
    newer = _listing("AMD", "RTL Intern", "CA", "https://url.com/job/1")
    newer.posted_at = "2026-04-01"
    result = deduper.deduplicate([older, newer])
    assert len(result) == 1
    assert result[0].posted_at == "2026-04-01"


def test_empty_input_returns_empty(deduper):
    assert deduper.deduplicate([]) == []


def test_single_listing_returned_as_is(deduper):
    lst = _listing()
    result = deduper.deduplicate([lst])
    assert len(result) == 1
    assert result[0] is lst


def test_three_duplicates_returns_one(deduper):
    url = "https://boards.greenhouse.io/co/jobs/456"
    listings = [_listing("Apple", "Silicon Engineering Co-op", "TX", url) for _ in range(3)]
    result = deduper.deduplicate(listings)
    assert len(result) == 1
