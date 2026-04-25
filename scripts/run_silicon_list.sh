#!/usr/bin/env bash
# Silicon List runner.
# Runs GitHub/SearXNG/Google providers (Stage 1) then invokes a Claude Cowork
# session (Stage 2) to do deep browser research, and writes a single HTML report.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_DIR="${SILICON_LIST_OUTPUT_DIR:-$HOME/.silicon-list}"
COWORK_FILE="${COWORK_EXPORT_FILE:-$OUTPUT_DIR/openclaw-listings.json}"
SILICON_MODE="${SILICON_LIST_MODE:-live}"
SILICON_PROVIDER="${SILICON_LIST_PROVIDER:-all}"

RESET_SEEN=1
OPEN_HTML=1
SKIP_COWORK=0
VALIDATE_LINKS="${SILICON_LIST_VALIDATE_LINKS:-1}"

usage() {
  cat <<EOF
Usage: $(basename "$0") [options]

Runs one end-to-end Silicon List pass:
  1. GitHub / SearXNG / Google providers (Stage 1)
  2. Claude Cowork browser research      (Stage 2) -> $COWORK_FILE
  3. Silicon List pipeline               -> $OUTPUT_DIR/results.html

Options:
  --skip-cowork       Skip the Claude research session; use existing export if present
  --no-reset-seen     Keep seen.json so only new listings are shown
  --no-open-html      Write results.html but do not open it
  --validate-links    Run HTTP validation before reporting (default)
  --no-validate-links Skip HTTP validation; faster but may include stale links
  -h, --help

Useful environment overrides:
  SILICON_LIST_OUTPUT_DIR
  COWORK_EXPORT_FILE
  SILICON_LIST_MODE
  SILICON_LIST_PROVIDER
  GOOGLE_API_KEY / GOOGLE_CSE_ID
  SEARXNG_URL
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-cowork) SKIP_COWORK=1; shift ;;
    --no-reset-seen) RESET_SEEN=0; shift ;;
    --no-open-html) OPEN_HTML=0; shift ;;
    --validate-links) VALIDATE_LINKS=1; shift ;;
    --no-validate-links) VALIDATE_LINKS=0; shift ;;
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

SILICON_ARGS=(
  --mode "$SILICON_MODE"
  --pipeline hybrid
  --provider "$SILICON_PROVIDER"
  --cowork-file "$COWORK_FILE"
  --cowork-stage2 true
  --hardware-bias true
  --output-dir "$OUTPUT_DIR"
)

if [[ "$SKIP_COWORK" -eq 1 ]]; then
  SILICON_ARGS+=(--skip-cowork-run)
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

cowork_count="$(json_count "$COWORK_FILE")"
echo "Cowork export: ${cowork_count:-0} listings written to $COWORK_FILE"
