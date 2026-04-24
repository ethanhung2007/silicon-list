# Silicon List — Codebase Audit

## Existing Providers

### GitHubSimplifyProvider (`providers/github_simplify.py`)
**URL type:** Exact listing URLs — parses the SimplifyJobs GitHub README HTML table and extracts direct ATS links (Greenhouse `/jobs/<id>`, Lever, Workday `/job/`). The `_extract_apply_url` method skips simplify.jobs wrapper links and returns the canonical ATS URL directly. The fallback `_parse_hardware_lines` produces source URLs (GitHub README) when no ATS link is parseable, which triggers a `link_validation` failure downstream and correctly filters those rows.

**Assessment:** Good. Produces exact URLs from a curated list. No fix needed.

### GoogleSearchProvider (`providers/google_search.py`)
**URL type:** Search result URLs — results come from Google Search API and may point to ATS pages, Indeed/LinkedIn listing pages, or generic career pages depending on the query. The `site:` query prefix helps narrow to ATS pages, but no URL filtering is applied at the provider level.

**Assessment:** Functional but requires `GOOGLE_API_KEY` + `GOOGLE_CSE_ID`. Not used in no-API-key runs. No fix needed — it's opt-in.

### SearXNGSearchProvider (`providers/searxng_search.py`)
**URL type:** Filtered ATS URLs — `_looks_useful()` checks `DIRECT_URL_TOKENS` against the result URL and discards any URL that doesn't contain a known ATS or job-board token. Combined with `site:` query prefixes in the default queries, this produces mostly exact listing URLs.

**Assessment:** Good. Token filtering is aggressive enough to mostly avoid homepage redirects. No fix needed.

### OpenClawFileProvider (`providers/openclaw_file.py`)
**URL type:** Depends on agent quality — reads from `~/.silicon-list/openclaw-listings.json`. The `select_best_url` call in `_row_to_listing` picks the best URL from multiple candidates. The agent prompt instructs exact posting URLs; the repair loop in `run_openclaw_silicon_list.sh` fixes generic links.

**Assessment:** Good. URL selection logic is solid. No fix needed.

### MockProvider (`providers/mock_provider.py`)
**URL type:** Hardcoded test URLs — uses real ATS URL shapes for testing.

**Assessment:** Good for testing. No fix needed.

---

## Existing Pipeline

### `pipeline/normalize.py`
Cleans tracking params, unwraps redirect URLs, selects best URL from candidates. Solid.

### `pipeline/filtering.py`
Hard exclusions (clearance/ITAR), age filter, cycle filter, link validation (pattern-based), senior/irrelevant filter. Solid.

### `pipeline/link_validation.py`
Pattern-based validation only — no HTTP requests. Validates against known exact-posting URL shapes. Returns `LinkValidationResult(valid, reason, confidence_bonus)`. **Does not make network calls.**

### `pipeline/merge.py`
Stage merging with URL-based and role-based deduplication across discovery stages. Solid.

### `pipeline/dedupe.py`
Cross-run deduplication via `seen.json` state file. Fuzzy role matching with `SequenceMatcher`. Solid.

### `pipeline/scoring.py`
Custom 0–100 scoring starting from 35, with bonuses for hardware role, priority company, US location, cycle, known tools, student type, and link validation. Tiering: ≥85=T1, ≥65=T2, else T3.

**Assessment:** Works but uses different tier thresholds and bonus structure than the spec table. A new `ranker.py` will implement the spec scoring without modifying this file.

### `pipeline/report.py`
Generates Markdown and HTML reports. HTML is functional but not filterable or sortable. Tier color coding is missing. No client-side filtering.

**Assessment:** Enhanced HTML dashboard added (filterable by tier/company/source/cycle, sortable by score, color-coded tiers, tier stats header).

---

## What Is Added

| Component | File | Status |
|-----------|------|--------|
| HTTP link validator | `silicon_list/validator.py` | **New** |
| New scoring ranker | `silicon_list/ranker.py` | **New** |
| Enhanced deduplicator | `silicon_list/deduper.py` | **New** |
| SQLite database | `silicon_list/storage/database.py` | **New** |
| Hermes provider | `silicon_list/providers/hermes.py` | **New** |
| Hermes shell script | `scripts/run_hermes_silicon_list.sh` | **New** |
| Hermes research prompt | `prompts/hermes_hardware_jobs.txt` | **New** |
| Enhanced HTML dashboard | `silicon_list/pipeline/report.py` | **Modified** |
| CLI wiring | `silicon_list/main.py` | **Modified** |
| Config additions | `silicon_list/config.py` | **Modified** |
| Tests | `tests/test_validator.py`, `test_ranker.py`, `test_deduper.py`, `test_providers.py` | **New** |

---

## What Is NOT Changed

- `providers/github_simplify.py` — working correctly
- `providers/google_search.py` — working, opt-in only
- `providers/searxng_search.py` — working correctly
- `providers/openclaw_file.py` — working correctly
- `pipeline/normalize.py` — working correctly
- `pipeline/filtering.py` — working correctly
- `pipeline/link_validation.py` — working correctly (pattern-based)
- `pipeline/merge.py` — working correctly
- `pipeline/dedupe.py` — working correctly (seen.json state)
- `pipeline/scoring.py` — preserved for backward compat; new ranker runs alongside it
