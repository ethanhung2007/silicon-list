import re
import hashlib
import requests
from html import unescape
from html.parser import HTMLParser
from typing import List
from silicon_list.models import Listing
from silicon_list.providers.base import BaseProvider, ProviderError, RateLimitError
import logging

logger = logging.getLogger(__name__)

class _TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows: list[list[dict[str, str]]] = []
        self._current_row: list[dict[str, str]] | None = None
        self._current_cell: dict[str, str] | None = None
        self._in_td = False

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "tr":
            self._current_row = []
        elif tag == "td" and self._current_row is not None:
            self._in_td = True
            self._current_cell = {"text": "", "html": ""}
        elif self._in_td and self._current_cell is not None:
            attr_text = "".join(f' {name}="{value}"' for name, value in attrs)
            self._current_cell["html"] += f"<{tag}{attr_text}>"

    def handle_endtag(self, tag):
        if tag == "td" and self._current_row is not None and self._current_cell is not None:
            self._current_row.append(self._current_cell)
            self._current_cell = None
            self._in_td = False
        elif tag == "tr":
            if self._current_row:
                self.rows.append(self._current_row)
            self._current_row = None
        elif self._in_td and self._current_cell is not None:
            self._current_cell["html"] += f"</{tag}>"

    def handle_data(self, data):
        if self._in_td and self._current_cell is not None:
            self._current_cell["text"] += data
            self._current_cell["html"] += data

