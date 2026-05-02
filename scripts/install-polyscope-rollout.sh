#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_SCRIPT="$SCRIPT_DIR/polyscope-rollout.py"
WORKSPACE_ROOT="${WORKSPACE_ROOT:-$HOME/code/SecPal}"
BIN_DIR="$HOME/.local/bin"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
SYSTEMCTL_BIN="${SYSTEMCTL_BIN:-systemctl}"
POLYSCOPE_SERVER_BIN="${POLYSCOPE_SERVER_BIN:-$(command -v polyscope-server || true)}"
POLYSCOPE_API_BASE="${POLYSCOPE_API_BASE:-http://127.0.0.1:4321/api}"
POLYSCOPE_CLONE_ROOT="${POLYSCOPE_CLONE_ROOT:-$HOME/.polyscope/clones}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --workspace-root)
            WORKSPACE_ROOT="$2"
            shift 2
            ;;
        --source-script)
            SOURCE_SCRIPT="$2"
            shift 2
            ;;
        --bin-dir)
            BIN_DIR="$2"
            shift 2
            ;;
        --unit-dir)
            UNIT_DIR="$2"
            shift 2
            ;;
        --polyscope-server-bin)
            POLYSCOPE_SERVER_BIN="$2"
            shift 2
            ;;
        *)
            echo "Unknown argument: $1" >&2
            exit 1
            ;;
    esac
done

INSTALL_TARGET="$BIN_DIR/polyscope-secpal-rollout.py"
SERVER_UNIT="$UNIT_DIR/polyscope-server.service"
SERVICE_UNIT="$UNIT_DIR/polyscope-rollout-sync.service"
PATH_UNIT="$UNIT_DIR/polyscope-rollout-sync.path"
PROVISION_SERVICE_UNIT="$UNIT_DIR/polyscope-worktree-provision.service"
PROVISION_PATH_UNIT="$UNIT_DIR/polyscope-worktree-provision.path"
ROLLOUT_READY_COMMAND="for attempt in 1 2 3 4 5 6 7 8 9 10; do curl -sf $POLYSCOPE_API_BASE/repos >/dev/null 2>&1 && exec $INSTALL_TARGET --workspace-root $WORKSPACE_ROOT --polyscope-api-base $POLYSCOPE_API_BASE; sleep 1; done; echo \"Polyscope API did not become ready in time.\" >&2; exit 1"

if [[ -z "$POLYSCOPE_SERVER_BIN" ]]; then
    echo "Error: polyscope-server binary not found. Pass --polyscope-server-bin or ensure it is in PATH." >&2
    exit 1
fi

if [[ ! -x "$POLYSCOPE_SERVER_BIN" ]]; then
    echo "Error: polyscope-server binary is not executable: $POLYSCOPE_SERVER_BIN" >&2
    exit 1
fi

for _var_name in WORKSPACE_ROOT SOURCE_SCRIPT POLYSCOPE_SERVER_BIN POLYSCOPE_API_BASE POLYSCOPE_CLONE_ROOT; do
    _val="${!_var_name}"
    if [[ "$_val" == *$'\n'* ]]; then
        echo "Error: $_var_name must not contain newlines" >&2
        exit 1
    fi
done

mkdir -p "$BIN_DIR" "$UNIT_DIR"
ln -sfn "$SOURCE_SCRIPT" "$INSTALL_TARGET"

cat >"$SERVER_UNIT" <<EOF
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
[Unit]
Description=Polyscope local API server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=$POLYSCOPE_SERVER_BIN serve --host 127.0.0.1 --port 4321
ExecStartPost=/usr/bin/env bash -lc '$ROLLOUT_READY_COMMAND'
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=default.target
EOF

cat >"$SERVICE_UNIT" <<EOF
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
[Unit]
Description=Sync Polyscope prompts and preview config for SecPal
After=polyscope-server.service

[Service]
Type=oneshot
WorkingDirectory=$WORKSPACE_ROOT/.github
ExecStart=$INSTALL_TARGET --workspace-root $WORKSPACE_ROOT --polyscope-api-base $POLYSCOPE_API_BASE
EOF

cat >"$PATH_UNIT" <<EOF
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
[Unit]
Description=Watch SecPal instruction files for Polyscope sync

[Path]
PathChanged=$WORKSPACE_ROOT/api/.github/copilot-instructions.md
PathChanged=$WORKSPACE_ROOT/api/.github/instructions
PathChanged=$WORKSPACE_ROOT/frontend/.github/copilot-instructions.md
PathChanged=$WORKSPACE_ROOT/frontend/.github/instructions
PathChanged=$WORKSPACE_ROOT/contracts/.github/copilot-instructions.md
PathChanged=$WORKSPACE_ROOT/contracts/.github/instructions
PathChanged=$WORKSPACE_ROOT/android/.github/copilot-instructions.md
PathChanged=$WORKSPACE_ROOT/android/.github/instructions
PathChanged=$WORKSPACE_ROOT/secpal.app/.github/copilot-instructions.md
PathChanged=$WORKSPACE_ROOT/secpal.app/.github/instructions
PathChanged=$WORKSPACE_ROOT/changelog/.github/copilot-instructions.md
PathChanged=$WORKSPACE_ROOT/changelog/.github/instructions
PathChanged=$WORKSPACE_ROOT/.github/.github/copilot-instructions.md
PathChanged=$WORKSPACE_ROOT/.github/.github/instructions
PathChanged=$SOURCE_SCRIPT

[Install]
WantedBy=default.target
EOF

cat >"$PROVISION_SERVICE_UNIT" <<EOF
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
[Unit]
Description=Provision SecPal Polyscope worktrees automatically
After=polyscope-rollout-sync.service

[Service]
Type=oneshot
WorkingDirectory=$WORKSPACE_ROOT/.github
ExecStart=$INSTALL_TARGET --workspace-root $WORKSPACE_ROOT --polyscope-api-base $POLYSCOPE_API_BASE --clone-root $POLYSCOPE_CLONE_ROOT --provision-worktrees
EOF

cat >"$PROVISION_PATH_UNIT" <<EOF
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
[Unit]
Description=Watch SecPal Polyscope worktree metadata and generated local config for automatic provisioning

[Path]
PathChanged=$HOME/.polyscope/polyscope.db
PathChanged=$WORKSPACE_ROOT/api/polyscope.local.json
PathChanged=$WORKSPACE_ROOT/frontend/polyscope.local.json
PathChanged=$WORKSPACE_ROOT/contracts/polyscope.local.json
PathChanged=$WORKSPACE_ROOT/android/polyscope.local.json
PathChanged=$WORKSPACE_ROOT/secpal.app/polyscope.local.json
PathChanged=$WORKSPACE_ROOT/changelog/polyscope.local.json
PathChanged=$WORKSPACE_ROOT/.github/polyscope.local.json

[Install]
WantedBy=default.target
EOF

"$SYSTEMCTL_BIN" --user daemon-reload
"$SYSTEMCTL_BIN" --user enable --now polyscope-server.service
"$SYSTEMCTL_BIN" --user enable --now polyscope-rollout-sync.path
"$SYSTEMCTL_BIN" --user enable --now polyscope-worktree-provision.path
"$SYSTEMCTL_BIN" --user start polyscope-rollout-sync.service
"$SYSTEMCTL_BIN" --user start polyscope-worktree-provision.service

echo "Installed $INSTALL_TARGET"
echo "Installed $SERVER_UNIT"
echo "Installed $SERVICE_UNIT"
echo "Installed $PATH_UNIT"
echo "Installed $PROVISION_SERVICE_UNIT"
echo "Installed $PROVISION_PATH_UNIT"
