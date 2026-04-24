"""Tests for silicon_list.validator — all HTTP calls are mocked."""
from unittest.mock import MagicMock, patch

import pytest

from silicon_list.models import Listing
from silicon_list.validator import ListingValidator, ValidationStatus


def _listing(url="https://boards.greenhouse.io/acme/jobs/123", role="ASIC Design Intern"):
    return Listing(
        source="test",
        source_job_id="1",
        company="Acme",
        role=role,
        location="CA",
        apply_url=url,
    )


def _mock_response(status_code=200, text="<html><body><h1>ASIC Design Intern</h1><button>Apply now</button></body></html>", url=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.url = url or "https://boards.greenhouse.io/acme/jobs/123"
    return resp


@pytest.fixture
def validator():
    return ListingValidator()


def test_missing_url_is_invalid(validator):
    lst = _listing(url="")
    result = validator.validate(lst)
    assert result.status == ValidationStatus.INVALID
    assert result.notes == "no_url"
    assert result.confidence == 0.0


def test_generic_careers_url_is_invalid(validator):
    lst = _listing(url="https://acme.com/careers")
    result = validator.validate(lst)
    assert result.status == ValidationStatus.INVALID
    assert result.notes == "generic_url"


def test_http_404_is_invalid(validator):
    with patch("requests.get", return_value=_mock_response(404, url="https://boards.greenhouse.io/acme/jobs/123")):
        result = validator.validate(_listing())
    assert result.status == ValidationStatus.INVALID
    assert "404" in result.notes


def test_http_200_with_title_and_apply_is_valid(validator):
    body = "<html><body><h1>ASIC Design Intern at Acme</h1><button>Apply now</button></body></html>"
    with patch("requests.get", return_value=_mock_response(200, text=body)):
        result = validator.validate(_listing())
    assert result.status == ValidationStatus.VALID
    assert result.confidence >= 0.8


def test_http_200_with_apply_only_is_valid(validator):
    body = "<html><body><p>Some job description.</p><a href='/apply'>Apply now</a></body></html>"
    with patch("requests.get", return_value=_mock_response(200, text=body)):
        result = validator.validate(_listing())
    assert result.status == ValidationStatus.VALID
    assert result.confidence >= 0.75


def test_expired_posting_is_invalid(validator):
    body = "<html><body><h1>ASIC Design Intern</h1><p>This position has been filled.</p></body></html>"
    with patch("requests.get", return_value=_mock_response(200, text=body)):
        result = validator.validate(_listing())
    assert result.status == ValidationStatus.INVALID
    assert result.notes == "expired_posting"


def test_js_heavy_page_is_uncertain(validator):
    # Very short HTML with lots of scripts = JS-heavy
    body = "<html><head>" + "<script>var x=1;</script>" * 10 + "</head><body></body></html>"
    with patch("requests.get", return_value=_mock_response(200, text=body)):
        result = validator.validate(_listing())
    assert result.status == ValidationStatus.UNCERTAIN
    assert result.notes == "js_heavy_page"


def test_request_exception_returns_uncertain(validator):
    import requests as req_mod
    with patch("requests.get", side_effect=req_mod.ConnectionError("timeout")):
        result = validator.validate(_listing())
    assert result.status == ValidationStatus.UNCERTAIN
    assert "request_failed" in result.notes


def test_redirected_to_generic_is_invalid(validator):
    resp = _mock_response(200, url="https://acme.com/careers")
    resp.text = "<html><body><h1>Jobs at Acme</h1></body></html>"
    with patch("requests.get", return_value=resp):
        result = validator.validate(_listing())
    assert result.status == ValidationStatus.INVALID
    assert result.notes == "redirected_to_generic"