class GitHubSimplifyProvider(BaseProvider):
    """Fetches hardware internship listings from the SimplifyJobs GitHub README."""

    URL = "https://api.github.com/repos/SimplifyJobs/Summer2026-Internships/contents/README.md"
    
    def fetch_listings(self) -> List[Listing]:
        headers = {"Accept": "application/vnd.github.v3.raw"}
        try:
            response = requests.get(self.URL, headers=headers)
        except requests.RequestException as e:
            raise ProviderError(f"Failed to fetch GitHub README: {e}")

        if response.status_code == 403 and "rate limit" in response.text.lower():
            raise RateLimitError("GitHub API rate limit exceeded.")
        if response.status_code != 200:
            raise ProviderError(f"GitHub API returned status code {response.status_code}")

        markdown_content = response.text
        return self._parse_markdown(markdown_content)

    def _parse_markdown(self, text: str) -> List[Listing]:
        listings: List[Listing] = []
        
        # Look for the Hardware Engineering section
        # The section typically starts with a header like "### 💻 Hardware Engineering" or similar
        # We find the hardware section, and parse lines until the next header or end of file
        
        # Use regex to find the actual heading line for the hardware section.
        hw_match = re.search(
            r'(?im)^#+\s*(?:[^\w#\n]+\s*)?Hardware(?: Engineering)?(?: Internship Roles)?\s*$',
            text
        )
        
        if not hw_match:
            logger.warning("Could not find 'Hardware Engineering' section in GitHub markdown.")
            return listings
        
        # Extract text after the header
        section_text = text[hw_match.end():]
        
        # We only care about the table in this section, so we truncate at the next heading
        next_heading_match = re.search(r'\n#+\s+', section_text)
        if next_heading_match:
            section_text = section_text[:next_heading_match.start()]
            
        if "<table>" in section_text:
            return self._parse_html_table(section_text)

        # Parse table rows. A typical row looks like:
        # | Company | Role | Location | Application/Link | Date Posted |
        # | **Company** | Role | Location | <a href="...">Apply</a> | Date |
        # Wait, if there's a closed icon, it's typically in the apply column or role column.
        
        lines = section_text.strip().split('\n')
        
        in_table = False
        
        for line in lines:
            line = line.strip()
            if not line.startswith('|') or not line.endswith('|'):
                continue
            
            # Split and clean columns
            cols = [col.strip() for col in line.split('|')][1:-1]
            if len(cols) < 4:
                continue
                
            # Skip header rows
            if '---' in cols[0]:
                in_table = True
                continue
            if 'Company' in cols[0] and 'Role' in cols[1]:
                in_table = True
                continue
                
            if not in_table:
                # Sometimes people forget headers, if it looks like data we might still try
                pass

            # Example:
            # 0: Company (e.g. **NVIDIA**)
            # 1: Role
            # 2: Location
            # 3: Apply Link (e.g. <a href="link"><img src="..."></a> or "🔒" for closed)
            # 4: Date (optional)
            
            company_raw = cols[0]
            role_raw = cols[1]
            location_raw = cols[2]
            apply_raw = cols[3]
            
            # Skip if closed
            if "🔒" in line or "closed" in apply_raw.lower() or "not open" in apply_raw.lower():
                continue
                
            # Clean company
            company = re.sub(r'\*+', '', company_raw).strip()
            # Remove link if company is linked
            company = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', company)
            company = re.sub(r'<a.*?>(.*?)</a>', r'\1', company)
            
            # Clean role
            role = re.sub(r'\*+', '', role_raw).strip()
            
            # Clean location
            location = re.sub(r'<br/?>', ', ', location_raw)
            location = re.sub(r'\*+', '', location).strip()
            
            # Extract URL
            url_match = re.search(r'href="([^"]+)"', apply_raw)
            if not url_match:
                url_match = re.search(r'\[.*?\]\((.*?)\)', apply_raw)
                
            apply_url = url_match.group(1) if url_match else apply_raw
            if apply_url.startswith('<a href='): # fallback failed
                apply_url = ""
                
            # Date posted if available
            posted_at = cols[4] if len(cols) > 4 else None
            
            if company and role:
                # Generate a stable ID since github entries don't have natural IDs
                source_id_input = f"{company}-{role}-{location}-{apply_url}".lower().encode('utf-8')
                source_job_id = hashlib.md5(source_id_input).hexdigest()[:16]
                
                listing = Listing(
                    source="github_simplify",
                    source_job_id=source_job_id,
                    company=company,
                    role=role,
                    location=location,
                    apply_url=apply_url,
                    posted_at=posted_at,
                    cycle="Summer 2026", # By definition of the repo
                    description=""
                )
                listings.append(listing)
                
        return listings

    def _parse_html_table(self, section_text: str) -> List[Listing]:
        parser = _TableParser()
        parser.feed(section_text)

        listings: List[Listing] = []
        last_company = ""

        for row in parser.rows:
            if len(row) < 5:
                continue

            company = self._clean_cell_text(row[0]["text"])
            role = self._clean_cell_text(row[1]["text"])
            location = self._clean_cell_text(row[2]["text"])
            apply_html = row[3]["html"]
            apply_text = self._clean_cell_text(row[3]["text"])
            posted_at = self._clean_cell_text(row[4]["text"]) or None

            if company == "↳":
                company = last_company
            elif company:
                last_company = company

            if "🔒" in apply_text or "closed" in apply_text.lower():
                continue

            apply_url = self._extract_apply_url(apply_html)

            if company and role:
                source_job_id = self._source_job_id(company, role, location, apply_url)
                listings.append(Listing(
                    source="github_simplify",
                    source_job_id=source_job_id,
                    company=company,
                    role=role,
                    location=location,
                    apply_url=apply_url,
                    posted_at=posted_at,
                    cycle="Summer 2026",
                    description=""
                ))

        return listings

    def _clean_cell_text(self, text: str) -> str:
        return re.sub(r'\s+', ' ', unescape(text)).strip()

    def _extract_apply_url(self, html: str) -> str:
        urls = re.findall(r'href="([^"]+)"', html)
        for url in urls:
            if "simplify.jobs/p/" not in url:
                return unescape(url)
        return unescape(urls[0]) if urls else ""

    def _source_job_id(self, company: str, role: str, location: str, apply_url: str) -> str:
        source_id_input = f"{company}-{role}-{location}-{apply_url}".lower().encode('utf-8')
        return hashlib.md5(source_id_input).hexdigest()[:16]
