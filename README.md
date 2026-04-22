# Silicon List

Silicon List is a local-first Python CLI tool that finds hardware and low-level engineering internship listings, deduplicates them across runs, ranks them into tiers, and outputs structured Markdown and HTML reports.

## Setup

Requires Python 3.10+

```bash
# Create a virtual environment
python -m venv venv
source venv/bin/activate

# Install the project
pip install -e .
```

## Usage

Run the CLI:
```bash
silicon-list --mode live --provider all
```

**Options:**
- `--mode mock|live`: Whether to use live data (GitHub fetching) or mock data.
- `--provider mock|github|google|openclaw|all`: Which provider to use.
- `--openclaw-file PATH`: Import a JSON listing export from OpenClaw or another browser agent.
- `--output-dir PATH`: Override the default directory for files (`~/.silicon-list`).
- `--write-default-config`: Writes the default configuration file and exits.
- `--print-report`: Print the markdown report directly to stdout.
- `--no-open-html`: Generate `results.html` but do not open it.
- `--dry-run`: Do not update `seen.json`, so you can re-run and see the same listings.
- `--reset-seen`: Wipes out `seen.json` before running.
- `--json-export`: Dumps the results to a `results.json` file.

## Google Search Setup

The GitHub provider works without credentials. The Google provider uses the Google Programmable Search JSON API, so set these environment variables before using `--provider google` or live `--provider all`:

```bash
export GOOGLE_API_KEY="your-api-key"
export GOOGLE_CSE_ID="your-search-engine-id"
```

Then run:

```bash
silicon-list --mode live --provider all
```

If those variables are not set, the GitHub provider will still run, and the CLI will print a provider error explaining that Google search was skipped.

## OpenClaw / Browser Agent Imports

Silicon List can ingest structured results from OpenClaw or any browser automation agent. Have the agent browse job boards, company career pages, or Google results, then save JSON to:

```bash
~/.silicon-list/openclaw-listings.json
```

Expected format:

```json
{
  "listings": [
    {
      "company": "Example Robotics",
      "role": "Embedded Firmware Intern",
      "location": "Austin, TX",
      "apply_url": "https://example.com/apply",
      "description": "Work on RTOS firmware and embedded systems.",
      "posted_at": "today",
      "cycle": "Summer 2026"
    }
  ]
}
```

Then run:

```bash
silicon-list --mode live --provider openclaw
```

Or combine GitHub, Google, and OpenClaw imports:

```bash
silicon-list --mode live --provider all
```

You can also run the full OpenClaw-to-report workflow with one script:

```bash
./scripts/run_openclaw_silicon_list.sh
```

The script starts the local OpenClaw Gateway if needed, sends the browser-agent research prompt, validates `~/.silicon-list/openclaw-listings.json`, then runs Silicon List and opens `results.html`.

Useful script flags:

```bash
./scripts/run_openclaw_silicon_list.sh --no-open-html
./scripts/run_openclaw_silicon_list.sh --no-reset-seen
./scripts/run_openclaw_silicon_list.sh --skip-openclaw
```

Useful browser-agent prompt:

```text
Find current hardware, silicon, FPGA, RTL, ASIC, verification, firmware, and embedded systems internship or co-op listings for 2026-2027. Search company career pages and job boards. Exclude roles that require clearance, ITAR, U.S. citizenship, or U.S. person status. Save a JSON file at ~/.silicon-list/openclaw-listings.json with a top-level "listings" array. Each listing must include company, role, location, apply_url, description, posted_at, and cycle when available. Only include direct application links.
```

## Outputs

All outputs by default go to `~/.silicon-list/`:
- `results.html`: The browser report with clickable apply links. This opens automatically after a run.
- `results.md`: The tiered job listings.
- `openclaw-listings.json`: Optional browser-agent import file.
- `seen.json`: State file to prevent duplicate reporting.
- `errors.log`: Error logs (if any).
- `config.json`: Can be generated and edited to tweak search queries and priorities.

## Pluggable Architecture

The system uses `silicon_list.providers.base.BaseProvider`. If you want to integrate a live job board wrapper (like JobSpy), you can simply implement the `fetch_listings()` method and register it in `main.py`.
