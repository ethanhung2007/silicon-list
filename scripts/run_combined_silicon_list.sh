#!/usr/bin/env bash
# Runs BOTH OpenClaw and Hermes (claw agent) in parallel, merges JSON, then runs Silicon List.
# This gives maximum coverage — OpenClaw + Hermes find different listings.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OPENCLAW_FILE="${OPENCLAW_EXPORT_FILE:-$HOME/.silicon-list/openclaw-listings.json}"
HERMES_FILE="${HERMES_EXPORT_FILE:-$HOME/.silicon-list/hermes-listings.json}"
OUTPUT_DIR="${SILICON_LIST_OUTPUT_DIR:-$HOME/.silicon-list}"
TIMEOUT_SECONDS="${AGENT_TIMEOUT_SECONDS:-900}"
MAX_LISTINGS="${AGENT_MAX_LISTINGS:-60}"
OPENCLAW_CONFIG="${OPENCLAW_CONFIG:-$HOME/.openclaw/openclaw.json}"
OPENCLAW_MODEL="${OPENCLAW_MODEL:-}"

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Runs OpenClaw AND Hermes (claw agent) sequentially, merges their JSON outputs,
then runs Silicon List with --provider all to load both.

Options:
  --skip-openclaw     Skip the OpenClaw agent run
  --skip-hermes       Skip the Hermes agent run
  --no-reset-seen     Don't wipe seen.json before running
  --no-open-html      Don't auto-open results.html
  -h, --help

Environment:
  OPENCLAW_EXPORT_FILE   (default: ~/.silicon-list/openclaw-listings.json)
  HERMES_EXPORT_FILE     (default: ~/.silicon-list/hermes-listings.json)
  SILICON_LIST_OUTPUT_DIR
  AGENT_TIMEOUT_SECONDS  (default: 900)
  AGENT_MAX_LISTINGS     (default: 60 each)
  OPENCLAW_MODEL
EOF
}

SKIP_OPENCLAW=0
SKIP_HERMES=0
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
    --skip-openclaw) SKIP_OPENCLAW=1; shift ;;
    --skip-hermes)   SKIP_HERMES=1; shift ;;
    --no-reset-seen) RESET_SEEN=0; shift ;;
    --no-open-html)  OPEN_HTML=0; shift ;;
    -h|--help)       usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if command -v python >/dev/null 2>&1; then PYTHON_BIN="python"
elif command -v python3 >/dev/null 2>&1; then PYTHON_BIN="python3"
else echo "python not found" >&2; exit 1; fi

mkdir -p "$OUTPUT_DIR"
cd "$PROJECT_DIR"
[[ -f "$PROJECT_DIR/venv/bin/activate" ]] && source "$PROJECT_DIR/venv/bin/activate"

snapshot() { [[ -f "$1" ]] && cp "$1" "$1.bak"; }
restore_if_missing() { [[ ! -f "$1" && -f "$1.bak" ]] && cp "$1.bak" "$1" && echo "Restored $1 from backup" >&2; }

validate_json() {
  local file="$1" label="$2"
  "$PYTHON_BIN" - "$file" "$label" <<'PY'
import json, sys
from pathlib import Path
path, label = Path(sys.argv[1]), sys.argv[2]
if not path.exists():
    print(f"  {label}: no export file at {path}", file=sys.stderr)
    sys.exit(1)
with path.open() as f:
    data = json.load(f)
rows = data.get("listings", data) if isinstance(data, dict) else data
print(f"  {label}: {len(rows)} listings")
PY
}

# --- Build the agent prompt ---
build_prompt() {
  local export_file="$1" max="$2"
  cat "$PROJECT_DIR/prompts/hermes_hardware_jobs.txt" \
    | sed "s|~/.silicon-list/hermes-listings.json|$export_file|g" \
    | sed "s|50–150 validated listings|${max} validated listings|g"
}

OPENCLAW_PROMPT="$(build_prompt "$OPENCLAW_FILE" "$MAX_LISTINGS")"
HERMES_PROMPT="$(build_prompt "$HERMES_FILE" "$MAX_LISTINGS")"

# Tweak the OpenClaw prompt slightly so the two agents search different companies
OPENCLAW_PROMPT="Focus on ATS portals: Greenhouse, Lever, Ashby, Workday, SmartRecruiters, iCIMS.
${OPENCLAW_PROMPT/Output a JSON file at/Output at} ${OPENCLAW_FILE}"

HERMES_PROMPT="Focus on job boards: LinkedIn, Indeed, Handshake, Simplify, Glassdoor, company career pages.
${HERMES_PROMPT}"

# -------------------------------------------------------
# Run OpenClaw
# -------------------------------------------------------
if [[ "$SKIP_OPENCLAW" -eq 0 ]]; then
  if ! command -v openclaw >/dev/null 2>&1; then
    echo "openclaw not found — skipping OpenClaw run" >&2
    SKIP_OPENCLAW=1
  else
    if [[ ! -f "$OPENCLAW_CONFIG" ]]; then
      echo "OpenClaw config not found: $OPENCLAW_CONFIG" >&2
      echo "Run: openclaw configure --section model --section gateway --section daemon" >&2
      SKIP_OPENCLAW=1
    fi
  fi
fi

