import datetime
from html import escape
from pathlib import Path
from typing import List, Tuple
from silicon_list.models import ScoredListing, Listing

def generate_report(
    scored_listings: List[ScoredListing], 
    skipped: List[Tuple[Listing, str]], 
    output_path: Path
):
    """Writes the results to a markdown report."""
    
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    
    t1 = [s for s in scored_listings if s.tier == 1]
    t2 = [s for s in scored_listings if s.tier == 2]
    t3 = [s for s in scored_listings if s.tier == 3]
    
    t1.sort(key=lambda x: x.score, reverse=True)
    t2.sort(key=lambda x: x.score, reverse=True)
    t3.sort(key=lambda x: x.score, reverse=True)
    
    skipped_hard = [s for s, reason in skipped if reason == "hard_exclusion"]
    skipped_companies = list(set([s.company for s in skipped_hard]))
    skipped_companies.sort()
    
    lines = []
    lines.append(f"# Silicon List — {date_str}")
    lines.append(f"{len(scored_listings)} new listings found")
    lines.append("")
    
    def _write_tier(tier_num: int, tier_name: str, tier_list: List[ScoredListing]):
        lines.append(f"## Tier {tier_num} ({tier_name})")
        lines.append("| Company | Role | Location | Score | Apply |")
        lines.append("|---|---|---|---:|---|")
        for s in tier_list:
            apply_link = f"[Apply]({s.listing.apply_url})" if s.listing.apply_url else "No link"
            lines.append(f"| {s.listing.company} | {s.listing.role} | {s.listing.location} | {s.score} | {apply_link} |")
        lines.append("")
        
    _write_tier(1, "score 8–10", t1)
    _write_tier(2, "score 5–7", t2)
    _write_tier(3, "score 1–4", t3)
    
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
    output_path: Path
):
    """Writes the results to a browser-friendly HTML report."""

    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    tiers = [
        (1, "score 8-10", sorted([s for s in scored_listings if s.tier == 1], key=lambda x: x.score, reverse=True)),
        (2, "score 5-7", sorted([s for s in scored_listings if s.tier == 2], key=lambda x: x.score, reverse=True)),
        (3, "score 1-4", sorted([s for s in scored_listings if s.tier == 3], key=lambda x: x.score, reverse=True)),
    ]

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
        return f"""
            <tr>
              <td>
                <strong>{escape(listing.company)}</strong>
                <span>{escape(meta)}</span>
              </td>
              <td>{escape(listing.role)}</td>
              <td>{escape(listing.location or "Unknown")}</td>
              <td class="score">{s.score}</td>
              <td>{apply_link}</td>
            </tr>
        """

    sections = []
    for tier_num, tier_name, tier_list in tiers:
        rows = "\n".join(listing_row(s) for s in tier_list)
        if not rows:
            rows = '<tr><td colspan="5" class="empty">No listings in this tier.</td></tr>'
        sections.append(f"""
          <section>
            <h2>Tier {tier_num} <small>{tier_name}</small></h2>
            <table>
              <thead>
                <tr>
                  <th>Company</th>
                  <th>Role</th>
                  <th>Location</th>
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
    <p class="summary">{len(scored_listings)} new listings found on {date_str}</p>
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
