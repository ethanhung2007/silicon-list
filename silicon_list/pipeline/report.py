import datetime
from html import escape
from pathlib import Path
from typing import List, Tuple
from silicon_list.models import ScoredListing, Listing
from silicon_list.config import Config
from silicon_list.pipeline.scoring import listing_tags, listing_type

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
        lines.append("| Company | Role Title | Location | Type | Date Found | Source | Direct Apply Link | Confidence Score | Tags |")
        lines.append("|---|---|---|---|---|---|---|---:|---|")
        for s in category_list:
            link_url = s.listing.apply_url or s.listing.canonical_url or s.listing.source_url
            apply_link = f"[link]({link_url})" if link_url else "No link"
            date_found = str(s.listing.raw_metadata.get("date_found") or date_str)
            source = s.listing.source.replace("_", " ").title()
            tags = ", ".join(s.listing.raw_metadata.get("tags") or listing_tags(s.listing, config))
            lines.append(
                f"| {s.listing.company} | {s.listing.role} | {s.listing.location} | "
                f"{listing_type(s.listing)} | {date_found} | {source} | {apply_link} | {s.score} | {tags} |"
            )
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
    new_count: int | None = None,
):
    """Writes a self-contained, filterable, sortable HTML dashboard."""

    config = config or Config()
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    sections_data = prepare_report_sections(scored_listings, config)
    shown_count = sum(len(section_list) for _, section_list in sections_data)

    skipped_hard = [s for s, reason in skipped if reason == "hard_exclusion"]
    skipped_companies = sorted(set(s.company for s in skipped_hard))

    tier_counts = {1: 0, 2: 0, 3: 0}
    for s in scored_listings:
        if s.tier in tier_counts:
            tier_counts[s.tier] += 1

    new_label = f" · {new_count} new" if new_count is not None else ""

    def listing_row(s: ScoredListing, category: str) -> str:
        listing = s.listing
        link_url = listing.apply_url or listing.canonical_url or listing.source_url
        link_label = "Apply →" if listing.apply_url else "Source →"
        link_title_parts = []
        if listing.source_url and listing.source_url != link_url:
            link_title_parts.append(f"source: {listing.source_url}")
        if listing.alternate_urls:
            link_title_parts.append(f"alternates: {', '.join(listing.alternate_urls[:3])}")
        link_title = escape(" | ".join(link_title_parts), quote=True)
        title_attr = f' title="{link_title}"' if link_title else ""
        apply_link = (
            f'<a class="apply t{s.tier}" href="{escape(link_url, quote=True)}" target="_blank" rel="noreferrer"{title_attr}>{escape(link_label)}</a>'
            if link_url else
            '<span class="muted">No link</span>'
        )
        source = escape(listing.source.replace("_", " ").title())
        tags_list = listing.raw_metadata.get("tags") or listing_tags(listing, config)
        tags = escape(", ".join(tags_list))
        cycle = escape(listing.cycle or "")
        date_found = escape(str(listing.raw_metadata.get("date_found") or date_str))
        ltype = escape(listing_type(listing))

        # data attributes for JS filtering
        data = (
            f'data-tier="{s.tier}" '
            f'data-company="{escape(listing.company.lower(), quote=True)}" '
            f'data-source="{escape(listing.source.lower(), quote=True)}" '
            f'data-location="{escape((listing.location or "").lower(), quote=True)}" '
            f'data-cycle="{escape((listing.cycle or "").lower(), quote=True)}" '
            f'data-tags="{escape(", ".join(tags_list).lower(), quote=True)}" '
            f'data-category="{escape(category.lower(), quote=True)}" '
            f'data-score="{s.score}" '
            f'data-date="{date_found}"'
        )

        return (
            f'<tr class="tier{s.tier}" {data}>'
            f'<td><strong>{escape(listing.company)}</strong>'
            f'<span class="cycle">{cycle}</span></td>'
            f'<td>{escape(listing.role)}</td>'
            f'<td>{escape(listing.location or "Unknown")}</td>'
            f'<td>{ltype}</td>'
            f'<td>{date_found}</td>'
            f'<td>{source}</td>'
            f'<td class="score">{s.score}</td>'
            f'<td class="tags">{tags}</td>'
            f'<td>{apply_link}</td>'
            f'</tr>'
        )

    sections_html = []
    for category, category_list in sections_data:
        rows = "\n".join(listing_row(s, category) for s in category_list)
        if not rows:
            rows = '<tr><td colspan="9" class="empty">No listings in this category.</td></tr>'
        sections_html.append(
            f'<section data-category="{escape(category.lower(), quote=True)}">'
            f'<h2>{escape(category)}<small>({len(category_list)})</small></h2>'
            f'<table>'
            f'<thead><tr>'
            f'<th>Company</th>'
            f'<th class="sortable" data-col="1">Role Title</th>'
            f'<th>Location</th>'
            f'<th>Type</th>'
            f'<th class="sortable" data-col="5">Date Found</th>'
            f'<th>Source</th>'
            f'<th class="sortable" data-col="6">Score ↕</th>'
            f'<th>Tags</th>'
            f'<th>Apply</th>'
            f'</tr></thead>'
            f'<tbody>{rows}</tbody>'
            f'</table>'
            f'</section>'
        )

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
      --t1-bg: #f0fdf4;
      --t1-border: #86efac;
      --t2-bg: #fefce8;
      --t2-border: #fde047;
      --t3-bg: #f8fafc;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.5;
    }}
    header {{
      padding: 28px 24px 20px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }}
    h1 {{ font-size: 28px; margin-bottom: 6px; }}
    .stats {{
      display: flex;
      gap: 16px;
      flex-wrap: wrap;
      margin-top: 8px;
      font-size: 14px;
      color: var(--muted);
    }}
    .stat {{ display: flex; align-items: center; gap: 4px; }}
    .badge {{
      display: inline-block;
      padding: 1px 7px;
      border-radius: 99px;
      font-size: 12px;
      font-weight: 600;
    }}
    .badge-t1 {{ background: #dcfce7; color: #166534; }}
    .badge-t2 {{ background: #fef9c3; color: #854d0e; }}
    .badge-t3 {{ background: #f1f5f9; color: #475569; }}
    .filters {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      padding: 14px 24px;
      background: var(--panel);
      border-bottom: 1px solid var(--line);
    }}
    .filters input, .filters select {{
      padding: 7px 10px;
      border: 1px solid var(--line);
      border-radius: 6px;
      font-size: 14px;
      color: var(--text);
      background: var(--bg);
      outline: none;
    }}
    .filters input {{ min-width: 200px; flex: 1; }}
    .filters input:focus, .filters select:focus {{ border-color: var(--accent); }}
    main {{
      width: min(1260px, calc(100% - 32px));
      margin: 20px auto 60px;
    }}
    section {{ margin-top: 28px; }}
    section[hidden] {{ display: none; }}
    h2 {{
      font-size: 20px;
      margin-bottom: 10px;
    }}
    h2 small {{
      color: var(--muted);
      font-size: 13px;
      font-weight: 400;
      margin-left: 6px;
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
      padding: 10px 13px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
      font-size: 14px;
    }}
    th {{
      background: #eef2f6;
      color: #344054;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      white-space: nowrap;
    }}
    th.sortable {{ cursor: pointer; user-select: none; }}
    th.sortable:hover {{ background: #e2e8f0; }}
    tr:last-child td {{ border-bottom: 0; }}
    tr[hidden] {{ display: none; }}
    tr.tier1 {{ background: var(--t1-bg); }}
    tr.tier1:hover {{ background: #dcfce7; }}
    tr.tier2 {{ background: var(--t2-bg); }}
    tr.tier2:hover {{ background: #fef08a44; }}
    tr.tier3 {{ background: var(--t3-bg); }}
    tr.tier3:hover {{ background: #e2e8f0; }}
    td span.cycle {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-top: 2px;
    }}
    .score {{
      font-weight: 700;
      text-align: right;
      white-space: nowrap;
    }}
    .tags {{ color: var(--muted); font-size: 12px; max-width: 160px; }}
    .apply {{
      display: inline-block;
      color: #fff;
      padding: 6px 12px;
      border-radius: 6px;
      font-weight: 600;
      text-decoration: none;
      white-space: nowrap;
      font-size: 13px;
    }}
    .apply.t1 {{ background: #15803d; }}
    .apply.t1:hover {{ background: #166534; }}
    .apply.t2 {{ background: #d97706; }}
    .apply.t2:hover {{ background: #b45309; }}
    .apply.t3 {{ background: #64748b; }}
    .apply.t3:hover {{ background: #475569; }}
    .empty, .muted {{ color: var(--muted); }}
    footer {{
      margin-top: 32px;
      color: var(--muted);
      font-size: 13px;
      padding-bottom: 16px;
    }}
    #no-results {{
      display: none;
      text-align: center;
      padding: 40px;
      color: var(--muted);
    }}
    @media (max-width: 800px) {{
      .filters {{ padding: 12px 16px; }}
      main {{ width: calc(100% - 20px); margin-top: 12px; }}
      table {{ display: block; overflow-x: auto; }}
      th, td {{ min-width: 100px; }}
      h1 {{ font-size: 22px; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Silicon List</h1>
    <div class="stats">
      <span class="stat">{shown_count} listings shown{new_label} &nbsp;·&nbsp; {date_str}</span>
      <span class="stat"><span class="badge badge-t1">Tier 1</span> {tier_counts[1]}</span>
      <span class="stat"><span class="badge badge-t2">Tier 2</span> {tier_counts[2]}</span>
      <span class="stat"><span class="badge badge-t3">Tier 3</span> {tier_counts[3]}</span>
    </div>
  </header>
  <div class="filters">
    <input id="q" type="search" placeholder="Filter by company, role, tags…" autocomplete="off">
    <select id="f-tier">
      <option value="">All tiers</option>
      <option value="1">Tier 1 (≥75)</option>
      <option value="2">Tier 2 (50–74)</option>
      <option value="3">Tier 3 (25–49)</option>
    </select>
    <select id="f-source">
      <option value="">All sources</option>
      <option value="github_simplify">GitHub Simplify</option>
      <option value="searxng">SearXNG</option>
      <option value="openclaw">OpenClaw</option>
      <option value="hermes">Hermes</option>
      <option value="google">Google</option>
      <option value="mock">Mock</option>
    </select>
    <select id="f-cycle">
      <option value="">All cycles</option>
      <option value="summer 2026">Summer 2026</option>
      <option value="fall 2026">Fall 2026</option>
      <option value="spring 2027">Spring 2027</option>
      <option value="summer 2027">Summer 2027</option>
    </select>
  </div>
  <main>
    {"".join(sections_html)}
    <div id="no-results">No listings match the current filters.</div>
    <footer>{skipped_text}</footer>
  </main>
  <script>
    (function () {{
      var q = document.getElementById('q');
      var fTier = document.getElementById('f-tier');
      var fSource = document.getElementById('f-source');
      var fCycle = document.getElementById('f-cycle');
      var noResults = document.getElementById('no-results');

      function applyFilters() {{
        var text = q.value.toLowerCase().trim();
        var tier = fTier.value;
        var source = fSource.value.toLowerCase();
        var cycle = fCycle.value.toLowerCase();
        var visibleTotal = 0;

        document.querySelectorAll('section').forEach(function (sec) {{
          var rows = sec.querySelectorAll('tbody tr[data-tier]');
          var visible = 0;
          rows.forEach(function (row) {{
            var match = true;
            if (tier && row.dataset.tier !== tier) match = false;
            if (source && row.dataset.source.indexOf(source) === -1) match = false;
            if (cycle && row.dataset.cycle.indexOf(cycle) === -1) match = false;
            if (text) {{
              var haystack = (row.dataset.company || '') + ' ' +
                             row.textContent.toLowerCase();
              if (haystack.indexOf(text) === -1) match = false;
            }}
            row.hidden = !match;
            if (match) visible++;
          }});
          sec.hidden = visible === 0;
          visibleTotal += visible;
        }});
        noResults.style.display = visibleTotal === 0 ? 'block' : 'none';
      }}

      [q, fTier, fSource, fCycle].forEach(function (el) {{
        el.addEventListener('input', applyFilters);
      }});

      document.querySelectorAll('th.sortable').forEach(function (th) {{
        th.addEventListener('click', function () {{
          var tbody = th.closest('table').querySelector('tbody');
          var col = parseInt(th.dataset.col);
          var asc = th.dataset.asc !== '1';
          th.dataset.asc = asc ? '1' : '0';
          var rows = Array.from(tbody.querySelectorAll('tr[data-tier]'));
          rows.sort(function (a, b) {{
            var av = a.cells[col] ? a.cells[col].textContent.trim() : '';
            var bv = b.cells[col] ? b.cells[col].textContent.trim() : '';
            var an = parseFloat(av), bn = parseFloat(bv);
            if (!isNaN(an) && !isNaN(bn)) return asc ? an - bn : bn - an;
            return asc ? av.localeCompare(bv) : bv.localeCompare(av);
          }});
          rows.forEach(function (r) {{ tbody.appendChild(r); }});
        }});
      }});
    }})();
  </script>
</body>
</html>
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write(html)