if [[ "$SKIP_OPENCLAW" -eq 0 ]]; then
  if [[ -n "$OPENCLAW_MODEL" ]]; then
    openclaw models set "$OPENCLAW_MODEL" 2>/dev/null || true
  fi

  # Extract gateway token
  OPENCLAW_GATEWAY_TOKEN="${OPENCLAW_GATEWAY_TOKEN:-}"
  if [[ -z "$OPENCLAW_GATEWAY_TOKEN" ]]; then
    OPENCLAW_GATEWAY_TOKEN="$(node -e "
const fs=require('fs');
const c=JSON.parse(fs.readFileSync('$OPENCLAW_CONFIG','utf8'));
const t=c?.gateway?.auth?.token;
if(!t) process.exit(1);
process.stdout.write(t);
" 2>/dev/null || echo "")"
    export OPENCLAW_GATEWAY_TOKEN
  fi

  echo "==> Running OpenClaw (ATS portals focus)..."
  snapshot "$OPENCLAW_FILE"
  run_with_timeout "$TIMEOUT_SECONDS" "OpenClaw collection" openclaw agent \
    --local \
    --session-id "silicon-openclaw" \
    --timeout "$TIMEOUT_SECONDS" \
    --thinking low \
    --message "$OPENCLAW_PROMPT" || true
  restore_if_missing "$OPENCLAW_FILE"
fi

# -------------------------------------------------------
# Run Hermes (via hermes claw agent)
# -------------------------------------------------------
HERMES_BIN=""
if [[ "$SKIP_HERMES" -eq 0 ]]; then
  # Locate hermes: check PATH then known install path
  if command -v hermes >/dev/null 2>&1; then
    HERMES_BIN="hermes"
  elif [[ -x "$HOME/.hermes/hermes-agent/venv/bin/hermes" ]]; then
    HERMES_BIN="$HOME/.hermes/hermes-agent/venv/bin/hermes"
  fi

  HERMES_CMD=""
  if [[ -n "$HERMES_BIN" ]]; then
    HERMES_CMD="hermes_chat"
  elif command -v openclaw >/dev/null 2>&1; then
    HERMES_CMD="openclaw"
  else
    echo "Neither hermes nor openclaw found — skipping Hermes run" >&2
    SKIP_HERMES=1
  fi
fi

if [[ "$SKIP_HERMES" -eq 0 ]]; then
  echo "==> Running Hermes (${HERMES_CMD}, job boards focus)..."
  snapshot "$HERMES_FILE"

  case "$HERMES_CMD" in
    hermes_chat)
      set +e
      run_with_timeout "$TIMEOUT_SECONDS" "Hermes collection" "$HERMES_BIN" chat \
        -q "$HERMES_PROMPT" \
        --yolo \
        --max-turns 90 \
        -Q 2>/dev/null
      hermes_status=$?
      set -e
      if [[ "$hermes_status" -ne 0 && "$hermes_status" -ne 124 && "$hermes_status" -ne 137 ]]; then
        set +e
        run_with_timeout "$TIMEOUT_SECONDS" "Hermes collection" "$HERMES_BIN" \
          -q "$HERMES_PROMPT" \
          --yolo \
          --max-turns 90 \
          -Q 2>/dev/null
        hermes_status=$?
        set -e
      fi
      ;;
    openclaw)
      # Two openclaw sessions with different prompts: ATS portals + job boards
      run_with_timeout "$TIMEOUT_SECONDS" "Hermes fallback collection" openclaw agent \
        --local \
        --session-id "silicon-hermes" \
        --timeout "$TIMEOUT_SECONDS" \
        --thinking low \
        --message "$HERMES_PROMPT" || true
      ;;
  esac

  restore_if_missing "$HERMES_FILE"
fi

# -------------------------------------------------------
# Report what we got
# -------------------------------------------------------
echo ""
echo "==> Results:"
[[ -f "$OPENCLAW_FILE" ]] && validate_json "$OPENCLAW_FILE" "OpenClaw" || echo "  OpenClaw: no file"
[[ -f "$HERMES_FILE"   ]] && validate_json "$HERMES_FILE"   "Hermes"   || echo "  Hermes:   no file"

if [[ ! -f "$OPENCLAW_FILE" && ! -f "$HERMES_FILE" ]]; then
  echo "No listings files produced. Exiting." >&2
  exit 1
fi

# -------------------------------------------------------
# Run Silicon List with both providers
# -------------------------------------------------------
SILICON_ARGS=(
  --mode live
  --pipeline hybrid
  --provider all
  --openclaw-stage2 true
  --hardware-bias true
  --output-dir "$OUTPUT_DIR"
)

if [[ -f "$HERMES_FILE" ]]; then
  SILICON_ARGS+=(--hermes-file "$HERMES_FILE" --hermes-enabled true)
fi

[[ "$RESET_SEEN" -eq 1 ]] && SILICON_ARGS+=(--reset-seen)
[[ "$OPEN_HTML"  -eq 0 ]] && SILICON_ARGS+=(--no-open-html)

echo ""
echo "==> Running Silicon List (GitHub + OpenClaw + Hermes)..."
if command -v silicon-list >/dev/null 2>&1; then
  silicon-list "${SILICON_ARGS[@]}"
else
  "$PYTHON_BIN" -m silicon_list.main "${SILICON_ARGS[@]}"
fi
