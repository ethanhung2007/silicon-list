#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OPENCLAW_CONFIG="${OPENCLAW_CONFIG:-$HOME/.openclaw/openclaw.json}"
OPENCLAW_WORKSPACE="${OPENCLAW_WORKSPACE:-$HOME/.openclaw/workspace}"
EXPORT_FILE="${OPENCLAW_EXPORT_FILE:-$HOME/.silicon-list/openclaw-listings.json}"
OUTPUT_DIR="${SILICON_LIST_OUTPUT_DIR:-$HOME/.silicon-list}"
SILICON_PROVIDER="${SILICON_LIST_PROVIDER:-all}"
STAGE1_PROVIDER="${SILICON_STAGE1_PROVIDER:-all}"
SESSION_ID="${OPENCLAW_SESSION_ID:-silicon-list}"
TIMEOUT_SECONDS="${OPENCLAW_TIMEOUT_SECONDS:-900}"
MAX_LISTINGS="${OPENCLAW_MAX_LISTINGS:-60}"
REPAIR_TIMEOUT_SECONDS="${OPENCLAW_REPAIR_TIMEOUT_SECONDS:-300}"
OPENCLAW_MAX_LEADS="${OPENCLAW_MAX_LEADS:-25}"
OPENCLAW_SEARCH_DEPTH="${OPENCLAW_SEARCH_DEPTH:-normal}"
OPENCLAW_MODEL="${OPENCLAW_MODEL:-}"
SEARCH_WIDTH="${OPENCLAW_SEARCH_WIDTH:-broad}"
STAGE1_OUTPUT_DIR="${SILICON_STAGE1_OUTPUT_DIR:-$OUTPUT_DIR/stage1}"

if [[ -z "${SEARXNG_BASE_URL:-}" && -n "${SEARXNG_URL:-}" ]]; then
  export SEARXNG_BASE_URL="$SEARXNG_URL"
fi
if [[ -z "${SEARXNG_BASE_URL:-}" ]]; then
  export SEARXNG_BASE_URL="http://localhost:8080"
fi

usage() {
  cat <<EOF
Usage: $(basename "$0") [--skip-openclaw] [--no-reset-seen] [--no-open-html]

Runs OpenClaw to gather listings into:
  $EXPORT_FILE

Then runs Silicon List against that export and opens:
  $OUTPUT_DIR/results.html

Environment overrides:
  OPENCLAW_CONFIG
  OPENCLAW_WORKSPACE
  OPENCLAW_EXPORT_FILE
  SILICON_LIST_OUTPUT_DIR
  SILICON_LIST_PROVIDER
  SILICON_STAGE1_PROVIDER
  SILICON_STAGE1_OUTPUT_DIR
  OPENCLAW_SESSION_ID
  OPENCLAW_TIMEOUT_SECONDS
  OPENCLAW_REPAIR_TIMEOUT_SECONDS (default: 300)
  OPENCLAW_MAX_LISTINGS
  OPENCLAW_MAX_LEADS
  OPENCLAW_SEARCH_DEPTH
  OPENCLAW_MODEL
  OPENCLAW_SEARCH_WIDTH
  SEARXNG_URL
  SEARXNG_BASE_URL (defaults to http://localhost:8080)
EOF
}

SKIP_OPENCLAW=0
RESET_SEEN=1
OPEN_HTML=1

run_with_timeout() {
  local seconds="$1"
  local label="$2"
  shift 2

  if command -v timeout >/dev/null 2>&1; then
    set +e
    timeout --kill-after=15s "${seconds}s" "$@"
    local status=$?
    set -e
    if [[ "$status" -eq 124 || "$status" -eq 137 ]]; then
      echo "$label timed out after ${seconds}s; continuing with any existing export." >&2
    fi
    return "$status"
  fi

  echo "Command 'timeout' not found; running $label without a hard shell timeout." >&2
  set +e
  "$@"
  local status=$?
  set -e
  return "$status"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-openclaw)
      SKIP_OPENCLAW=1
      shift
      ;;
    --no-reset-seen)
      RESET_SEEN=0
      shift
      ;;
    --no-open-html)
      OPEN_HTML=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

