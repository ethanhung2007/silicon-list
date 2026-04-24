from silicon_list.models import Listing
from silicon_list.pipeline.merge import merge_listing_records, merge_stage_listings


def test_merge_listing_records_prefers_exact_apply_url_and_preserves_alternates():
    stage1 = Listing(
        source="github_simplify",
        source_job_id="1",
        company="CesiumAstro",
        role="Embedded Software Engineering Internship",
        location="",
        apply_url="https://jobs.lever.co/CesiumAstro",
        source_url="https://github.com/example/list",
        description="Firmware internship.",
        raw_metadata={"stage": "stage1"},
    )
    stage2 = Listing(
        source="openclaw",
        source_job_id="2",
        company="CesiumAstro",
        role="Embedded Software Engineering Internship (Summer 2026)",
        location="Austin, TX",
        apply_url="https://jobs.lever.co/CesiumAstro/9fcbcbaf-9c95-4d48-b7c8-521ac052ff39",
        alternate_urls=["https://jobs.lever.co/CesiumAstro"],
        raw_metadata={"stage": "stage2"},
    )

    merged = merge_listing_records(stage1, stage2)

    assert merged.source == "merged"
    assert merged.apply_url == "https://jobs.lever.co/CesiumAstro/9fcbcbaf-9c95-4d48-b7c8-521ac052ff39"
    assert "https://jobs.lever.co/CesiumAstro" in merged.alternate_urls
    assert merged.location == "Austin, TX"
    assert merged.raw_metadata["merged_sources"] == ["stage1", "stage2"]


def test_merge_stage_listings_dedupes_company_and_role_when_url_is_weak():
    listings = [
        Listing(
            source="github_simplify",
            source_job_id="1",
            company="Astera Labs",
            role="Electrical Validation Engineer Internship",
            location="San Jose, CA",
            apply_url="https://job-boards.greenhouse.io/asteraearlycareer2026",
        ),
        Listing(
            source="openclaw",
            source_job_id="2",
            company="Astera Labs",
            role="Electrical Validation Engineer (Internship 2026)",
            location="San Jose, CA",
            apply_url="https://job-boards.greenhouse.io/asteraearlycareer2026/jobs/4605663005",
        ),
    ]

    merged = merge_stage_listings(listings)

    assert len(merged) == 1
    assert merged[0].apply_url == "https://job-boards.greenhouse.io/asteraearlycareer2026/jobs/4605663005"
