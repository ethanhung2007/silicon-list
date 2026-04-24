#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SYSTEMD_USER_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
SERVICE_FILE="$SYSTEMD_USER_DIR/silicon-list.service"
TIMER_FILE="$SYSTEMD_USER_DIR/silicon-list.timer"

mkdir -p "$SYSTEMD_USER_DIR"

cat >"$SERVICE_FILE" <<EOF
[Unit]
Description=Silicon List daily hardware job scan

[Service]
Type=oneshot
WorkingDirectory=$PROJECT_DIR
ExecStart=$PROJECT_DIR/scripts/run_silicon_list.sh --no-open-html --no-reset-seen
Environment=SILICON_LIST_PROVIDER=all
Environment=OPENCLAW_SEARCH_DEPTH=aggressive
EOF

cat >"$TIMER_FILE" <<'EOF'
[Unit]
Description=Run Silicon List daily

[Timer]
OnCalendar=daily
Persistent=true
RandomizedDelaySec=30m

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now silicon-list.timer

echo "Installed daily Silicon List timer."
echo "Check status with: systemctl --user status silicon-list.timer"
echo "Run once with: systemctl --user start silicon-list.service"