extract_gateway_token() {
  node -e "
const fs = require('fs');
const path = process.argv[1];
const config = JSON.parse(fs.readFileSync(path, 'utf8'));
const token = config?.gateway?.auth?.token;
if (!token) process.exit(1);
process.stdout.write(token);
" "$OPENCLAW_CONFIG"
}

validate_export() {
  "$PYTHON_BIN" - "$EXPORT_FILE" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1]).expanduser()
if not path.exists():
    raise SystemExit(f"OpenClaw export was not created: {path}")

with path.open() as f:
    try:
        data = json.load(f)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"OpenClaw export is invalid JSON at {path}: {exc}")

rows = data.get("listings", data) if isinstance(data, dict) else data
if not isinstance(rows, list):
    raise SystemExit("OpenClaw export must be a JSON list or an object with a listings list.")

print(f"Validated OpenClaw export: {len(rows)} listings at {path}")
PY
}

run_stage1_discovery() {
  mkdir -p "$STAGE1_OUTPUT_DIR"
  echo "Running Stage 1 broad discovery with provider: $STAGE1_PROVIDER"

  local stage1_args=(
    --mode live
    --pipeline hybrid
    --provider "$STAGE1_PROVIDER"
    --openclaw-stage2 false
    --hardware-bias true
    --json-export
    --dry-run
    --no-open-html
    --output-dir "$STAGE1_OUTPUT_DIR"
  )

  if command -v silicon-list >/dev/null 2>&1; then
    silicon-list "${stage1_args[@]}" || true
  else
    "$PYTHON_BIN" -m silicon_list.main "${stage1_args[@]}" || true
  fi
}

stage1_leads_json() {
  "$PYTHON_BIN" - "$STAGE1_OUTPUT_DIR/results.json" "$OPENCLAW_MAX_LEADS" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1]).expanduser()
limit = int(sys.argv[2])
if not path.exists():
    print("[]")
    raise SystemExit

try:
    rows = json.loads(path.read_text())
except json.JSONDecodeError:
    print("[]")
    raise SystemExit

leads = []
for row in rows[:limit]:
    if not isinstance(row, dict):
        continue
    leads.append({
        "company": row.get("company", ""),
        "role": row.get("role", ""),
        "location": row.get("location", ""),
        "apply_url": row.get("apply_url", ""),
        "source_url": row.get("source_url", ""),
        "cycle": row.get("cycle", ""),
        "source": row.get("source", ""),
    })

print(json.dumps(leads, ensure_ascii=True, separators=(",", ":")))
PY
}

collect_link_issues() {
  PYTHONPATH="$PROJECT_DIR" "$PYTHON_BIN" - "$EXPORT_FILE" <<'PY'
import json
import sys
from pathlib import Path

from silicon_list.models import Listing
from silicon_list.pipeline.filtering import has_bad_apply_url, is_generic_openclaw_listing

path = Path(sys.argv[1]).expanduser()
if not path.exists():
    print("[]")
    raise SystemExit

with path.open() as f:
    try:
        data = json.load(f)
    except json.JSONDecodeError:
        print("[]")
        raise SystemExit

rows = data.get("listings", data) if isinstance(data, dict) else data
if not isinstance(rows, list):
    print("[]")
    raise SystemExit

issues = []
for index, row in enumerate(rows):
    if not isinstance(row, dict):
        continue
    listing = Listing(
        source="openclaw",
        source_job_id=str(row.get("source_job_id") or row.get("id") or index),
        company=str(row.get("company") or row.get("employer") or "Unknown").strip(),
        role=str(row.get("role") or row.get("title") or "Unknown role").strip(),
        location=str(row.get("location") or "").strip(),
        apply_url=str(row.get("apply_url") or row.get("url") or row.get("link") or "").strip(),
        description=str(row.get("description") or row.get("snippet") or "").strip(),
        posted_at=str(row.get("posted_at") or row.get("posted") or "").strip() or None,
        cycle=str(row.get("cycle") or row.get("term") or "").strip(),
    )
    reason = ""
    if has_bad_apply_url(listing):
        reason = "search_or_generic_url"
    elif is_generic_openclaw_listing(listing):
        reason = "not_exact_posting_url"
    if reason:
        issues.append({
            "index": index,
            "company": listing.company,
            "role": listing.role,
            "current_apply_url": listing.apply_url,
            "reason": reason,
        })

print(json.dumps(issues[:20], separators=(",", ":")))
PY
}

