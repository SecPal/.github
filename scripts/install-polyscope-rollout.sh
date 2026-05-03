#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_SCRIPT="$SCRIPT_DIR/polyscope-rollout.py"
WRAPPER_SOURCE="$SCRIPT_DIR/polyscope-expose-wrapper.sh"
GIT_WRAPPER_SOURCE="$SCRIPT_DIR/polyscope-git-wrapper.sh"
WORKSPACE_ROOT="${WORKSPACE_ROOT:-$HOME/code/SecPal}"
BIN_DIR="$HOME/.local/bin"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
SYSTEMCTL_BIN="${SYSTEMCTL_BIN:-systemctl}"
POLYSCOPE_SERVER_BIN="${POLYSCOPE_SERVER_BIN:-$(command -v polyscope-server || true)}"
POLYSCOPE_REAL_GIT_BIN="${POLYSCOPE_REAL_GIT_BIN:-$(command -v git || true)}"
POLYSCOPE_API_BASE="${POLYSCOPE_API_BASE:-http://127.0.0.1:4321/api}"
POLYSCOPE_CLONE_ROOT="${POLYSCOPE_CLONE_ROOT:-$HOME/.polyscope/clones}"
POLYSCOPE_HOME="${POLYSCOPE_HOME:-$HOME/.polyscope}"
POLYSCOPE_EXPOSE_BIN="${POLYSCOPE_EXPOSE_BIN:-$POLYSCOPE_HOME/bin/expose-linux-x64}"
POLYSCOPE_EXPOSE_REAL_BIN="${POLYSCOPE_EXPOSE_REAL_BIN:-$POLYSCOPE_HOME/bin/expose-linux-x64.real}"
POLYSCOPE_GIT_BIN_DIR="${POLYSCOPE_GIT_BIN_DIR:-$HOME/.local/lib/polyscope/bin}"
POLYSCOPE_GIT_WRAPPER_BIN="${POLYSCOPE_GIT_WRAPPER_BIN:-$POLYSCOPE_GIT_BIN_DIR/git}"
POLYSCOPE_SERVER_SCOPE="${POLYSCOPE_SERVER_SCOPE:-auto}"
POLYSCOPE_SYSTEM_SERVER_UNIT="${POLYSCOPE_SYSTEM_SERVER_UNIT:-polyscope-server.service}"
POLYSCOPE_SYSTEM_SERVER_DROPIN_DIR="${POLYSCOPE_SYSTEM_SERVER_DROPIN_DIR:-/etc/systemd/system/$POLYSCOPE_SYSTEM_SERVER_UNIT.d}"
SERVICE_PATH="${POLYSCOPE_SERVICE_PATH:-}"
SUDO_BIN="${SUDO_BIN:-sudo}"

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
        --polyscope-server-scope)
            POLYSCOPE_SERVER_SCOPE="$2"
            shift 2
            ;;
        *)
            echo "Unknown argument: $1" >&2
            exit 1
            ;;
    esac
done

if [[ -z "$SERVICE_PATH" ]]; then
    SERVICE_PATH="$POLYSCOPE_GIT_BIN_DIR:$BIN_DIR:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin"
fi

INSTALL_TARGET="$BIN_DIR/polyscope-secpal-rollout.py"
EXPOSE_WRAPPER_TARGET="$BIN_DIR/polyscope-expose-wrapper.sh"
GIT_WRAPPER_TARGET="$BIN_DIR/polyscope-git-wrapper.sh"
SERVER_UNIT="$UNIT_DIR/polyscope-server.service"
SERVICE_UNIT="$UNIT_DIR/polyscope-rollout-sync.service"
PATH_UNIT="$UNIT_DIR/polyscope-rollout-sync.path"
PROVISION_SERVICE_UNIT="$UNIT_DIR/polyscope-worktree-provision.service"
PROVISION_PATH_UNIT="$UNIT_DIR/polyscope-worktree-provision.path"
ROLLOUT_READY_COMMAND="for attempt in 1 2 3 4 5 6 7 8 9 10; do curl -sf $POLYSCOPE_API_BASE/repos >/dev/null 2>&1 && exec $INSTALL_TARGET --workspace-root $WORKSPACE_ROOT --polyscope-api-base $POLYSCOPE_API_BASE; sleep 1; done; echo \"Polyscope API did not become ready in time.\" >&2; exit 1"

