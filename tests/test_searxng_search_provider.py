import pytest

from silicon_list.config import Config
from silicon_list.providers.base import ProviderError, RateLimitError
from silicon_list.providers.searxng_search import SearXNGSearchProvider


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text

    def json(self):
        return self._payload


def test_searxng_provider_fetches_and_filters_results(monkeypatch):
    config = Config(
        searxng_search_queries=[
            "site:greenhouse.io fpga internship summer 2026",
        ],
        searxng_job_board_search_queries=[],
    )
    provider = SearXNGSearchProvider(config)
    calls = []

    def fake_get(url, params, timeout):
        calls.append((url, params, timeout))
        return FakeResponse(payload={
            "results": [
                {
                    "title": "FPGA Design Intern - Example Robotics",
                    "url": "https://boards.greenhouse.io/example/jobs/123?gh_src=abc&utm_source=test",
                    "content": "Summer 2026 internship working with Verilog and FPGA development.",
                    "engine": "duckduckgo",
                },
                {
                    "title": "FPGA interview questions",
                    "url": "https://example.com/blog/fpga-interview",
                    "content": "Interview preparation for hardware roles.",
                },
            ]
        })

    monkeypatch.setattr("silicon_list.providers.searxng_search.requests.get", fake_get)

    listings = provider.fetch_listings()

    assert len(listings) == 1
    assert calls == [
        (
            "http://localhost:8080/search",
            {"q": "site:greenhouse.io fpga internship summer 2026", "format": "json"},
            20,
        )
    ]
    assert listings[0].source == "searxng"
    assert listings[0].company == "Example Robotics"
    assert listings[0].role == "FPGA Design Intern - Example Robotics"
    assert listings[0].apply_url == "https://boards.greenhouse.io/example/jobs/123"
    assert listings[0].description == "Summer 2026 internship working with Verilog and FPGA development."
    assert listings[0].cycle == "Summer 2026"
    assert listings[0].raw_metadata["query"] == "site:greenhouse.io fpga internship summer 2026"


def test_searxng_provider_uses_env_url(monkeypatch):
    monkeypatch.setenv("SEARXNG_URL", "http://localhost:9999/")
    provider = SearXNGSearchProvider(Config(searxng_search_queries=[], searxng_job_board_search_queries=[]))

    assert provider.base_url == "http://localhost:9999"


def test_searxng_provider_includes_job_board_queries_for_existing_configs():
    provider = SearXNGSearchProvider(Config(
        searxng_search_queries=["fpga intern"],
        searxng_job_board_search_queries=["fpga intern", "site:linkedin.com/jobs/view fpga intern"],
    ))

    assert provider._search_queries() == ["fpga intern", "site:linkedin.com/jobs/view fpga intern"]


def test_searxng_provider_dedupes_results(monkeypatch):
    config = Config(searxng_search_queries=["fpga intern", "hardware intern"], searxng_job_board_search_queries=[])
    provider = SearXNGSearchProvider(config)

    def fake_get(url, params, timeout):
        return FakeResponse(payload={
            "results": [
                {
                    "title": "FPGA Intern @ Chip Co",
                    "url": "https://jobs.lever.co/chipco/abc",
                    "content": "Summer 2026 internship for FPGA hardware design.",
                }
            ]
        })

    monkeypatch.setattr("silicon_list.providers.searxng_search.requests.get", fake_get)

    listings = provider.fetch_listings()

    assert len(listings) == 1
    assert listings[0].company == "Chip Co"


def test_searxng_provider_accepts_exact_job_board_postings(monkeypatch):
    config = Config(searxng_search_queries=["job board hardware intern"], searxng_job_board_search_queries=[])
    provider = SearXNGSearchProvider(config)

    def fake_get(url, params, timeout):
        return FakeResponse(payload={
            "results": [
                {
                    "title": "Hardware Engineering Intern - Example Robotics",
                    "url": "https://www.indeed.com/viewjob?jk=abc123&utm_source=test",
                    "content": "Summer 2026 internship using FPGA and embedded hardware skills.",
                },
                {
                    "title": "Hardware intern jobs in Austin, TX",
                    "url": "https://www.indeed.com/jobs?q=hardware+intern&l=Austin%2C+TX",
                    "content": "Search results for jobs in Austin.",
                },
            ]
        })

    monkeypatch.setattr("silicon_list.providers.searxng_search.requests.get", fake_get)

    listings = provider.fetch_listings()

    assert len(listings) == 1
    assert listings[0].company == "Example Robotics"
    assert listings[0].apply_url == "https://www.indeed.com/viewjob?jk=abc123"


def test_searxng_provider_raises_rate_limit(monkeypatch):
    provider = SearXNGSearchProvider(Config(searxng_search_queries=["fpga intern"], searxng_job_board_search_queries=[]))

    def fake_get(url, params, timeout):
        return FakeResponse(status_code=429, text="too many requests")

    monkeypatch.setattr("silicon_list.providers.searxng_search.requests.get", fake_get)

    with pytest.raises(RateLimitError):
        provider.fetch_listings()


def test_searxng_provider_raises_provider_error_for_invalid_json(monkeypatch):
    provider = SearXNGSearchProvider(Config(searxng_search_queries=["fpga intern"], searxng_job_board_search_queries=[]))

    class BadJsonResponse(FakeResponse):
        def json(self):
            raise ValueError("bad json")

    def fake_get(url, params, timeout):
        return BadJsonResponse()

    monkeypatch.setattr("silicon_list.providers.searxng_search.requests.get", fake_get)

    with pytest.raises(ProviderError):
        provider.fetch_listings()