snapshot_export() {
  if [[ -f "$EXPORT_FILE" ]]; then
    cp "$EXPORT_FILE" "$EXPORT_FILE.bak"
  fi
}

restore_export_if_missing() {
  if [[ ! -f "$EXPORT_FILE" && -f "$EXPORT_FILE.bak" ]]; then
    echo "OpenClaw did not create a new export; restoring previous export from $EXPORT_FILE.bak" >&2
    cp "$EXPORT_FILE.bak" "$EXPORT_FILE"
  fi
}

complete_openclaw_bootstrap() {
  local workspace="$1"
  local bootstrap_file="$workspace/BOOTSTRAP.md"

  if [[ ! -f "$bootstrap_file" ]]; then
    return
  fi

  echo "Completing OpenClaw bootstrap for unattended run..."
  mkdir -p "$workspace"
  cat >"$workspace/IDENTITY.md" <<'EOF'
# IDENTITY.md - Who Am I?

- **Name:** OpenClaw
- **Creature:** AI assistant
- **Vibe:** Direct, practical, and task-focused
- **Emoji:** :lobster:
- **Avatar:**

## Operating Notes

For Silicon List runs, prioritize the requested data collection task over onboarding.
EOF

  cat >"$workspace/USER.md" <<'EOF'
# USER.md - About Your Human

- **Name:** Ethan
- **What to call them:** Ethan
- **Pronouns:** _(optional)_
- **Timezone:** America/Chicago
- **Notes:** Wants current hardware, silicon, FPGA, RTL, ASIC, verification, firmware, and embedded systems internship/co-op listings.

## Context

This workspace is used for unattended Silicon List job-search exports. Do not pause for identity setup during these runs.
EOF

  if [[ -f "$workspace/SOUL.md" ]] && ! grep -q "Silicon List unattended runs" "$workspace/SOUL.md"; then
    cat >>"$workspace/SOUL.md" <<'EOF'

## Silicon List unattended runs

When invoked by the Silicon List runner, complete the requested listing search and write the requested JSON export without stopping for onboarding.
EOF
  fi

  rm "$bootstrap_file"
}

require_command node
if command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
else
  echo "Missing required command: python or python3" >&2
  exit 1
fi

