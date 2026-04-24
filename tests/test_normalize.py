import pytest
from silicon_list.models import Listing
from silicon_list.pipeline.normalize import normalize_apply_url, normalize_listings, select_best_url

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

def test_normalize_apply_action_urls_and_tracking_params():
    listings = [
        Listing(source="x", source_job_id="1", company="Intel", role="Silicon Hardware Engineering Intern", location="CA", apply_url="https://intel.wd1.myworkdayjobs.com/en-US/External/job/Silicon-Hardware-Engineering----Intern--Bachelor-s_JR0281132/apply/autofillWithResume?utm_source=Simplify&ref=Simplify")
    ]

    normalized = normalize_listings(listings)
    assert normalized[0].apply_url == "https://intel.wd1.myworkdayjobs.com/en-US/External/job/Silicon-Hardware-Engineering----Intern--Bachelor-s_JR0281132"

def test_normalize_repairs_common_url_issues():
    assert normalize_apply_url("jobs.lever.co/example/abc123).") == "https://jobs.lever.co/example/abc123"
    assert normalize_apply_url("https://example.com//careers//job?id=1&utm_source=x") == "https://example.com/careers/job?id=1"

def test_normalize_unwraps_redirect_urls():
    url = "https://www.google.com/url?q=https%3A%2F%2Fjobs.lever.co%2Fchipco%2Fabc123&utm_source=x"

    assert normalize_apply_url(url) == "https://jobs.lever.co/chipco/abc123"

def test_select_best_url_prefers_direct_apply_and_preserves_alternates():
    primary, canonical, alternates = select_best_url([
        "https://example.com/careers",
        "https://www.linkedin.com/jobs/view/123456789",
        "https://jobs.lever.co/example/abc123?utm_source=x",
    ])

    assert primary == "https://jobs.lever.co/example/abc123"
    assert canonical == primary
    assert "https://www.linkedin.com/jobs/view/123456789" in alternates
    assert "https://example.com/careers" in alternates

def test_select_best_url_prefers_exact_ats_posting_over_board_root():
    primary, canonical, alternates = select_best_url([
        "https://job-boards.greenhouse.io/asteraearlycareer2026",
        "https://job-boards.greenhouse.io/asteraearlycareer2026/jobs/4605663005",
    ])

    assert primary == "https://job-boards.greenhouse.io/asteraearlycareer2026/jobs/4605663005"
    assert canonical == primary
    assert alternates == ["https://job-boards.greenhouse.io/asteraearlycareer2026"]

def test_select_best_url_prefers_exact_lever_posting_over_company_root():
    primary, canonical, alternates = select_best_url([
        "https://jobs.lever.co/CesiumAstro",
        "https://jobs.lever.co/CesiumAstro/9fcbcbaf-9c95-4d48-b7c8-521ac052ff39",
    ])

    assert primary == "https://jobs.lever.co/CesiumAstro/9fcbcbaf-9c95-4d48-b7c8-521ac052ff39"
    assert canonical == primary
    assert alternates == ["https://jobs.lever.co/CesiumAstro"]
