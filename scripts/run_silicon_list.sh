#!/usr/bin/env bash
# One-command Silicon List runner.
# Collects from OpenClaw + Hermes when available, then runs GitHub/SearXNG/Google/import providers
# through Silicon List and writes a single HTML report.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_DIR="${SILICON_LIST_OUTPUT_DIR:-$HOME/.silicon-list}"
OPENCLAW_FILE="${OPENCLAW_EXPORT_FILE:-$OUTPUT_DIR/openclaw-listings.json}"
HERMES_FILE="${HERMES_EXPORT_FILE:-$OUTPUT_DIR/hermes-listings.json}"
PROMPT_FILE="${SILICON_LIST_PROMPT_FILE:-$PROJECT_DIR/prompts/hermes_hardware_jobs.txt}"
OPENCLAW_CONFIG="${OPENCLAW_CONFIG:-$HOME/.openclaw/openclaw.json}"
OPENCLAW_SESSION_ID="${OPENCLAW_SESSION_ID:-silicon-list-openclaw}"
HERMES_SESSION_ID="${HERMES_SESSION_ID:-silicon-list-hermes}"
AGENT_TIMEOUT_SECONDS="${AGENT_TIMEOUT_SECONDS:-900}"
AGENT_MAX_LISTINGS="${AGENT_MAX_LISTINGS:-80}"
SILICON_MODE="${SILICON_LIST_MODE:-live}"
SILICON_PROVIDER="${SILICON_LIST_PROVIDER:-all}"

RUN_OPENCLAW=1
RUN_HERMES=1
RESET_SEEN=1
OPEN_HTML=1
VALIDATE_LINKS=0

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

usage() {
  cat <<EOF
Usage: $(basename "$0") [options]

Runs one end-to-end Silicon List pass:
  1. OpenClaw export -> $OPENCLAW_FILE
  2. Hermes export   -> $HERMES_FILE
  3. Silicon List    -> $OUTPUT_DIR/results.html

Options:
  --skip-openclaw     Do not run OpenClaw; use existing export if present
  --skip-hermes       Do not run Hermes; use existing export if present
  --skip-agents       Do not run either agent; use existing exports + GitHub/etc.
  --no-reset-seen     Keep seen.json so only new listings are shown
  --no-open-html      Write results.html but do not open it
  --validate-links    Run HTTP validation before reporting; slower
  -h, --help

Useful environment overrides:
  SILICON_LIST_OUTPUT_DIR
  OPENCLAW_EXPORT_FILE
  HERMES_EXPORT_FILE
  AGENT_TIMEOUT_SECONDS
  AGENT_MAX_LISTINGS
  SILICON_LIST_MODE
  SILICON_LIST_PROVIDER
  GOOGLE_API_KEY / GOOGLE_CSE_ID
  SEARXNG_URL
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-openclaw) RUN_OPENCLAW=0; shift ;;
    --skip-hermes) RUN_HERMES=0; shift ;;
    --skip-agents) RUN_OPENCLAW=0; RUN_HERMES=0; shift ;;
    --no-reset-seen) RESET_SEEN=0; shift ;;
    --no-open-html) OPEN_HTML=0; shift ;;
    --validate-links) VALIDATE_LINKS=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

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

json_count() {
  local file="$1"
  "$PYTHON_BIN" - "$file" <<'PY' 2>/dev/null || true
import json, sys
from pathlib import Path
path = Path(sys.argv[1]).expanduser()
if not path.exists():
    raise SystemExit
data = json.loads(path.read_text())
rows = data.get("listings", data) if isinstance(data, dict) else data
print(len(rows) if isinstance(rows, list) else 0)
PY
}

build_prompt() {
  local export_file="$1"
  local focus="$2"
  if [[ -f "$PROMPT_FILE" ]]; then
    sed "s|~/.silicon-list/hermes-listings.json|$export_file|g; s|50–150 validated listings|$AGENT_MAX_LISTINGS validated listings|g" "$PROMPT_FILE"
  else
    cat <<EOF
Find current hardware, silicon, FPGA, RTL, ASIC, verification, firmware, embedded systems, physical design, analog, mixed-signal, EDA, and electrical internship/co-op/new-grad listings for 2026-2027. Focus on $focus. Exclude clearance, ITAR, U.S. citizenship, and U.S. person roles. Only include exact open job posting URLs. Save JSON at $export_file with a top-level listings array.
EOF
  fi
}

