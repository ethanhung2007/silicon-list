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