mkdir -p "$OUTPUT_DIR"
cd "$PROJECT_DIR"
if [[ -f "$PROJECT_DIR/venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$PROJECT_DIR/venv/bin/activate"
fi

if [[ "$SKIP_OPENCLAW" -eq 0 ]]; then
  require_command openclaw

  if [[ ! -f "$OPENCLAW_CONFIG" ]]; then
    echo "OpenClaw config not found: $OPENCLAW_CONFIG" >&2
    echo "Run: openclaw configure --section model --section gateway --section daemon" >&2
    exit 1
  fi

  export OPENCLAW_GATEWAY_TOKEN="${OPENCLAW_GATEWAY_TOKEN:-$(extract_gateway_token)}"
  complete_openclaw_bootstrap "$OPENCLAW_WORKSPACE"

  if [[ -n "$OPENCLAW_MODEL" ]]; then
    echo "Setting OpenClaw model to $OPENCLAW_MODEL..."
    openclaw models set "$OPENCLAW_MODEL"
  fi

  run_stage1_discovery
  STAGE1_LEADS="$(stage1_leads_json)"

  snapshot_export

  PROMPT="Ignore onboarding and identity setup. Complete this bounded Stage 2 browser-agent task and finish within the timeout. Search width: $SEARCH_WIDTH. Search depth: $OPENCLAW_SEARCH_DEPTH. Stage 1 already did broad fast discovery from free public GitHub/job-list sources. Use browser automation like a human researcher: open public search pages, job boards, company career portals, and direct ATS pages; navigate results; open individual postings; validate the page; then extract structured rows. Do not use Google APIs, SerpAPI, paid scraping APIs, paid external data sources, or any API keys. Find up to $MAX_LISTINGS current hardware, silicon, semiconductor, FPGA, RTL, ASIC, DV, verification, physical design, firmware, embedded systems, robotics hardware/firmware, computer architecture, low-level systems, analog, mixed-signal, validation, test, and electrical engineering internship, co-op, and new grad listings for 2026-2027. Optimize for broad coverage, but only publish exact job posting links.

Stage 1 high-value leads to inspect or enrich first:
$STAGE1_LEADS

Use a wide search plan. Run multiple targeted searches instead of one broad search:
1. FPGA intern 2026 site:jobs.lever.co OR site:boards.greenhouse.io OR site:ashbyhq.com
2. RTL intern 2026 site:workdayjobs.com OR site:myworkdayjobs.com
3. ASIC verification intern 2026 site:jobs.ashbyhq.com OR site:greenhouse.io
4. firmware intern 2026 embedded systems intern 2026
5. hardware engineering co-op fall 2026 OR spring 2027
6. silicon engineering intern 2026 company careers
7. physical design intern 2026 OR VLSI intern 2026
8. EDA intern 2026 OR design verification intern 2026
9. site:indeed.com/viewjob fpga OR rtl OR asic OR firmware intern 2026
10. site:linkedin.com/jobs/view hardware OR silicon OR embedded intern 2026
11. site:glassdoor.com/job-listing verification OR physical design OR vlsi intern 2026
12. site:joinhandshake.com/stu/jobs OR site:app.joinhandshake.com/stu/jobs hardware co-op OR firmware intern 2026
13. site:simplify.jobs/p fpga OR hardware OR firmware OR embedded intern 2026
14. semiconductor intern OR chip design intern OR computer architecture intern summer 2027
15. analog intern OR mixed signal intern OR validation intern summer 2026
16. robotics firmware intern OR embedded hardware intern fall 2026 OR spring 2027

Also check direct ATS/job board result pages from Lever, Greenhouse, Ashby, Workday, SmartRecruiters, iCIMS, Oracle Cloud, SuccessFactors, Built In, Indeed, Handshake, Glassdoor, LinkedIn, Simplify, company-specific hiring pages, and GitHub-hosted internship/job lists.

For each listing, apply_url must be the exact posting page, not a company careers homepage, ATS landing page, search page, internship program page, or page listing multiple jobs. Good URLs include Workday /job/ pages, Greenhouse numeric /jobs/<id> pages, Lever posting pages, Ashby posting pages, LinkedIn /jobs/view/<id>, Indeed /viewjob?jk=, Handshake /stu/jobs/<id>, Glassdoor /job-listing/, Simplify /p/, or a company-specific posting URL with a req/job id. Validate each page when possible: HTTP 200, no redirect loop, page still open, title appears on page, apply button exists, and requisition/job id exists if available. Add validation_status, http_status, title_found, apply_button_found, page_status, and requisition_id fields when known. If you can identify a promising role but cannot find an exact posting URL, do not include it in listings; keep it only as a candidate URL in another row's alternate_urls if useful. Do not apply to anything. Exclude obvious non-student roles requiring clearance, ITAR, U.S. citizenship, U.S. person status, senior, staff, principal, manager, or director.

Save a JSON file at $EXPORT_FILE with exactly this structure: {\"listings\":[{\"company\":\"...\",\"role\":\"...\",\"location\":\"...\",\"apply_url\":\"...\",\"source_url\":\"...\",\"canonical_url\":\"...\",\"alternate_urls\":[\"...\"],\"description\":\"...\",\"posted_at\":\"...\",\"cycle\":\"...\"}]}. Do not include duplicates. If you cannot find $MAX_LISTINGS listings before the time limit, still write valid JSON with the listings found so far."

  echo "Running OpenClaw listing search. This can take a while..."
  run_with_timeout "$TIMEOUT_SECONDS" "OpenClaw listing search" openclaw agent \
    --local \
    --session-id "$SESSION_ID" \
    --timeout "$TIMEOUT_SECONDS" \
    --thinking low \
    --message "$PROMPT" || true

  restore_export_if_missing

  LINK_ISSUES="$(collect_link_issues)"
  if [[ "$LINK_ISSUES" != "[]" ]]; then
    echo "OpenClaw produced some general links. Asking it to repair exact posting URLs..."
    REPAIR_BACKUP="$EXPORT_FILE.before-repair"
    cp "$EXPORT_FILE" "$REPAIR_BACKUP"
    REPAIR_PROMPT="The Silicon List export at $EXPORT_FILE contains listings whose apply_url is too general. Do not start over. Repair only the rows listed below, then rewrite the same JSON file with the corrected listings.

Rows needing repair:
$LINK_ISSUES

For every repaired row, apply_url must be the exact job posting URL for that role. Use these URL shapes as the standard:
- Greenhouse: https://boards.greenhouse.io/<company>/jobs/<numeric-id> or https://job-boards.greenhouse.io/<company>/jobs/<numeric-id>
- Lever: https://jobs.lever.co/<company>/<posting-id>
- Ashby: https://jobs.ashbyhq.com/<company>/<posting-id>
- Workday: a company Workday URL containing /job/
- LinkedIn: https://www.linkedin.com/jobs/view/<job-id> or a jobs/view URL ending in a numeric job id
- Indeed: https://www.indeed.com/viewjob?jk=<job-key>
- Glassdoor: a /job-listing/ URL for the exact role
- Handshake: a /stu/jobs/<numeric-id> URL for the exact role

Do not use a company homepage, company careers page, ATS landing page, search page, internship program page, or a page listing multiple jobs. If you cannot find the exact posting URL for a listed role, remove that row from listings rather than publishing a generic apply_url. Keep the same JSON shape, with validation fields allowed: {\"listings\":[{\"company\":\"...\",\"role\":\"...\",\"location\":\"...\",\"apply_url\":\"...\",\"alternate_urls\":[\"...\"],\"description\":\"...\",\"posted_at\":\"...\",\"cycle\":\"...\",\"validation_status\":\"validated\",\"http_status\":200,\"title_found\":true,\"apply_button_found\":true,\"page_status\":\"open\",\"requisition_id\":\"...\"}]}."

    run_with_timeout "$REPAIR_TIMEOUT_SECONDS" "OpenClaw repair" openclaw agent \
      --local \
      --session-id "$SESSION_ID" \
      --timeout "$REPAIR_TIMEOUT_SECONDS" \
      --thinking low \
      --message "$REPAIR_PROMPT" || true

    restore_export_if_missing
    if ! validate_export >/dev/null; then
      echo "OpenClaw repair produced invalid JSON; restoring pre-repair export from $REPAIR_BACKUP" >&2
      cp "$REPAIR_BACKUP" "$EXPORT_FILE"
    fi
  fi
fi

validate_export

SILICON_ARGS=(
  --mode live
  --pipeline hybrid
  --provider "$SILICON_PROVIDER"
  --openclaw-file "$EXPORT_FILE"
  --openclaw-stage2 true
  --openclaw-max-leads "$OPENCLAW_MAX_LEADS"
  --openclaw-search-depth "$OPENCLAW_SEARCH_DEPTH"
  --hardware-bias true
  --output-dir "$OUTPUT_DIR"
)

if [[ "$RESET_SEEN" -eq 1 ]]; then
  SILICON_ARGS+=(--reset-seen)
fi

if [[ "$OPEN_HTML" -eq 0 ]]; then
  SILICON_ARGS+=(--no-open-html)
fi

echo "Running Silicon List..."
echo "Silicon List provider: $SILICON_PROVIDER"
if command -v silicon-list >/dev/null 2>&1; then
  silicon-list "${SILICON_ARGS[@]}"
else
  "$PYTHON_BIN" -m silicon_list.main "${SILICON_ARGS[@]}"
fi
