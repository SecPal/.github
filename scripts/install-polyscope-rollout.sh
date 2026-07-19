#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_SCRIPT="$SCRIPT_DIR/polyscope-rollout.py"
REAPER_SOURCE="$SCRIPT_DIR/reap-polyscope-clones.py"
WRAPPER_SOURCE="$SCRIPT_DIR/polyscope-expose-wrapper.sh"
GIT_WRAPPER_SOURCE="$SCRIPT_DIR/polyscope-git-wrapper.sh"
NGINX_LIBRARY_SOURCE="$SCRIPT_DIR/polyscope_nginx.py"
NGINX_HELPER_SOURCE="$SCRIPT_DIR/secpal-polyscope-nginx-apply.py"
CODEX_AGENTS_SOURCE="$(cd -- "$SCRIPT_DIR/../templates" && pwd)/polyscope-codex-AGENTS.md"
WORKSPACE_ROOT="${WORKSPACE_ROOT:-$HOME/code/SecPal}"
BIN_DIR="$HOME/.local/bin"
CODEX_HOME_DIR="${CODEX_HOME:-$HOME/.codex}"
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
FIXED_POLYSCOPE_NGINX_HELPER="/usr/local/libexec/secpal-polyscope-nginx-apply"
POLYSCOPE_NGINX_HELPER_CHECK="${POLYSCOPE_NGINX_HELPER:-$FIXED_POLYSCOPE_NGINX_HELPER}"
FIXED_POLYSCOPE_NGINX_MANIFEST="/home/secpal/.local/state/polyscope/nginx-manifest.json"
if [[ "${POLYSCOPE_NGINX_MANIFEST:-$FIXED_POLYSCOPE_NGINX_MANIFEST}" != "$FIXED_POLYSCOPE_NGINX_MANIFEST" ]]; then
    echo "Error: the nginx manifest path is fixed at $FIXED_POLYSCOPE_NGINX_MANIFEST." >&2
    exit 1
fi
POLYSCOPE_NGINX_MANIFEST="$FIXED_POLYSCOPE_NGINX_MANIFEST"
if [[ "$POLYSCOPE_NGINX_HELPER_CHECK" != "$FIXED_POLYSCOPE_NGINX_HELPER" \
    && "${POLYSCOPE_TEST_ALLOW_NGINX_HELPER_OVERRIDE:-0}" != "1" ]]; then
    echo "Error: the nginx helper path is fixed at $FIXED_POLYSCOPE_NGINX_HELPER." >&2
    exit 1
fi
POLYSCOPE_NGINX_HELPER="$FIXED_POLYSCOPE_NGINX_HELPER"

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

if ! secpal_uid="$(id -u secpal 2>/dev/null)"; then
    echo "Error: required service user 'secpal' does not exist." >&2
    exit 1
fi
if [[ "$(id -u)" != "$secpal_uid" ]]; then
    echo "Error: this installer must be run as the secpal user." >&2
    exit 1
fi

if [[ -z "$SERVICE_PATH" ]]; then
    SERVICE_PATH="$POLYSCOPE_GIT_BIN_DIR:$BIN_DIR:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin"
fi

INSTALL_TARGET="$BIN_DIR/polyscope-secpal-rollout.py"
REAPER_TARGET="$BIN_DIR/reap-polyscope-clones.py"
EXPOSE_WRAPPER_TARGET="$BIN_DIR/polyscope-expose-wrapper.sh"
GIT_WRAPPER_TARGET="$BIN_DIR/polyscope-git-wrapper.sh"
CODEX_AGENTS_TARGET="$CODEX_HOME_DIR/AGENTS.md"
CODEX_AGENTS_OVERRIDE="$CODEX_HOME_DIR/AGENTS.override.md"
SERVER_UNIT="$UNIT_DIR/polyscope-server.service"
SERVICE_UNIT="$UNIT_DIR/polyscope-rollout-sync.service"
PATH_UNIT="$UNIT_DIR/polyscope-rollout-sync.path"
PROVISION_SERVICE_UNIT="$UNIT_DIR/polyscope-worktree-provision.service"
PROVISION_PATH_UNIT="$UNIT_DIR/polyscope-worktree-provision.path"
PROVISION_TIMER_UNIT="$UNIT_DIR/polyscope-worktree-provision.timer"
REAPER_SERVICE_UNIT="$UNIT_DIR/polyscope-clone-reaper.service"
REAPER_TIMER_UNIT="$UNIT_DIR/polyscope-clone-reaper.timer"
ROLLOUT_READY_COMMAND="for attempt in 1 2 3 4 5 6 7 8 9 10; do curl -sf $POLYSCOPE_API_BASE/repos >/dev/null 2>&1 && exec $INSTALL_TARGET --workspace-root $WORKSPACE_ROOT --polyscope-api-base $POLYSCOPE_API_BASE; sleep 1; done; echo \"Polyscope API did not become ready in time.\" >&2; exit 1"