detect_system_server_fragment_path() {
    "$SYSTEMCTL_BIN" show -p FragmentPath --value "$POLYSCOPE_SYSTEM_SERVER_UNIT" 2>/dev/null || true
}

detect_user_server_fragment_path() {
    "$SYSTEMCTL_BIN" --user show -p FragmentPath --value "$POLYSCOPE_SYSTEM_SERVER_UNIT" 2>/dev/null || true
}

resolve_server_scope() {
    case "$POLYSCOPE_SERVER_SCOPE" in
        auto)
            local system_fragment user_fragment
            system_fragment="$(detect_system_server_fragment_path)"
            user_fragment="$(detect_user_server_fragment_path)"
            if [[ -n "$system_fragment" && "$system_fragment" != "$user_fragment" ]]; then
                printf 'system\n'
            else
                printf 'user\n'
            fi
            ;;
        user|system)
            printf '%s\n' "$POLYSCOPE_SERVER_SCOPE"
            ;;
        *)
            echo "Error: POLYSCOPE_SERVER_SCOPE must be one of: auto, user, system" >&2
            exit 1
            ;;
    esac
}

can_run_privileged_commands() {
    if [[ "$(id -u)" -eq 0 ]]; then
        return 0
    fi

    "$SUDO_BIN" -n true >/dev/null 2>&1
}

run_privileged() {
    if [[ "$(id -u)" -eq 0 ]]; then
        "$@"
        return
    fi

    "$SUDO_BIN" -n "$@"
}

if [[ -z "$POLYSCOPE_SERVER_BIN" ]]; then
    echo "Error: polyscope-server binary not found. Pass --polyscope-server-bin or ensure it is in PATH." >&2
    exit 1
fi

if [[ ! -x "$POLYSCOPE_SERVER_BIN" ]]; then
    echo "Error: polyscope-server binary is not executable: $POLYSCOPE_SERVER_BIN" >&2
    exit 1
fi

if [[ -z "$POLYSCOPE_REAL_GIT_BIN" ]]; then
    echo "Error: git binary not found. Pass POLYSCOPE_REAL_GIT_BIN or ensure git is in PATH." >&2
    exit 1
fi

if [[ ! -x "$POLYSCOPE_REAL_GIT_BIN" ]]; then
    echo "Error: git binary is not executable: $POLYSCOPE_REAL_GIT_BIN" >&2
    exit 1
fi

for _var_name in WORKSPACE_ROOT SOURCE_SCRIPT WRAPPER_SOURCE GIT_WRAPPER_SOURCE POLYSCOPE_SERVER_BIN POLYSCOPE_REAL_GIT_BIN POLYSCOPE_API_BASE POLYSCOPE_CLONE_ROOT POLYSCOPE_HOME POLYSCOPE_EXPOSE_BIN POLYSCOPE_EXPOSE_REAL_BIN POLYSCOPE_GIT_BIN_DIR POLYSCOPE_GIT_WRAPPER_BIN POLYSCOPE_SERVER_SCOPE POLYSCOPE_SYSTEM_SERVER_UNIT POLYSCOPE_SYSTEM_SERVER_DROPIN_DIR SERVICE_PATH SUDO_BIN; do
    _val="${!_var_name}"
    if [[ "$_val" == *$'\n'* ]]; then
        echo "Error: $_var_name must not contain newlines" >&2
        exit 1
    fi
    if [[ "$_val" =~ [[:space:]] ]]; then
        echo "Error: $_var_name must not contain whitespace" >&2
        exit 1
    fi
