#!/usr/bin/env bash
# Runs Hermes (via `hermes claw agent`) to collect job listings, then runs Silicon List.
# Hermes is Claude-Code / a Claude-based CLI whose claw subcommand wraps OpenClaw.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXPORT_FILE="${HERMES_EXPORT_FILE:-$HOME/.silicon-list/hermes-listings.json}"
OUTPUT_DIR="${SILICON_LIST_OUTPUT_DIR:-$HOME/.silicon-list}"
SILICON_PROVIDER="${SILICON_LIST_PROVIDER:-all}"
TIMEOUT_SECONDS="${HERMES_TIMEOUT_SECONDS:-900}"
MAX_LISTINGS="${HERMES_MAX_LISTINGS:-100}"
HERMES_MODEL="${HERMES_MODEL:-}"
OPENCLAW_CONFIG="${OPENCLAW_CONFIG:-$HOME/.openclaw/openclaw.json}"
OPENCLAW_SESSION_ID="${OPENCLAW_SESSION_ID:-silicon-list}"
PROMPT_FILE="${HERMES_PROMPT_FILE:-$PROJECT_DIR/prompts/hermes_hardware_jobs.txt}"

usage() {
  cat <<EOF
Usage: $(basename "$0") [--skip-hermes] [--no-reset-seen] [--no-open-html]

Runs Hermes (via hermes claw agent) to gather listings into:
  $EXPORT_FILE

Then runs Silicon List with both Hermes and OpenClaw results.

Environment overrides:
  HERMES_EXPORT_FILE      Output JSON path (default: ~/.silicon-list/hermes-listings.json)
  SILICON_LIST_OUTPUT_DIR Output directory (default: ~/.silicon-list)
  HERMES_TIMEOUT_SECONDS  Agent timeout (default: 900)
  HERMES_MAX_LISTINGS     Max listings to collect (default: 100)
  HERMES_MODEL            Override model for hermes
  OPENCLAW_CONFIG         OpenClaw config path
  OPENCLAW_SESSION_ID     OpenClaw session ID
EOF
}

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
    --skip-hermes)   SKIP_HERMES=1; shift ;;
    --no-reset-seen) RESET_SEEN=0; shift ;;
    --no-open-html)  OPEN_HTML=0; shift ;;
    -h|--help)       usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
else
  echo "Missing required command: python or python3" >&2; exit 1
fi

