import pytest
from silicon_list.providers.github_simplify import GitHubSimplifyProvider
from silicon_list.config import Config

@pytest.fixture
def provider():
    return GitHubSimplifyProvider(Config())

def test_parse_markdown(provider):
    markdown = """
# Some README
### 💻 Hardware Engineering
| Company | Role | Location | Application/Link | Date Posted |
| --- | --- | --- | --- | --- |
| **NVIDIA** | ASIC Design Intern | Santa Clara, CA | <a href="https://nvidia.com/apply">Apply</a> | Oct 1 |
| Apple | Hardware Engineering Co-op | Cupertino, CA | <a href="https://apple.com/apply">Apply</a> | Oct 2 |
| **Tesla** | Hardware Intern | Palo Alto, CA | 🔒 | Oct 3 |
| SpaceX | Avionics Intern | Hawthorne, CA | [Apply](https://spacex.com/apply) | Oct 4 |

### Other section
| Company | Role | Location | Application/Link | Date Posted |
| --- | --- | --- | --- | --- |
| Random | Software Intern | NY | <a href="x">Apply</a> | Oct 5 |
    """
    
    listings = provider._parse_markdown(markdown)
    
    assert len(listings) == 3
    
    # NVIDIA
    assert listings[0].company == "NVIDIA"
    assert listings[0].role == "ASIC Design Intern"
    assert listings[0].location == "Santa Clara, CA"
    assert listings[0].apply_url == "https://nvidia.com/apply"
    assert listings[0].posted_at == "Oct 1"
    
    # Apple
    assert listings[1].company == "Apple"
    assert listings[1].apply_url == "https://apple.com/apply"
    
    # Tesla should be skipped because of 🔒
    
    # SpaceX
    assert listings[2].company == "SpaceX"
    assert listings[2].apply_url == "https://spacex.com/apply"

def test_parse_html_table(provider):
    markdown = """
# Some README
## 🔧 Hardware Engineering Internship Roles

<table>
<thead>
<tr>
<th>Company</th>
<th>Role</th>
<th>Location</th>
<th>Application</th>
<th>Age</th>
</tr>
</thead>
<tbody>
<tr>
<td><strong><a href="https://simplify.jobs/c/Analog-Devices">Analog Devices</a></strong></td>
<td>Systems Integration Intern 🎓</td>
<td>Burlington, MA</td>
<td><div align="center"><a href="https://analog.com/apply"><img src="https://example.com/apply.png" alt="Apply"></a> <a href="https://simplify.jobs/p/abc"><img src="https://example.com/simplify.png" alt="Simplify"></a></div></td>
<td>0d</td>
</tr>
<tr>
<td>↳</td>
<td>R&D Engineering Co-op</td>
<td>Auburn, NY</td>
<td><div align="center"><a href="https://baxter.com/apply"><img src="https://example.com/apply.png" alt="Apply"></a></div></td>
<td>1d</td>
</tr>
<tr>
<td><strong><a href="https://simplify.jobs/c/Tesla">Tesla</a></strong></td>
<td>Hardware Intern</td>
<td>Palo Alto, CA</td>
<td>🔒</td>
<td>2d</td>
</tr>
</tbody>
</table>

## Other section
    """

    listings = provider._parse_markdown(markdown)

    assert len(listings) == 2
    assert listings[0].company == "Analog Devices"
    assert listings[0].role == "Systems Integration Intern 🎓"
    assert listings[0].location == "Burlington, MA"
    assert listings[0].apply_url == "https://analog.com/apply"
    assert listings[0].posted_at == "0d"
    assert listings[1].company == "Analog Devices"
    assert listings[1].role == "R&D Engineering Co-op"
    assert listings[1].apply_url == "https://baxter.com/apply"

def test_parse_html_table_with_heading_and_table_variants(provider):
    markdown = """
# Some README
### 🛠️ Hardware Engineering Internships

<table data-testid="job-table">
<tr>
<td><strong>Qualcomm</strong></td>
<td>ASIC Verification Intern</td>
<td>San Diego, CA</td>
<td><a href="https://qualcomm.com/apply/123">Apply</a></td>
<td>2d</td>
</tr>
</table>
    """

    listings = provider._parse_markdown(markdown)

    assert len(listings) == 1
    assert listings[0].company == "Qualcomm"
    assert listings[0].role == "ASIC Verification Intern"
    assert listings[0].apply_url == "https://qualcomm.com/apply/123"

def test_parse_hardware_lines_when_no_hardware_section(provider):
    markdown = """
# Hardware-ish jobs
- Chip Co - FPGA Internship Summer 2026 - https://jobs.lever.co/chipco/abc123
- Web Co - Frontend Internship - https://example.com/web
- Robo Co | Robotics Firmware Intern | https://jobs.ashbyhq.com/roboco/abc12345-1234-1234-1234-123456789abc
    """

    listings = provider._parse_markdown(markdown, source_url="https://github.com/example/list")

    assert len(listings) == 2
    assert listings[0].company == "Chip Co"
    assert listings[0].role == "FPGA Internship Summer 2026"
    assert listings[0].source_url == "https://github.com/example/list"
    assert listings[1].company == "Robo Co"

def test_github_search_item_to_listing(provider):
    listing = provider._search_item_to_listing(
        {
            "id": 123,
            "title": "ASIC Verification Internship Summer 2026 - Chip Co",
            "body": "Apply at https://jobs.lever.co/chipco/verify123. Work with SystemVerilog and UVM.",
            "html_url": "https://github.com/org/repo/issues/1",
        },
        '"asic internship" "2026"',
    )

    assert listing is not None
    assert listing.source == "github_search"
    assert listing.apply_url == "https://jobs.lever.co/chipco/verify123"
    assert listing.source_url == "https://github.com/org/repo/issues/1"
    assert listing.cycle == "Summer 2026"

def test_github_search_rate_limit_is_nonfatal(provider, monkeypatch):
    class FakeResponse:
        status_code = 403
        text = "API rate limit exceeded"

        def json(self):
            return {}

    def fake_get(url, headers=None, params=None, timeout=None):
        return FakeResponse()

    monkeypatch.setattr("silicon_list.providers.github_simplify.requests.get", fake_get)

    assert provider._fetch_search_listings() == []