done

# Reject shell metacharacters in variables embedded in ExecStart/ExecStartPost command strings.
for _var_name in WORKSPACE_ROOT POLYSCOPE_API_BASE INSTALL_TARGET; do
    _val="${!_var_name}"
    if [[ "$_val" =~ [^a-zA-Z0-9/_.:-] ]]; then
        echo "Error: $_var_name contains characters that are unsafe in shell command strings; only letters, digits, /, _, ., :, - are permitted" >&2
        exit 1
    fi
done

server_scope="$(resolve_server_scope)"
system_server_fragment_path="$(detect_system_server_fragment_path)"

if [[ "$server_scope" == "system" ]] && [[ -z "$system_server_fragment_path" ]]; then
    echo "Error: --polyscope-server-scope system was requested but no system $POLYSCOPE_SYSTEM_SERVER_UNIT unit was found." >&2
    echo "Hint: use --polyscope-server-scope user to install the user-managed server unit instead." >&2
    exit 1
fi

if [[ "$server_scope" == "system" ]] && ! can_run_privileged_commands; then
    echo "Error: detected existing system $POLYSCOPE_SYSTEM_SERVER_UNIT at ${system_server_fragment_path:-<unknown>}, but non-interactive sudo or root access is unavailable." >&2
    echo "Refusing to create a competing user polyscope-server.service on port 4321." >&2
    exit 1
fi

mkdir -p "$BIN_DIR" "$UNIT_DIR" "$POLYSCOPE_GIT_BIN_DIR" "$(dirname -- "$POLYSCOPE_EXPOSE_BIN")" "$(dirname -- "$POLYSCOPE_EXPOSE_REAL_BIN")"
ln -sfn "$SOURCE_SCRIPT" "$INSTALL_TARGET"
ln -sfn "$WRAPPER_SOURCE" "$EXPOSE_WRAPPER_TARGET"
ln -sfn "$GIT_WRAPPER_SOURCE" "$GIT_WRAPPER_TARGET"

if [[ -e "$POLYSCOPE_EXPOSE_BIN" && ! -L "$POLYSCOPE_EXPOSE_BIN" ]]; then
    if [[ -e "$POLYSCOPE_EXPOSE_REAL_BIN" ]]; then
        if cmp -s "$POLYSCOPE_EXPOSE_BIN" "$POLYSCOPE_EXPOSE_REAL_BIN"; then
            rm -f "$POLYSCOPE_EXPOSE_BIN"
        else
            echo "Error: $POLYSCOPE_EXPOSE_REAL_BIN already exists; will not overwrite it." >&2
            echo "Remove or rename $POLYSCOPE_EXPOSE_REAL_BIN manually before re-running the installer." >&2
            exit 1
        fi
    else
        mv -f "$POLYSCOPE_EXPOSE_BIN" "$POLYSCOPE_EXPOSE_REAL_BIN"
    fi
fi

ln -sfn "$EXPOSE_WRAPPER_TARGET" "$POLYSCOPE_EXPOSE_BIN"
ln -sfn "$GIT_WRAPPER_TARGET" "$POLYSCOPE_GIT_WRAPPER_BIN"

rollout_sync_after='After=polyscope-server.service'
installed_server_target="$SERVER_UNIT"