mkdir -p "$OUTPUT_DIR"
cd "$PROJECT_DIR"
if [[ -f "$PROJECT_DIR/venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$PROJECT_DIR/venv/bin/activate"
fi

# --- Detect which hermes-compatible command to use ---
# hermes is a local AI agent CLI (different from openclaw).
# Use `hermes chat -q "..."` for non-interactive one-shot runs.
HERMES_BIN=""
detect_hermes_cmd() {
  # Check standard PATH first, then the known install location
  if command -v hermes >/dev/null 2>&1; then
    HERMES_BIN="hermes"
  elif [[ -x "$HOME/.hermes/hermes-agent/venv/bin/hermes" ]]; then
    HERMES_BIN="$HOME/.hermes/hermes-agent/venv/bin/hermes"
  fi

  if [[ -n "$HERMES_BIN" ]]; then
    # hermes chat -q supports non-interactive one-shot mode
    if "$HERMES_BIN" chat --help 2>&1 | grep -q "\-\-query\|-q "; then
      echo "hermes_chat"
    elif command -v openclaw >/dev/null 2>&1; then
      echo "openclaw"
    else
      echo "hermes_chat"  # try anyway
    fi
  elif command -v openclaw >/dev/null 2>&1; then
    echo "openclaw"
  else
    echo "none"
  fi
}

validate_export() {
  local file="$1"
  "$PYTHON_BIN" - "$file" <<'PY'
import json, sys
from pathlib import Path
path = Path(sys.argv[1]).expanduser()
if not path.exists():
    raise SystemExit(f"Export was not created: {path}")
with path.open() as f:
    try:
        data = json.load(f)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Export is invalid JSON at {path}: {exc}")
rows = data.get("listings", data) if isinstance(data, dict) else data
if not isinstance(rows, list):
    raise SystemExit("Export must be a JSON list or object with a listings list.")
print(f"Validated export: {len(rows)} listings at {path}")
PY
}

snapshot_export() {
  local file="$1"
  [[ -f "$file" ]] && cp "$file" "$file.bak"
}

restore_export_if_missing() {
  local file="$1"
  if [[ ! -f "$file" && -f "$file.bak" ]]; then
    echo "Agent did not create a new export; restoring backup from $file.bak" >&2
    cp "$file.bak" "$file"
  fi
}

run_openclaw_agent() {
  local export_file="$1"
  local session_id="$2"
  local prompt="$3"
  local cmd="$4"   # "hermes_chat" or "openclaw"

  snapshot_export "$export_file"
  echo "Running agent (${cmd}) for Hermes export..."

  if [[ "$cmd" == "hermes_chat" ]]; then
    local hermes_status
    set +e
    run_with_timeout "$TIMEOUT_SECONDS" "Hermes collection" "$HERMES_BIN" chat \
      -q "$prompt" \
      --yolo \
      --max-turns 90 \
      -Q 2>/dev/null
    hermes_status=$?
    set -e
    if [[ "$hermes_status" -ne 0 && "$hermes_status" -ne 124 && "$hermes_status" -ne 137 ]]; then
      set +e
      run_with_timeout "$TIMEOUT_SECONDS" "Hermes collection" "$HERMES_BIN" \
        -q "$prompt" \
        --yolo \
        --max-turns 90 \
        -Q 2>/dev/null
      hermes_status=$?
      set -e
    fi
  else
    run_with_timeout "$TIMEOUT_SECONDS" "Hermes fallback collection" openclaw agent \
      --local \
      --session-id "$session_id" \
      --timeout "$TIMEOUT_SECONDS" \
      --thinking low \
      --message "$prompt" || true
  fi

  restore_export_if_missing "$export_file"
}

# -------------------------------------------------------
if [[ "$SKIP_HERMES" -eq 0 ]]; then
  CMD="$(detect_hermes_cmd)"
  if [[ "$CMD" == "none" ]]; then
    echo "No hermes or openclaw command found. Run with --skip-hermes if you already have $EXPORT_FILE" >&2
    exit 1
  fi

  if [[ ! -f "$PROMPT_FILE" ]]; then
    echo "Prompt file not found: $PROMPT_FILE" >&2
    exit 1
  fi

  PROMPT="$(cat "$PROMPT_FILE")"
  PROMPT="${PROMPT//\~\/.silicon-list\/hermes-listings.json/$EXPORT_FILE}"
  PROMPT="${PROMPT//50–150 validated listings/${MAX_LISTINGS} validated listings}"

  if [[ -n "$HERMES_MODEL" ]]; then
    if [[ "$CMD" == "hermes_claw" ]]; then
      hermes model set "$HERMES_MODEL" 2>/dev/null || true
    else
      openclaw models set "$HERMES_MODEL" 2>/dev/null || true
    fi
  fi

  run_openclaw_agent "$EXPORT_FILE" "silicon-hermes" "$PROMPT" "$CMD"
fi

validate_export "$EXPORT_FILE"

SILICON_ARGS=(
  --mode live
  --pipeline hybrid
  --provider "$SILICON_PROVIDER"
  --hermes-file "$EXPORT_FILE"
  --hermes-enabled true
  --openclaw-stage2 false
  --hardware-bias true
  --output-dir "$OUTPUT_DIR"
)

[[ "$RESET_SEEN" -eq 1 ]] && SILICON_ARGS+=(--reset-seen)
[[ "$OPEN_HTML"  -eq 0 ]] && SILICON_ARGS+=(--no-open-html)

echo "Running Silicon List..."
if command -v silicon-list >/dev/null 2>&1; then
  silicon-list "${SILICON_ARGS[@]}"
else
  "$PYTHON_BIN" -m silicon_list.main "${SILICON_ARGS[@]}"
fi
