import datetime
from html import escape
from pathlib import Path
from typing import List, Tuple
from silicon_list.models import ScoredListing, Listing
from silicon_list.config import Config

def categorize_listing(listing: Listing, config: Config) -> str:
    text = f"{listing.role} {listing.description}".lower()
    for category, keywords in config.description_categories.items():
        if any(keyword.lower() in text for keyword in keywords):
            return category
    return "Other Relevant"

def prepare_report_sections(scored_listings: List[ScoredListing], config: Config) -> list[tuple[str, list[ScoredListing]]]:
    max_report_listings = getattr(config, "max_report_listings", 0)
    sorted_listings = sorted(scored_listings, key=lambda s: s.score, reverse=True)
    if max_report_listings:
        sorted_listings = sorted_listings[:max_report_listings]

    grouped: dict[str, list[ScoredListing]] = {}
    for scored in sorted_listings:
        grouped.setdefault(categorize_listing(scored.listing, config), []).append(scored)

    category_order = list(config.description_categories.keys()) + ["Other Relevant"]
    return [(category, grouped[category]) for category in category_order if grouped.get(category)]

def generate_report(
    scored_listings: List[ScoredListing], 
    skipped: List[Tuple[Listing, str]], 
    output_path: Path,
    config: Config | None = None,
):
    """Writes the results to a markdown report."""
    
    config = config or Config()
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    sections = prepare_report_sections(scored_listings, config)
    
    skipped_hard = [s for s, reason in skipped if reason == "hard_exclusion"]
    skipped_companies = list(set([s.company for s in skipped_hard]))
    skipped_companies.sort()
    
    lines = []
    lines.append(f"# Silicon List — {date_str}")
    shown_count = sum(len(section_list) for _, section_list in sections)
    lines.append(f"{shown_count} listings shown from {len(scored_listings)} new listings found")
    lines.append("")
    
    for category, category_list in sections:
        lines.append(f"## {category}")
        lines.append("| Company | Role | Location | Posted | Score | Apply |")
        lines.append("|---|---|---|---|---:|---|")
        for s in category_list:
            apply_link = f"[Apply]({s.listing.apply_url})" if s.listing.apply_url else "No link"
            posted = s.listing.posted_at or "Unknown"
            lines.append(f"| {s.listing.company} | {s.listing.role} | {s.listing.location} | {posted} | {s.score} | {apply_link} |")
        lines.append("")
    
    lines.append("## Skipped (hard eligibility restrictions)")
    if skipped_hard:
        lines.append(f"{len(skipped_hard)} listings skipped — {', '.join(skipped_companies)}")
    else:
        lines.append("0 listings skipped — ")
        
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write("\n".join(lines) + "\n")

def generate_html_report(
    scored_listings: List[ScoredListing],
    skipped: List[Tuple[Listing, str]],
    output_path: Path,
    config: Config | None = None,
):
    """Writes the results to a browser-friendly HTML report."""

    config = config or Config()
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    sections_data = prepare_report_sections(scored_listings, config)
    shown_count = sum(len(section_list) for _, section_list in sections_data)

    skipped_hard = [s for s, reason in skipped if reason == "hard_exclusion"]
    skipped_companies = sorted(set(s.company for s in skipped_hard))

    def listing_row(s: ScoredListing) -> str:
        listing = s.listing
        apply_link = (
            f'<a class="apply" href="{escape(listing.apply_url, quote=True)}" target="_blank" rel="noreferrer">Apply</a>'
            if listing.apply_url else
            '<span class="muted">No link</span>'
        )
        source = escape(listing.source.replace("_", " ").title())
        tools = ", ".join(listing.tools_found) if listing.tools_found else ""
        meta = " / ".join(part for part in [source, listing.cycle, tools] if part)
        posted = listing.posted_at or "Unknown"
        return f"""
            <tr>
              <td>
                <strong>{escape(listing.company)}</strong>
                <span>{escape(meta)}</span>
              </td>
              <td>{escape(listing.role)}</td>
              <td>{escape(listing.location or "Unknown")}</td>
              <td>{escape(posted)}</td>
              <td class="score">{s.score}</td>
              <td>{apply_link}</td>
            </tr>
        """

    sections = []
    for category, category_list in sections_data:
        rows = "\n".join(listing_row(s) for s in category_list)
        if not rows:
            rows = '<tr><td colspan="6" class="empty">No listings in this category.</td></tr>'
        sections.append(f"""
          <section>
            <h2>{escape(category)}</h2>
            <table>
              <thead>
                <tr>
                  <th>Company</th>
                  <th>Role</th>
                  <th>Location</th>
                  <th>Posted</th>
                  <th>Score</th>
                  <th>Apply</th>
                </tr>
              </thead>
              <tbody>{rows}</tbody>
            </table>
          </section>
        """)

    skipped_text = (
        f"{len(skipped_hard)} listings skipped: {escape(', '.join(skipped_companies))}"
        if skipped_hard else
        "0 listings skipped"
    )

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Silicon List - {date_str}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f8fa;
      --panel: #ffffff;
      --text: #1e2937;
      --muted: #667085;
      --line: #d8dee8;
      --accent: #0f766e;
      --accent-dark: #115e59;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.45;
    }}
    header {{
      padding: 32px 24px 18px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }}
    main {{
      width: min(1180px, calc(100% - 32px));
      margin: 24px auto 48px;
    }}
    h1 {{
      margin: 0 0 6px;
      font-size: 32px;
      letter-spacing: 0;
    }}
    h2 {{
      margin: 28px 0 12px;
      font-size: 22px;
      letter-spacing: 0;
    }}
    h2 small {{
      color: var(--muted);
      font-size: 14px;
      font-weight: 500;
      margin-left: 8px;
    }}
    .summary {{
      color: var(--muted);
      margin: 0;
    }}
    section {{
      margin-top: 22px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
    }}
    th, td {{
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
    }}
    th {{
      background: #eef2f6;
      color: #344054;
      font-size: 13px;
      text-transform: uppercase;
    }}
    td span {{
      display: block;
      color: var(--muted);
      font-size: 13px;
      margin-top: 3px;
    }}
    tr:last-child td {{ border-bottom: 0; }}
    .score {{
      font-weight: 700;
      text-align: right;
      white-space: nowrap;
    }}
    .apply {{
      display: inline-block;
      color: #ffffff;
      background: var(--accent);
      padding: 7px 12px;
      border-radius: 6px;
      font-weight: 700;
      text-decoration: none;
      white-space: nowrap;
    }}
    .apply:hover {{ background: var(--accent-dark); }}
    .empty, .muted {{
      color: var(--muted);
    }}
    footer {{
      margin-top: 24px;
      color: var(--muted);
      font-size: 14px;
    }}
    @media (max-width: 760px) {{
      header {{ padding: 24px 16px 16px; }}
      main {{ width: calc(100% - 20px); margin-top: 14px; }}
      table {{ display: block; overflow-x: auto; }}
      th, td {{ min-width: 120px; }}
      h1 {{ font-size: 26px; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Silicon List</h1>
    <p class="summary">{shown_count} listings shown from {len(scored_listings)} new listings found on {date_str}</p>
  </header>
  <main>
    {"".join(sections)}
    <footer>{skipped_text}</footer>
  </main>
</body>
</html>
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write(html)
