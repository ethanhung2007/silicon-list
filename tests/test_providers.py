"""Tests for all providers — zero network calls (file I/O mocked or uses tmp files)."""
import json
import pytest
from pathlib import Path
from unittest.mock import patch

from silicon_list.config import Config
from silicon_list.providers.base import ProviderError
from silicon_list.providers.mock_provider import MockProvider
from silicon_list.providers.openclaw_file import OpenClawFileProvider
from silicon_list.providers.hermes import HermesProvider


SAMPLE_LISTINGS = {
    "listings": [
        {
            "company": "NVIDIA",
            "role": "ASIC Design Intern",
            "location": "Santa Clara, CA",
            "apply_url": "https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/job/ASIC-Intern_JR123",
            "description": "RTL design on next-gen GPU silicon.",
            "posted_at": "2026-04-10",
            "cycle": "Summer 2026",
            "source": "Workday",
            "req_id": "JR123",
        },
        {
            "company": "Intel",
            "role": "Hardware Verification Intern",
            "location": "Hillsboro, OR",
            "apply_url": "https://intel.wd1.myworkdayjobs.com/en-US/External/job/HW-Intern_JR999",
            "description": "SystemVerilog verification.",
            "posted_at": "2026-04-01",
            "cycle": "Summer 2026",
        },
    ]
}


@pytest.fixture
def config():
    return Config()


# --- MockProvider ---

def test_mock_provider_returns_listings(config):
    provider = MockProvider(config)
    listings = provider.fetch_listings()
    assert len(listings) > 0
    for lst in listings:
        assert lst.company
        assert lst.role
        assert lst.source == "mock"


def test_mock_provider_has_apply_urls(config):
    provider = MockProvider(config)
    listings = provider.fetch_listings()
    urls = [lst.apply_url for lst in listings if lst.apply_url]
    assert len(urls) > 0


# --- OpenClawFileProvider ---

def test_openclaw_provider_reads_json(tmp_path, config):
    export_file = tmp_path / "openclaw-listings.json"
    export_file.write_text(json.dumps(SAMPLE_LISTINGS))

    provider = OpenClawFileProvider(config, export_path=export_file)
    listings = provider.fetch_listings()

    assert len(listings) == 2
    assert listings[0].company == "NVIDIA"
    assert listings[0].source == "openclaw"
    assert "workdayjobs.com" in listings[0].apply_url


def test_openclaw_provider_raises_on_missing_file(tmp_path, config):
    provider = OpenClawFileProvider(config, export_path=tmp_path / "missing.json")
    with pytest.raises(ProviderError, match="not found"):
        provider.fetch_listings()


def test_openclaw_provider_raises_on_invalid_json(tmp_path, config):
    export_file = tmp_path / "bad.json"
    export_file.write_text("{not valid json}")
    provider = OpenClawFileProvider(config, export_path=export_file)
    with pytest.raises(ProviderError, match="invalid JSON"):
        provider.fetch_listings()


def test_openclaw_provider_handles_flat_list(tmp_path, config):
    export_file = tmp_path / "flat.json"
    export_file.write_text(json.dumps(SAMPLE_LISTINGS["listings"]))
    provider = OpenClawFileProvider(config, export_path=export_file)
    listings = provider.fetch_listings()
    assert len(listings) == 2


# --- HermesProvider ---

def test_hermes_provider_reads_json(tmp_path, config):
    export_file = tmp_path / "hermes-listings.json"
    export_file.write_text(json.dumps(SAMPLE_LISTINGS))

    provider = HermesProvider(config, export_path=export_file)
    listings = provider.fetch_listings()

    assert len(listings) == 2
    assert listings[0].company == "NVIDIA"
    assert listings[0].source == "hermes"
    assert listings[0].raw_metadata.get("hermes_source") is True
    assert listings[0].raw_metadata.get("req_id") == "JR123"


def test_hermes_provider_raises_on_missing_file(tmp_path, config):
    provider = HermesProvider(config, export_path=tmp_path / "missing.json")
    with pytest.raises(ProviderError, match="not found"):
        provider.fetch_listings()


def test_hermes_provider_raises_on_invalid_json(tmp_path, config):
    export_file = tmp_path / "bad.json"
    export_file.write_text("{{broken}")
    provider = HermesProvider(config, export_path=export_file)
    with pytest.raises(ProviderError, match="invalid JSON"):
        provider.fetch_listings()


def test_hermes_provider_warns_on_stale_file(tmp_path, config, capsys):
    export_file = tmp_path / "hermes-listings.json"
    export_file.write_text(json.dumps(SAMPLE_LISTINGS))

    # Backdate the file modification time by 30 hours
    import time, os
    past = time.time() - 30 * 3600
    os.utime(str(export_file), (past, past))

    provider = HermesProvider(config, export_path=export_file)
    listings = provider.fetch_listings()

    captured = capsys.readouterr()
    assert "Warning" in captured.err
    assert len(listings) == 2


def test_hermes_provider_returns_correct_schema(tmp_path, config):
    export_file = tmp_path / "hermes-listings.json"
    export_file.write_text(json.dumps(SAMPLE_LISTINGS))

    provider = HermesProvider(config, export_path=export_file)
    listings = provider.fetch_listings()

    lst = listings[0]
    assert lst.company == "NVIDIA"
    assert lst.role == "ASIC Design Intern"
    assert lst.location == "Santa Clara, CA"
    assert "workdayjobs.com" in lst.apply_url
    assert lst.posted_at == "2026-04-10"
    assert lst.cycle == "Summer 2026"
