import json

from silicon_list.config import Config
from silicon_list.providers.openclaw_file import OpenClawFileProvider


def test_openclaw_file_provider_imports_listings(tmp_path):
    export_file = tmp_path / "openclaw-listings.json"
    export_file.write_text(json.dumps({
        "listings": [
            {
                "company": "Example Robotics",
                "title": "Embedded Firmware Intern",
                "location": "Austin, TX",
                "url": "https://example.com/apply",
                "snippet": "Work on RTOS firmware and embedded systems.",
                "posted": "today",
                "term": "Summer 2026",
            }
        ]
    }))

    provider = OpenClawFileProvider(Config(), export_file)
    listings = provider.fetch_listings()

    assert len(listings) == 1
    assert listings[0].source == "openclaw"
    assert listings[0].company == "Example Robotics"
    assert listings[0].role == "Embedded Firmware Intern"
    assert listings[0].apply_url == "https://example.com/apply"
    assert listings[0].description == "Work on RTOS firmware and embedded systems."
    assert listings[0].posted_at == "today"
    assert listings[0].cycle == "Summer 2026"
