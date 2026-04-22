#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OPENCLAW_CONFIG="${OPENCLAW_CONFIG:-$HOME/.openclaw/openclaw.json}"
OPENCLAW_WORKSPACE="${OPENCLAW_WORKSPACE:-$HOME/.openclaw/workspace}"
EXPORT_FILE="${OPENCLAW_EXPORT_FILE:-$HOME/.silicon-list/openclaw-listings.json}"
OUTPUT_DIR="${SILICON_LIST_OUTPUT_DIR:-$HOME/.silicon-list}"
SILICON_PROVIDER="${SILICON_LIST_PROVIDER:-all}"
SESSION_ID="${OPENCLAW_SESSION_ID:-silicon-list}"
TIMEOUT_SECONDS="${OPENCLAW_TIMEOUT_SECONDS:-900}"
MAX_LISTINGS="${OPENCLAW_MAX_LISTINGS:-30}"
OPENCLAW_MODEL="${OPENCLAW_MODEL:-}"
SEARCH_WIDTH="${OPENCLAW_SEARCH_WIDTH:-broad}"

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
  OPENCLAW_SESSION_ID
  OPENCLAW_TIMEOUT_SECONDS
  OPENCLAW_MAX_LISTINGS
  OPENCLAW_MODEL
  OPENCLAW_SEARCH_WIDTH
EOF
}

SKIP_OPENCLAW=0
RESET_SEEN=1
OPEN_HTML=1

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
    data = json.load(f)

rows = data.get("listings", data) if isinstance(data, dict) else data
if not isinstance(rows, list):
    raise SystemExit("OpenClaw export must be a JSON list or an object with a listings list.")

print(f"Validated OpenClaw export: {len(rows)} listings at {path}")
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

if [[ "$SKIP_OPENCLAW" -eq 0 ]]; then
  require_command openclaw

  if [[ ! -f "$OPENCLAW_CONFIG" ]]; then
    echo "OpenClaw config not found: $OPENCLAW_CONFIG" >&2
    echo "Run: openclaw configure --section model --section gateway --section daemon" >&2
    exit 1
  fi

  export OPENCLAW_GATEWAY_TOKEN="${OPENCLAW_GATEWAY_TOKEN:-$(extract_gateway_token)}"

  if [[ -n "$OPENCLAW_MODEL" ]]; then
    echo "Setting OpenClaw model to $OPENCLAW_MODEL..."
    openclaw models set "$OPENCLAW_MODEL"
  fi

  snapshot_export

  PROMPT="Ignore onboarding and identity setup. Complete this bounded data collection task and finish within the timeout. Search width: $SEARCH_WIDTH. Find up to $MAX_LISTINGS current hardware, silicon, FPGA, RTL, ASIC, verification, firmware, and embedded systems internship or co-op listings for 2026-2027.

Use a wide search plan. Run multiple targeted searches instead of one broad search:
1. FPGA intern 2026 site:jobs.lever.co OR site:boards.greenhouse.io OR site:ashbyhq.com
2. RTL intern 2026 site:workdayjobs.com OR site:myworkdayjobs.com
3. ASIC verification intern 2026 site:jobs.ashbyhq.com OR site:greenhouse.io
4. firmware intern 2026 embedded systems intern 2026
5. hardware engineering co-op fall 2026 OR spring 2027
6. silicon engineering intern 2026 company careers
7. physical design intern 2026 OR VLSI intern 2026
8. EDA intern 2026 OR design verification intern 2026

Also check direct ATS/job board result pages from Lever, Greenhouse, Ashby, Workday, SmartRecruiters, iCIMS, Oracle Cloud, and Built In.

Only include specific internship/co-op job postings with direct application URLs for that exact role. Do not include generic company careers pages, generic internship program pages, search result pages, aggregator collection pages, or pages listing multiple unrelated jobs. Exclude roles that require clearance, ITAR, U.S. citizenship, U.S. person status, new grad, full-time, senior, staff, principal, manager, or director. Prefer search result titles/snippets and direct job URLs over fetching Workday pages directly; Workday pages may fail extraction, but you can still use the exact job title, company, location, direct URL, and snippet from search results if it is clearly a specific internship/co-op posting. Skip any page that cannot be verified as an internship/co-op.

Save a JSON file at $EXPORT_FILE with exactly this structure: {\"listings\":[{\"company\":\"...\",\"role\":\"...\",\"location\":\"...\",\"apply_url\":\"...\",\"description\":\"...\",\"posted_at\":\"...\",\"cycle\":\"...\"}]}. Do not include duplicates. Do not apply to anything. If you cannot find $MAX_LISTINGS listings before the time limit, still write valid JSON with the listings found so far."

  echo "Running OpenClaw listing search. This can take a while..."
  openclaw agent \
    --local \
    --session-id "$SESSION_ID" \
    --timeout "$TIMEOUT_SECONDS" \
    --thinking low \
    --message "$PROMPT"

  restore_export_if_missing
fi

validate_export

cd "$PROJECT_DIR"
if [[ -f "$PROJECT_DIR/venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$PROJECT_DIR/venv/bin/activate"
fi

SILICON_ARGS=(
  --mode live
  --provider "$SILICON_PROVIDER"
  --openclaw-file "$EXPORT_FILE"
  --output-dir "$OUTPUT_DIR"
)

if [[ "$RESET_SEEN" -eq 1 ]]; then
  SILICON_ARGS+=(--reset-seen)
fi

if [[ "$OPEN_HTML" -eq 0 ]]; then
  SILICON_ARGS+=(--no-open-html)
fi

echo "Running Silicon List..."
if command -v silicon-list >/dev/null 2>&1; then
  silicon-list "${SILICON_ARGS[@]}"
else
  "$PYTHON_BIN" -m silicon_list.main "${SILICON_ARGS[@]}"
fi
