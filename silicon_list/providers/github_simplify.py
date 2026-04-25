import re
import hashlib
import requests
from html import unescape
from html.parser import HTMLParser
from typing import Any, List
import logging

from silicon_list.models import Listing
from silicon_list.pipeline.normalize import normalize_apply_url
from silicon_list.providers.base import BaseProvider, ProviderError, RateLimitError

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
    """Fetches hardware internship listings from GitHub README/list/search sources."""

    URL = "https://api.github.com/repos/SimplifyJobs/Summer2026-Internships/contents/README.md"
    SEARCH_URL = "https://api.github.com/search/issues"
    HARDWARE_TERMS = [
        "hardware", "silicon", "fpga", "rtl", "asic", "verification", "dv",
        "firmware", "embedded", "vlsi", "physical design", "eda", "verilog",
        "systemverilog", "analog", "mixed signal", "semiconductor", "robotics",
        "computer architecture", "electrical",
    ]
    STUDENT_TERMS = ["intern", "internship", "co-op", "co op", "coop"]
    
    def fetch_listings(self) -> List[Listing]:
        headers = {"Accept": "application/vnd.github.v3.raw"}
        listings: List[Listing] = []

        source_urls = getattr(self.config, "github_source_urls", None) or [self.URL]
        for source_url in source_urls:
            try:
                response = requests.get(source_url, headers=headers)
            except requests.RequestException as e:
                logger.warning("Failed to fetch GitHub source %s: %s", source_url, e)
                continue

            if response.status_code == 403 and "rate limit" in response.text.lower():
                logger.warning("GitHub source %s hit the API rate limit; skipping it.", source_url)
                continue
            if response.status_code != 200:
                logger.warning("GitHub source %s returned status %s", source_url, response.status_code)
                continue

            listings.extend(self._parse_markdown(response.text, source_url=source_url))

        listings.extend(self._fetch_search_listings())
        if listings:
            return listings

        # Preserve the old hard-fail behavior if every configured source fails.
        try:
            response = requests.get(self.URL, headers=headers)
        except requests.RequestException as e:
            raise ProviderError(f"Failed to fetch GitHub README: {e}")

        if response.status_code == 403 and "rate limit" in response.text.lower():
            raise RateLimitError("GitHub API rate limit exceeded.")
        if response.status_code != 200:
            raise ProviderError(f"GitHub API returned status code {response.status_code}")

        markdown_content = response.text
        return self._parse_markdown(markdown_content, source_url=self.URL)

    def _parse_markdown(self, text: str, source_url: str = URL) -> List[Listing]:
        listings: List[Listing] = []
        
        # Look for the Hardware Engineering section
        # The section typically starts with a header like "### 💻 Hardware Engineering" or similar
        # We find the hardware section, and parse lines until the next header or end of file
        
        # Use regex to find the actual heading line for the hardware section.
        hw_match = re.search(r'(?im)^#+\s*.*\bhardware\b.*$', text)
        
        if not hw_match:
            logger.warning("Could not find 'Hardware Engineering' section in GitHub markdown.")
            return self._parse_hardware_lines(text, source_url)
        
        # Extract text after the header
        section_text = text[hw_match.end():]
        
        # We only care about the table in this section, so we truncate at the next heading
        next_heading_match = re.search(r'\n#+\s+', section_text)
        if next_heading_match:
            section_text = section_text[:next_heading_match.start()]
            
        if re.search(r"<table\b", section_text, re.IGNORECASE):
            return self._parse_html_table(section_text, source_url)

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
                    original_url=apply_url,
                    canonical_url=apply_url,
                    source_url=source_url,
                    posted_at=posted_at,
                    cycle="Summer 2026", # By definition of the repo
                    description=""
                )
                listings.append(listing)
                
        if listings:
            return listings
        return self._parse_hardware_lines(section_text, source_url)

    def _parse_html_table(self, section_text: str, source_url: str = URL) -> List[Listing]:
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
                    original_url=apply_url,
                    canonical_url=apply_url,
                    source_url=source_url,
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

    def _parse_hardware_lines(self, text: str, source_url: str) -> List[Listing]:
        listings: List[Listing] = []
        for line in text.splitlines():
            clean_line = self._clean_cell_text(re.sub(r"<[^>]+>", " ", line))
            text_lower = clean_line.lower()
            if not clean_line or not self._is_hardware_student_text(text_lower):
                continue

            url = self._extract_first_url(line) or source_url
            role = self._infer_role_from_text(clean_line)
            company = self._infer_company_from_text(clean_line)
            source_job_id = self._source_job_id(company, role, "", url)
            listings.append(Listing(
                source="github_hardware_list",
                source_job_id=source_job_id,
                company=company,
                role=role,
                location="",
                apply_url=url,
                original_url=url,
                canonical_url=url,
                source_url=source_url,
                description=clean_line[:500],
                cycle=self._infer_cycle(clean_line),
            ))

        return listings

    def _fetch_search_listings(self) -> List[Listing]:
        listings: List[Listing] = []
        queries = getattr(self.config, "github_search_queries", [])
        limit = max(1, min(10, getattr(self.config, "github_search_results_per_query", 5)))
        headers = {"Accept": "application/vnd.github+json"}

        for query in queries:
            params = {
                "q": f"{query} in:title,body",
                "per_page": limit,
            }
            try:
                response = requests.get(self.SEARCH_URL, headers=headers, params=params, timeout=20)
            except requests.RequestException as e:
                logger.warning("GitHub issue search failed for %r: %s", query, e)
                continue

            if response.status_code == 403 and "rate limit" in response.text.lower():
                logger.warning("GitHub issue search hit the API rate limit for %r; skipping remaining GitHub searches.", query)
                break
            if response.status_code != 200:
                logger.warning("GitHub issue search returned status %s for %r", response.status_code, query)
                continue

            items = response.json().get("items", [])
            if not isinstance(items, list):
                continue
            for item in items:
                listing = self._search_item_to_listing(item, query)
                if listing:
                    listings.append(listing)

        return listings

    def _search_item_to_listing(self, item: dict[str, Any], query: str) -> Listing | None:
        title = self._clean_cell_text(str(item.get("title", "")))
        body = self._clean_cell_text(str(item.get("body", "")))
        text_lower = f"{title} {body}".lower()
        if not title or not self._is_hardware_student_text(text_lower):
            return None

        html_url = str(item.get("html_url", "")).strip()
        apply_url = self._extract_first_url(body) or html_url
        company = self._infer_company_from_text(title)
        source_job_id = str(item.get("id") or self._source_job_id(company, title, "", apply_url))
        return Listing(
            source="github_search",
            source_job_id=source_job_id,
            company=company,
            role=title,
            location="",
            apply_url=apply_url,
            original_url=apply_url,
            canonical_url=apply_url,
            source_url=html_url,
            alternate_urls=[html_url] if html_url and html_url != apply_url else [],
            description=body[:500],
            cycle=self._infer_cycle(f"{title} {body} {query}"),
            raw_metadata={"query": query, "github_url": html_url},
        )

    def _is_hardware_student_text(self, text_lower: str) -> bool:
        return (
            any(term in text_lower for term in self.HARDWARE_TERMS)
            and any(term in text_lower for term in self.STUDENT_TERMS)
        )

    def _extract_first_url(self, text: str) -> str:
        href_match = re.search(r'href=["\']([^"\']+)["\']', text)
        if href_match:
            return unescape(href_match.group(1))
        markdown_match = re.search(r"\[[^\]]+\]\((https?://[^)\s]+)\)", text)
        if markdown_match:
            return unescape(markdown_match.group(1))
        plain_match = re.search(r"https?://[^\s)\]>\"']+", text)
        return normalize_apply_url(unescape(plain_match.group(0))) if plain_match else ""

    def _infer_role_from_text(self, text: str) -> str:
        parts = [part.strip(" -*|") for part in re.split(r"\s+\|\s+|\s+-\s+", text) if part.strip(" -*|")]
        for part in parts:
            if any(term in part.lower() for term in self.STUDENT_TERMS):
                return part[:180]
        return text[:180]

    def _infer_company_from_text(self, text: str) -> str:
        parts = [part.strip(" -*|") for part in re.split(r"\s+\|\s+|\s+-\s+| at ", text) if part.strip(" -*|")]
        if len(parts) >= 2:
            return parts[0][:80]
        return "GitHub"

    def _infer_cycle(self, text: str) -> str:
        text_lower = text.lower()
        for season in ("summer", "fall", "spring"):
            for year in ("2026", "2027"):
                if season in text_lower and year in text_lower:
                    return f"{season.title()} {year}"
        for year in ("2026", "2027"):
            if year in text_lower:
                return year
        return ""