run_openclaw() {
  if [[ "$RUN_OPENCLAW" -eq 0 ]]; then
    return
  fi
  if ! command -v openclaw >/dev/null 2>&1; then
    echo "OpenClaw not found; skipping OpenClaw collection."
    return
  fi
  if [[ ! -f "$OPENCLAW_CONFIG" ]]; then
    echo "OpenClaw config not found at $OPENCLAW_CONFIG; skipping OpenClaw collection."
    return
  fi

  local prompt
  prompt="Focus on ATS portals and company career pages: Greenhouse, Lever, Ashby, Workday, SmartRecruiters, iCIMS, Oracle Cloud, SuccessFactors.

$(build_prompt "$OPENCLAW_FILE" "ATS portals and company career pages")"

  echo "Running OpenClaw collection..."
  run_with_timeout "$AGENT_TIMEOUT_SECONDS" "OpenClaw collection" openclaw agent \
    --local \
    --session-id "$OPENCLAW_SESSION_ID" \
    --timeout "$AGENT_TIMEOUT_SECONDS" \
    --thinking low \
    --message "$prompt" || echo "OpenClaw collection failed; continuing with any existing export."
}

run_hermes() {
  if [[ "$RUN_HERMES" -eq 0 ]]; then
    return
  fi

  local hermes_bin=""
  if command -v hermes >/dev/null 2>&1; then
    hermes_bin="hermes"
  elif [[ -x "$HOME/.hermes/hermes-agent/venv/bin/hermes" ]]; then
    hermes_bin="$HOME/.hermes/hermes-agent/venv/bin/hermes"
  fi

  local prompt
  prompt="Focus on job boards and discovery pages: LinkedIn, Indeed, Handshake, Simplify, Glassdoor, and company career pages.

$(build_prompt "$HERMES_FILE" "job boards and discovery pages")"

  if [[ -n "$hermes_bin" ]]; then
    echo "Running Hermes collection..."
    local hermes_status
    set +e
    run_with_timeout "$AGENT_TIMEOUT_SECONDS" "Hermes collection" "$hermes_bin" chat \
      -q "$prompt" \
      --yolo \
      --max-turns 90 \
      -Q 2>/dev/null
    hermes_status=$?
    set -e
    if [[ "$hermes_status" -ne 0 && "$hermes_status" -ne 124 && "$hermes_status" -ne 137 ]]; then
      set +e
      run_with_timeout "$AGENT_TIMEOUT_SECONDS" "Hermes collection" "$hermes_bin" \
        -q "$prompt" \
        --yolo \
        --max-turns 90 \
        -Q 2>/dev/null
      hermes_status=$?
      set -e
    fi
    if [[ "$hermes_status" -ne 0 ]]; then
      echo "Hermes collection failed; continuing with any existing export."
    fi
  elif command -v openclaw >/dev/null 2>&1; then
    echo "Hermes not found; running second OpenClaw session with Hermes/job-board focus..."
    run_with_timeout "$AGENT_TIMEOUT_SECONDS" "Hermes fallback collection" openclaw agent \
      --local \
      --session-id "$HERMES_SESSION_ID" \
      --timeout "$AGENT_TIMEOUT_SECONDS" \
      --thinking low \
      --message "$prompt" || echo "Hermes fallback collection failed; continuing with any existing export."
  else
    echo "Hermes not found; skipping Hermes collection."
  fi
}

run_openclaw
run_hermes

openclaw_count="$(json_count "$OPENCLAW_FILE")"
hermes_count="$(json_count "$HERMES_FILE")"
echo "OpenClaw export: ${openclaw_count:-0} listings"
echo "Hermes export: ${hermes_count:-0} listings"

SILICON_ARGS=(
  --mode "$SILICON_MODE"
  --pipeline hybrid
  --provider "$SILICON_PROVIDER"
  --openclaw-file "$OPENCLAW_FILE"
  --openclaw-stage2 true
  --hardware-bias true
  --output-dir "$OUTPUT_DIR"
)

if [[ -f "$HERMES_FILE" ]]; then
  SILICON_ARGS+=(--hermes-file "$HERMES_FILE" --hermes-enabled true)
fi
if [[ "$RESET_SEEN" -eq 1 ]]; then
  SILICON_ARGS+=(--reset-seen)
fi
if [[ "$OPEN_HTML" -eq 0 ]]; then
  SILICON_ARGS+=(--no-open-html)
fi
if [[ "$VALIDATE_LINKS" -eq 1 ]]; then
  SILICON_ARGS+=(--validate-links)
fi

echo "Running Silicon List. HTML report will be at $OUTPUT_DIR/results.html"
if command -v silicon-list >/dev/null 2>&1; then
  silicon-list "${SILICON_ARGS[@]}"
else
  "$PYTHON_BIN" -m silicon_list.main "${SILICON_ARGS[@]}"
fi