if [[ "$server_scope" == "user" ]]; then
cat >"$SERVER_UNIT" <<EOF
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
[Unit]
Description=Polyscope local API server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
Environment=PATH=$SERVICE_PATH
Environment=SSH_AUTH_SOCK=%t/openssh_agent
Environment=POLYSCOPE_REAL_GIT_BIN=$POLYSCOPE_REAL_GIT_BIN
ExecStart=$POLYSCOPE_SERVER_BIN serve --host 127.0.0.1 --port 4321
ExecStartPost=/usr/bin/env bash -lc '$ROLLOUT_READY_COMMAND'
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=default.target
EOF
else
    rm -f "$SERVER_UNIT"
    rollout_sync_after='After=network-online.target'
    installed_server_target="$POLYSCOPE_SYSTEM_SERVER_DROPIN_DIR/zz-secpal-runtime.conf"

    system_dropin_tmp="$(mktemp)"
    cat >"$system_dropin_tmp" <<EOF
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
[Service]
ExecStart=
ExecStart=$POLYSCOPE_SERVER_BIN serve --host 127.0.0.1 --port 4321
ExecStartPost=
ExecStartPost=/usr/bin/env bash -lc '$ROLLOUT_READY_COMMAND'
Environment=PATH=$SERVICE_PATH
Environment=SSH_AUTH_SOCK=/run/user/%U/openssh_agent
Environment=POLYSCOPE_REAL_GIT_BIN=$POLYSCOPE_REAL_GIT_BIN
EOF

    run_privileged install -d -m 0755 "$POLYSCOPE_SYSTEM_SERVER_DROPIN_DIR"
    run_privileged install -m 0644 "$system_dropin_tmp" "$installed_server_target"
    rm -f "$system_dropin_tmp"
fi

cat >"$SERVICE_UNIT" <<EOF
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
[Unit]
Description=Sync Polyscope prompts and preview config for SecPal
$rollout_sync_after

[Service]
Type=oneshot
WorkingDirectory=$WORKSPACE_ROOT/.github
Environment=PATH=$SERVICE_PATH
Environment=SSH_AUTH_SOCK=%t/openssh_agent
Environment=POLYSCOPE_REAL_GIT_BIN=$POLYSCOPE_REAL_GIT_BIN
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
Environment=PATH=$SERVICE_PATH
Environment=SSH_AUTH_SOCK=%t/openssh_agent
Environment=POLYSCOPE_REAL_GIT_BIN=$POLYSCOPE_REAL_GIT_BIN
ExecStart=$INSTALL_TARGET --workspace-root $WORKSPACE_ROOT --polyscope-api-base $POLYSCOPE_API_BASE --clone-root $POLYSCOPE_CLONE_ROOT --skip-local-configs --skip-db-sync --provision-worktrees
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

if [[ "$server_scope" == "user" ]]; then
    "$SYSTEMCTL_BIN" --user enable --now polyscope-server.service
    "$SYSTEMCTL_BIN" --user restart polyscope-server.service
else
    run_privileged "$SYSTEMCTL_BIN" daemon-reload
    run_privileged "$SYSTEMCTL_BIN" enable --now "$POLYSCOPE_SYSTEM_SERVER_UNIT"
    run_privileged "$SYSTEMCTL_BIN" restart "$POLYSCOPE_SYSTEM_SERVER_UNIT"
    "$SYSTEMCTL_BIN" --user disable --now polyscope-server.service >/dev/null 2>&1 || true
fi

"$SYSTEMCTL_BIN" --user enable --now polyscope-rollout-sync.path
"$SYSTEMCTL_BIN" --user enable --now polyscope-worktree-provision.path
"$SYSTEMCTL_BIN" --user start polyscope-rollout-sync.service
"$SYSTEMCTL_BIN" --user start polyscope-worktree-provision.service

echo "Installed $INSTALL_TARGET"
echo "Installed $EXPOSE_WRAPPER_TARGET"
echo "Installed $GIT_WRAPPER_TARGET"
echo "Installed expose wrapper at $POLYSCOPE_EXPOSE_BIN"
echo "Installed git wrapper at $POLYSCOPE_GIT_WRAPPER_BIN"
echo "Installed $installed_server_target"
echo "Installed $SERVICE_UNIT"
echo "Installed $PATH_UNIT"
echo "Installed $PROVISION_SERVICE_UNIT"
echo "Installed $PROVISION_PATH_UNIT"