detect_system_server_fragment_path() {
    "$SYSTEMCTL_BIN" show -p FragmentPath --value "$POLYSCOPE_SYSTEM_SERVER_UNIT" 2>/dev/null || true
}

detect_system_server_user() {
    "$SYSTEMCTL_BIN" show -p User --value "$POLYSCOPE_SYSTEM_SERVER_UNIT" 2>/dev/null || true
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

can_apply_nginx_non_interactively() {
    [[ -x "$POLYSCOPE_NGINX_HELPER_CHECK" ]] || return 1
    "$SUDO_BIN" -k -n "$POLYSCOPE_NGINX_HELPER_CHECK" --check >/dev/null 2>&1
}

is_managed_codex_agents_link() {
    local link_target

    [[ -L "$CODEX_AGENTS_TARGET" ]] || return 1
    link_target="$(readlink "$CODEX_AGENTS_TARGET")" || return 1
    [[ "$link_target" == "$CODEX_AGENTS_SOURCE" || "$link_target" == /*/templates/polyscope-codex-AGENTS.md ]]
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

for _var_name in WORKSPACE_ROOT SOURCE_SCRIPT WRAPPER_SOURCE GIT_WRAPPER_SOURCE NGINX_LIBRARY_SOURCE NGINX_HELPER_SOURCE CODEX_AGENTS_SOURCE CODEX_HOME_DIR POLYSCOPE_SERVER_BIN POLYSCOPE_REAL_GIT_BIN POLYSCOPE_API_BASE POLYSCOPE_CLONE_ROOT POLYSCOPE_HOME POLYSCOPE_EXPOSE_BIN POLYSCOPE_EXPOSE_REAL_BIN POLYSCOPE_GIT_BIN_DIR POLYSCOPE_GIT_WRAPPER_BIN POLYSCOPE_SERVER_SCOPE POLYSCOPE_SYSTEM_SERVER_UNIT POLYSCOPE_SYSTEM_SERVER_DROPIN_DIR SERVICE_PATH SUDO_BIN POLYSCOPE_NGINX_HELPER POLYSCOPE_NGINX_HELPER_CHECK POLYSCOPE_NGINX_MANIFEST; do
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

if [[ ! -x "$SOURCE_SCRIPT" ]]; then
    echo "Error: rollout source script is missing or not executable: $SOURCE_SCRIPT" >&2
    exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "Error: python3 is required to resolve the rollout source bundle." >&2
    exit 1
fi

SOURCE_SCRIPT="$(python3 -c 'import pathlib, sys; print(pathlib.Path(sys.argv[1]).resolve(strict=True))' "$SOURCE_SCRIPT")"
if [[ "$SOURCE_SCRIPT" =~ [[:space:]] ]]; then
    echo "Error: resolved rollout source script path must not contain whitespace: $SOURCE_SCRIPT" >&2
    exit 1
fi

VALIDATOR_SOURCE="$(dirname -- "$SOURCE_SCRIPT")/validate-ai-instructions.sh"
if [[ ! -x "$VALIDATOR_SOURCE" ]]; then
    echo "Error: canonical instruction validator is missing or not executable next to the rollout source: $VALIDATOR_SOURCE" >&2
    exit 1
fi
NGINX_LIBRARY_SOURCE="$(dirname -- "$SOURCE_SCRIPT")/polyscope_nginx.py"
NGINX_HELPER_SOURCE="$(dirname -- "$SOURCE_SCRIPT")/secpal-polyscope-nginx-apply.py"
if [[ ! -f "$NGINX_LIBRARY_SOURCE" || ! -x "$NGINX_HELPER_SOURCE" ]]; then
    echo "Error: constrained nginx source bundle is incomplete next to the rollout: $(dirname -- "$SOURCE_SCRIPT")" >&2
    exit 1
fi

VALIDATOR_TOOLCHAIN_ROOT="$(cd -- "$(dirname -- "$SOURCE_SCRIPT")/.." && pwd)"
VALIDATOR_PACKAGE_LOCK="$VALIDATOR_TOOLCHAIN_ROOT/package-lock.json"
VALIDATOR_INSTALLED_PACKAGE_LOCK="$VALIDATOR_TOOLCHAIN_ROOT/node_modules/.package-lock.json"
VALIDATOR_MARKDOWNLINT="$VALIDATOR_TOOLCHAIN_ROOT/node_modules/.bin/markdownlint"
VALIDATOR_YAML_MODULE="$VALIDATOR_TOOLCHAIN_ROOT/node_modules/js-yaml/index.js"

for _validator_tool in bash basename dirname find grep head node python3 wc; do
    if ! PATH="$SERVICE_PATH" command -v "$_validator_tool" >/dev/null 2>&1; then
        echo "Error: rollout validator toolchain is incomplete: $_validator_tool is unavailable in the service PATH." >&2
        exit 1
    fi
done

if [[ ! -f "$VALIDATOR_PACKAGE_LOCK" \
    || ! -f "$VALIDATOR_INSTALLED_PACKAGE_LOCK" \
    || ! -x "$VALIDATOR_MARKDOWNLINT" \
    || ! -f "$VALIDATOR_YAML_MODULE" ]]; then
    echo "Error: rollout validator toolchain is incomplete; install the source bundle's committed npm dependencies before installing the rollout." >&2
    exit 1
fi

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

if ! can_apply_nginx_non_interactively; then
    echo "Error: the exact constrained nginx helper capability is unavailable." >&2
    echo "Expected: sudo -k -n $POLYSCOPE_NGINX_HELPER_CHECK --check" >&2
    echo "Run scripts/install-polyscope-system-components.sh interactively as root, then retry." >&2
    exit 1
fi

if [[ ! -f "$CODEX_AGENTS_SOURCE" ]]; then
    echo "Error: Polyscope Codex instructions not found: $CODEX_AGENTS_SOURCE" >&2
    exit 1
fi

if [[ -f "$CODEX_AGENTS_OVERRIDE" && -s "$CODEX_AGENTS_OVERRIDE" ]]; then
    echo "Error: AGENTS.override.md takes precedence over the managed AGENTS.md: $CODEX_AGENTS_OVERRIDE" >&2
    echo "Merge the Polyscope guidance into the override, or remove or empty the override before re-running the installer." >&2
    exit 1
fi

if [[ ( -e "$CODEX_AGENTS_TARGET" || -L "$CODEX_AGENTS_TARGET" ) ]] && ! is_managed_codex_agents_link; then
    echo "Error: refusing to overwrite existing Codex instructions: $CODEX_AGENTS_TARGET" >&2
    exit 1
fi

rollout_sync_after='After=polyscope-server.service'
installed_server_target="$SERVER_UNIT"
if [[ "$server_scope" == "system" ]]; then
    rollout_sync_after='After=network-online.target'
    installed_server_target="$POLYSCOPE_SYSTEM_SERVER_DROPIN_DIR/zz-secpal-runtime.conf"
    if [[ ! -f "$installed_server_target" ]]; then
        echo "Error: reviewed system server drop-in is not installed: $installed_server_target" >&2
        echo "Run scripts/install-polyscope-system-components.sh interactively as root first." >&2
        exit 1
    fi
    if [[ "$(detect_system_server_user)" != "secpal" ]]; then
        echo "Error: the system Polyscope server must run as secpal before user units are installed." >&2
        exit 1
    fi
    if ! system_server_uid="$(id -u secpal 2>/dev/null)"; then
        echo "Error: required system Polyscope service user 'secpal' does not exist." >&2
        exit 1
    fi
    mapfile -t _installed_path_lines < <(sed -n 's/^Environment=PATH=//p' "$installed_server_target")
    if [[ "${#_installed_path_lines[@]}" -ne 1 ]]; then
        echo "Error: reviewed system server drop-in is incomplete; expected exactly one service PATH: $installed_server_target" >&2
        exit 1
    fi
    _installed_service_path="${_installed_path_lines[0]}"
    if [[ -z "$_installed_service_path" \
        || "$_installed_service_path" == *: \
        || "$_installed_service_path" =~ [[:space:]] ]]; then
        echo "Error: reviewed system server drop-in contains an invalid service PATH: $installed_server_target" >&2
        exit 1
    fi
    IFS=: read -r -a _installed_path_entries <<<"$_installed_service_path"
    for _installed_path_entry in "${_installed_path_entries[@]}"; do
        if [[ -z "$_installed_path_entry" || "$_installed_path_entry" != /* ]]; then
            echo "Error: reviewed system server drop-in PATH entries must be absolute and non-empty: $installed_server_target" >&2
            exit 1
        fi
    done
    for _required_path_entry in \
        /home/secpal/.local/lib/polyscope/bin \
        /home/secpal/.local/bin \
        /usr/local/sbin \
        /usr/local/bin \
        /usr/sbin \
        /usr/bin; do
        if [[ ":$_installed_service_path:" != *":$_required_path_entry:"* ]]; then
            echo "Error: reviewed system server drop-in PATH is incomplete: $installed_server_target" >&2
            echo "Missing PATH entry: $_required_path_entry" >&2
            exit 1
        fi
    done
    _installed_node_bin="$(PATH="$_installed_service_path" command -v node || true)"
    if [[ -z "$_installed_node_bin" || "$_installed_node_bin" != /* || ! -x "$_installed_node_bin" ]]; then
        echo "Error: reviewed system server drop-in PATH cannot resolve Node.js: $installed_server_target" >&2
        exit 1
    fi
    for _required_dropin_line in \
        "User=secpal" \
        "ExecStart=/home/secpal/.local/bin/polyscope-server serve --host 127.0.0.1 --port 4321" \
        "Environment=SSH_AUTH_SOCK=/run/user/$system_server_uid/openssh_agent" \
        "Environment=POLYSCOPE_REAL_GIT_BIN=/usr/bin/git"; do
        if ! grep -qxF "$_required_dropin_line" "$installed_server_target"; then
            echo "Error: reviewed system server drop-in is incomplete: $installed_server_target" >&2
            echo "Missing: $_required_dropin_line" >&2
            exit 1
        fi
    done
    if ! grep -qF -- '--nginx-manifest-output /home/secpal/.local/state/polyscope/nginx-manifest.json --install-nginx' "$installed_server_target"; then
        echo "Error: reviewed system server drop-in lacks constrained nginx activation: $installed_server_target" >&2
        exit 1
    fi
    if ! grep -qF -- 'exec /home/secpal/code/SecPal/.github/scripts/polyscope-rollout.py --workspace-root /home/secpal/code/SecPal' "$installed_server_target"; then
        echo "Error: reviewed system server drop-in lacks the canonical rollout runtime: $installed_server_target" >&2
        exit 1
    fi
    if grep -qF -- 'exec /home/secpal/.local/bin/polyscope-secpal-rollout.py ' "$installed_server_target"; then
        echo "Error: reviewed system server drop-in depends on a user installer target: $installed_server_target" >&2
        exit 1
    fi
fi

mkdir -p "$BIN_DIR" "$UNIT_DIR" "$CODEX_HOME_DIR" "$POLYSCOPE_GIT_BIN_DIR" "$(dirname -- "$POLYSCOPE_EXPOSE_BIN")" "$(dirname -- "$POLYSCOPE_EXPOSE_REAL_BIN")"
ln -sfn "$SOURCE_SCRIPT" "$INSTALL_TARGET"
ln -sfn "$REAPER_SOURCE" "$REAPER_TARGET"
ln -sfn "$WRAPPER_SOURCE" "$EXPOSE_WRAPPER_TARGET"
ln -sfn "$GIT_WRAPPER_SOURCE" "$GIT_WRAPPER_TARGET"
ln -sfn "$CODEX_AGENTS_SOURCE" "$CODEX_AGENTS_TARGET"

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
Environment=POLYSCOPE_SUDO_BIN=$SUDO_BIN
Environment=POLYSCOPE_NGINX_HELPER=$POLYSCOPE_NGINX_HELPER
ExecStart=$INSTALL_TARGET --workspace-root $WORKSPACE_ROOT --polyscope-api-base $POLYSCOPE_API_BASE --nginx-manifest-output $POLYSCOPE_NGINX_MANIFEST --install-nginx
EOF

cat >"$PATH_UNIT" <<EOF
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
[Unit]
Description=Watch SecPal instruction files for Polyscope sync

[Path]
PathChanged=$WORKSPACE_ROOT/api/AGENTS.md
PathChanged=$WORKSPACE_ROOT/api/.github/copilot-instructions.md
PathChanged=$WORKSPACE_ROOT/api/.github/instructions
PathChanged=$WORKSPACE_ROOT/frontend/AGENTS.md
PathChanged=$WORKSPACE_ROOT/frontend/.github/copilot-instructions.md
PathChanged=$WORKSPACE_ROOT/frontend/.github/instructions
PathChanged=$WORKSPACE_ROOT/contracts/AGENTS.md
PathChanged=$WORKSPACE_ROOT/contracts/.github/copilot-instructions.md
PathChanged=$WORKSPACE_ROOT/contracts/.github/instructions
PathChanged=$WORKSPACE_ROOT/android/AGENTS.md
PathChanged=$WORKSPACE_ROOT/android/.github/copilot-instructions.md
PathChanged=$WORKSPACE_ROOT/android/.github/instructions
PathChanged=$WORKSPACE_ROOT/secpal.app/AGENTS.md
PathChanged=$WORKSPACE_ROOT/secpal.app/.github/copilot-instructions.md
PathChanged=$WORKSPACE_ROOT/secpal.app/.github/instructions
PathChanged=$WORKSPACE_ROOT/guardguide.de/AGENTS.md
PathChanged=$WORKSPACE_ROOT/guardguide.de/.github/copilot-instructions.md
PathChanged=$WORKSPACE_ROOT/guardguide.de/.github/instructions
PathChanged=$WORKSPACE_ROOT/GuardGuide/AGENTS.md
PathChanged=$WORKSPACE_ROOT/GuardGuide/.github/copilot-instructions.md
PathChanged=$WORKSPACE_ROOT/GuardGuide/.github/instructions
PathChanged=$WORKSPACE_ROOT/changelog/AGENTS.md
PathChanged=$WORKSPACE_ROOT/changelog/.github/copilot-instructions.md
PathChanged=$WORKSPACE_ROOT/changelog/.github/instructions
PathChanged=$WORKSPACE_ROOT/.github/AGENTS.md
PathChanged=$WORKSPACE_ROOT/.github/.github/copilot-instructions.md
PathChanged=$WORKSPACE_ROOT/.github/.github/instructions
PathChanged=$CODEX_AGENTS_SOURCE
PathChanged=$SOURCE_SCRIPT
PathChanged=$VALIDATOR_SOURCE
PathChanged=$VALIDATOR_PACKAGE_LOCK
PathChanged=$VALIDATOR_INSTALLED_PACKAGE_LOCK
PathChanged=$NGINX_LIBRARY_SOURCE
PathChanged=$NGINX_HELPER_SOURCE

[Install]
WantedBy=default.target
EOF

cat >"$PROVISION_SERVICE_UNIT" <<EOF
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
[Unit]
Description=Provision SecPal Polyscope worktrees automatically
After=polyscope-rollout-sync.service
# Bound the self-trigger feedback loop: DB sync writes to polyscope.db which is
# watched by the paired path unit; without a burst cap this can re-trigger the
# service until systemd rate-limits the unit. Five starts per five minutes
# leaves room for the three-minute fallback timer plus real workspace events
# without letting the provisioning loop run away indefinitely.
StartLimitIntervalSec=300
StartLimitBurst=5

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
PathModified=$HOME/.polyscope/polyscope.db-wal
PathChanged=$WORKSPACE_ROOT/api/polyscope.local.json
PathChanged=$WORKSPACE_ROOT/frontend/polyscope.local.json
PathChanged=$WORKSPACE_ROOT/contracts/polyscope.local.json
PathChanged=$WORKSPACE_ROOT/android/polyscope.local.json
PathChanged=$WORKSPACE_ROOT/secpal.app/polyscope.local.json
PathChanged=$WORKSPACE_ROOT/guardguide.de/polyscope.local.json
PathChanged=$WORKSPACE_ROOT/changelog/polyscope.local.json
PathChanged=$WORKSPACE_ROOT/.github/polyscope.local.json

[Install]
WantedBy=default.target
EOF

cat >"$PROVISION_TIMER_UNIT" <<EOF
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
[Unit]
Description=Poll SecPal Polyscope worktrees for provisioning fallback

[Timer]
OnStartupSec=30s
OnUnitActiveSec=3min
Persistent=true

[Install]
WantedBy=timers.target
EOF

cat >"$REAPER_SERVICE_UNIT" <<EOF
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
[Unit]
Description=Reap orphaned SecPal Polyscope clone roots
After=polyscope-worktree-provision.service

[Service]
Type=oneshot
Environment=PATH=$SERVICE_PATH
ExecStart=$REAPER_TARGET --polyscope-home $POLYSCOPE_HOME --clone-root $POLYSCOPE_CLONE_ROOT --grace-period 7d
EOF

cat >"$REAPER_TIMER_UNIT" <<EOF
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
[Unit]
Description=Schedule conservative Polyscope clone-root reaping

[Timer]
OnStartupSec=10min
OnUnitActiveSec=1d
Persistent=true

[Install]
WantedBy=timers.target
EOF

"$SYSTEMCTL_BIN" --user daemon-reload

if [[ "$server_scope" == "user" ]]; then
    "$SYSTEMCTL_BIN" --user enable --now polyscope-server.service
    "$SYSTEMCTL_BIN" --user restart polyscope-server.service
else
    "$SYSTEMCTL_BIN" --user disable --now polyscope-server.service >/dev/null 2>&1 || true
fi

"$SYSTEMCTL_BIN" --user enable --now polyscope-rollout-sync.path
"$SYSTEMCTL_BIN" --user start polyscope-rollout-sync.service
"$SYSTEMCTL_BIN" --user enable --now polyscope-worktree-provision.path
"$SYSTEMCTL_BIN" --user enable --now polyscope-worktree-provision.timer
"$SYSTEMCTL_BIN" --user enable --now polyscope-clone-reaper.timer

echo "Installed $INSTALL_TARGET"
echo "Installed $EXPOSE_WRAPPER_TARGET"
echo "Installed $GIT_WRAPPER_TARGET"
echo "Installed expose wrapper at $POLYSCOPE_EXPOSE_BIN"
echo "Installed git wrapper at $POLYSCOPE_GIT_WRAPPER_BIN"
echo "Installed Codex instructions at $CODEX_AGENTS_TARGET"
echo "Installed $installed_server_target"
echo "Installed $SERVICE_UNIT"
echo "Installed $PATH_UNIT"
echo "Installed $PROVISION_SERVICE_UNIT"
echo "Installed $PROVISION_PATH_UNIT"
echo "Installed $PROVISION_TIMER_UNIT"
echo "Installed $REAPER_SERVICE_UNIT"
echo "Installed $REAPER_TIMER_UNIT"
