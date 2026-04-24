from silicon_list.config import Config
from silicon_list.providers.google_search import GoogleSearchProvider


def test_google_search_item_to_listing():
    provider = GoogleSearchProvider(Config())

    listing = provider._item_to_listing(
        {
            "title": "Firmware Engineering Intern - Example Robotics",
            "snippet": "Work on embedded systems and RTOS firmware.",
            "link": "https://jobs.example.com/firmware-intern",
        },
        "firmware engineering intern 2026",
    )

    assert listing.source == "google_search"
    assert listing.company == "Example Robotics"
    assert listing.role == "Firmware Engineering Intern - Example Robotics"
    assert listing.apply_url == "https://jobs.example.com/firmware-intern"
    assert listing.description == "Work on embedded systems and RTOS firmware."
    assert listing.raw_metadata["query"] == "firmware engineering intern 2026"


def test_google_search_includes_job_board_queries_for_existing_configs():
    provider = GoogleSearchProvider(Config(search_queries=["fpga intern"], job_board_search_queries=["fpga intern", "site:indeed.com/viewjob fpga intern"]))

    assert provider._search_queries() == ["fpga intern", "site:indeed.com/viewjob fpga intern"]
