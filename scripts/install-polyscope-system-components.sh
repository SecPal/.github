#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -eEuo pipefail
umask 022

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
HELPER_SOURCE="$SCRIPT_DIR/secpal-polyscope-nginx-apply.py"
LIBRARY_SOURCE="$SCRIPT_DIR/polyscope_nginx.py"
ROLLOUT_SOURCE="$SCRIPT_DIR/polyscope-rollout.py"
RUNTIME_ROLLOUT_SOURCE="/home/secpal/code/SecPal/.github/scripts/polyscope-rollout.py"
RUNTIME_SCRIPT_DIR="${RUNTIME_ROLLOUT_SOURCE%/*}"
RUNTIME_TOOLCHAIN_ROOT="${RUNTIME_SCRIPT_DIR%/scripts}"
RUNTIME_YAML_CHECK="$RUNTIME_SCRIPT_DIR/verify-js-yaml-package.cjs"
RUNTIME_YAML_PACKAGE="$RUNTIME_TOOLCHAIN_ROOT/node_modules/js-yaml"
RUNTIME_PACKAGE_JSON="$RUNTIME_TOOLCHAIN_ROOT/package.json"
RUNTIME_VALIDATOR_BASE="/home/secpal/.local/share/polyscope/ai-instruction-validator"
RUNTIME_VALIDATOR_CURRENT="$RUNTIME_VALIDATOR_BASE/current"
RUNTIME_NPM_CACHE="/home/secpal/.npm"
DESTDIR="${DESTDIR:-}"
NODE_BIN=""
STAGE_ONLY=0

usage() {
    echo "Usage: $0 [--stage-only] [--node-bin PATH]" >&2
    exit 2
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --stage-only)
            STAGE_ONLY=1
            shift
            ;;
        --node-bin)
            [[ $# -ge 2 ]] || usage
            NODE_BIN="$2"
            shift 2
            ;;
        *)
            usage
            ;;
    esac
done

if [[ "$STAGE_ONLY" -eq 1 ]]; then
    if [[ -z "$DESTDIR" ]]; then
        echo "Error: --stage-only requires a non-empty DESTDIR." >&2
        exit 2
    fi
elif [[ "$(id -u)" -ne 0 ]]; then
    echo "Error: this installer must be run as root through an interactive sudo prompt." >&2
    exit 1
fi

for source_file in "$HELPER_SOURCE" "$LIBRARY_SOURCE" "$ROLLOUT_SOURCE"; do
    if [[ ! -f "$source_file" ]]; then
        echo "Error: required system-component source is missing: $source_file" >&2
        exit 1
    fi
done

if [[ "$STAGE_ONLY" -eq 1 ]]; then
    SECPAL_UID=1000
elif ! SECPAL_UID="$(id -u secpal 2>/dev/null)"; then
    echo "Error: required service user 'secpal' does not exist." >&2
    exit 1
fi

if [[ -z "$NODE_BIN" ]]; then
    if [[ "$STAGE_ONLY" -eq 1 ]]; then
        NODE_BIN="/usr/bin/node"
    else
        NODE_BIN="$(command -v node || true)"
    fi
fi
if [[ -z "$NODE_BIN" || "$NODE_BIN" != /* || "$NODE_BIN" =~ [[:space:]:] ]]; then
    echo "Error: Node.js must resolve to an absolute executable path without whitespace or colons." >&2
    exit 1
fi
if [[ "$STAGE_ONLY" -eq 0 ]]; then
    if [[ ! -f "$NODE_BIN" || ! -x "$NODE_BIN" ]]; then
        echo "Error: Node.js executable is missing or not executable: $NODE_BIN" >&2
        exit 1
    fi
    unresolved_node_bin="$NODE_BIN"
    if ! resolved_node_bin="$(readlink -f -- "$NODE_BIN")" || [[ -z "$resolved_node_bin" ]]; then
        echo "Error: failed to resolve the Node.js executable: $unresolved_node_bin" >&2
        exit 1
    fi
    NODE_BIN="$resolved_node_bin"
    if [[ "$NODE_BIN" != /* || "$NODE_BIN" =~ [[:space:]:] ]]; then
        echo "Error: resolved Node.js path is unsafe for the service PATH: $NODE_BIN" >&2
        exit 1
    fi
    if [[ ! -x /usr/bin/sudo ]] \
        || ! /usr/bin/sudo -u secpal -- /usr/bin/test -x "$NODE_BIN"; then
        echo "Error: Node.js is not executable by the secpal service user: $NODE_BIN" >&2
        exit 1
    fi
fi
NODE_BIN_DIR="$(dirname -- "$NODE_BIN")"
BASE_SERVICE_PATH="/home/secpal/.local/lib/polyscope/bin:/home/secpal/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin"
case ":$BASE_SERVICE_PATH:" in
    *":$NODE_BIN_DIR:"*) SYSTEM_SERVICE_PATH="$BASE_SERVICE_PATH" ;;
    *) SYSTEM_SERVICE_PATH="$NODE_BIN_DIR:$BASE_SERVICE_PATH" ;;
esac

if [[ "$STAGE_ONLY" -eq 0 ]]; then
    for runtime_file in \
        "$RUNTIME_ROLLOUT_SOURCE" \
        "$RUNTIME_SCRIPT_DIR/validate-ai-instructions.sh" \
        "$RUNTIME_SCRIPT_DIR/polyscope_nginx.py" \
        "$RUNTIME_YAML_CHECK" \
        "$RUNTIME_PACKAGE_JSON" \
        "$RUNTIME_TOOLCHAIN_ROOT/package-lock.json" \
        "$RUNTIME_TOOLCHAIN_ROOT/node_modules/.package-lock.json" \
        "$RUNTIME_TOOLCHAIN_ROOT/node_modules/js-yaml/package.json"; do
        if [[ ! -f "$runtime_file" ]]; then
            echo "Error: canonical Polyscope runtime source is missing: $runtime_file" >&2
            exit 1
        fi
    done
    if [[ ! -x "$RUNTIME_ROLLOUT_SOURCE" \
        || ! -x "$RUNTIME_SCRIPT_DIR/validate-ai-instructions.sh" \
        || ! -x "$RUNTIME_TOOLCHAIN_ROOT/node_modules/.bin/markdownlint" ]]; then
        echo "Error: canonical Polyscope runtime scripts and pinned validator must be executable below $RUNTIME_TOOLCHAIN_ROOT." >&2
        exit 1
    fi
    if ! /usr/bin/sudo -u secpal -- \
        "$NODE_BIN" "$RUNTIME_YAML_CHECK" "$RUNTIME_YAML_PACKAGE"; then
        echo "Error: canonical Polyscope runtime js-yaml package is unusable; reinstall the committed dependencies before activation." >&2
        exit 1
    fi
    for trusted_system_tool in \
        /usr/bin/awk \
        /usr/bin/flock \
        /usr/bin/git \
        /usr/bin/grep \
        /usr/bin/readlink \
        /usr/bin/sha256sum \
        /usr/bin/tar; do
        if [[ ! -x "$trusted_system_tool" ]]; then
            echo "Error: trusted system runtime tool is unavailable: $trusted_system_tool" >&2
            exit 1
        fi
    done
    runtime_npm="$(PATH="$SYSTEM_SERVICE_PATH" command -v npm || true)"
    if [[ -z "$runtime_npm" || "$runtime_npm" != /* ]] \
        || ! /usr/bin/sudo -u secpal -- /usr/bin/test -x "$runtime_npm"; then
        echo "Error: npm is unavailable to the secpal service user." >&2
        exit 1
    fi
fi

validator_node_modules_digest() {
    local toolchain_root="$1"

    /usr/bin/tar \
        --sort=name \
        --mtime='@0' \
        --owner=0 \
        --group=0 \
        --numeric-owner \
        --format=gnu \
        -cf - \
        -C "$toolchain_root" node_modules \
        | /usr/bin/sha256sum \
        | /usr/bin/awk '{print $1}'
}

validator_source_commit() {
    local source_commit

    if ! source_commit="$(
        /usr/bin/sudo -u secpal -- /usr/bin/git -C "$RUNTIME_TOOLCHAIN_ROOT" \
            log -1 --format=%H HEAD -- package.json package-lock.json 2>/dev/null
    )" \
        || [[ ! "$source_commit" =~ ^[0-9a-f]{40}$ ]]; then
        echo "Error: validator runtime source must belong to a Git commit." >&2
        return 1
    fi
    if ! /usr/bin/sudo -u secpal -- /usr/bin/git -C "$RUNTIME_TOOLCHAIN_ROOT" \
        diff --quiet HEAD -- package.json package-lock.json; then
        echo "Error: validator runtime package metadata must match its source commit." >&2
        return 1
    fi
    printf '%s\n' "$source_commit"
}

validator_snapshot_source_commit() {
    local toolchain_root="$1"

    /usr/bin/awk -F= \
        '$1 == "source_commit" { print substr($0, index($0, "=") + 1) }' \
        "$toolchain_root/.secpal-validator-snapshot"
}

installed_validator_toolchain_usable() {
    local toolchain_root="$1"
    local expected_lock_digest="$2"
    local expected_schema="${3:-2}"
    local installed_lock_digest installed_node_modules_digest installed_source_commit

    [[ -d "$toolchain_root" && ! -L "$toolchain_root" ]] || return 1
    read -r installed_lock_digest _ < <(
        /usr/bin/sha256sum "$toolchain_root/package-lock.json"
    )
    if [[ "$installed_lock_digest" != "$expected_lock_digest" ]]; then
        return 1
    fi
    if ! installed_node_modules_digest="$(validator_node_modules_digest "$toolchain_root")"; then
        return 1
    fi

    [[ -f "$toolchain_root/package.json" \
        && -f "$toolchain_root/package-lock.json" \
        && -f "$toolchain_root/node_modules/.package-lock.json" \
        && -f "$toolchain_root/.secpal-validator-snapshot" \
        && -x "$toolchain_root/node_modules/.bin/markdownlint" ]] \
        && /usr/bin/grep -qxF \
            "schema=$expected_schema" \
            "$toolchain_root/.secpal-validator-snapshot" \
        && /usr/bin/grep -qxF \
            "lock_sha256=$expected_lock_digest" \
            "$toolchain_root/.secpal-validator-snapshot" \
        && /usr/bin/grep -qxF \
            "node_modules_sha256=$installed_node_modules_digest" \
            "$toolchain_root/.secpal-validator-snapshot" \
        && /usr/bin/sudo -u secpal -- /usr/bin/env \
            PATH="$SYSTEM_SERVICE_PATH" \
            "$toolchain_root/node_modules/.bin/markdownlint" --version >/dev/null 2>&1 \
        && /usr/bin/sudo -u secpal -- \
            "$NODE_BIN" "$RUNTIME_YAML_CHECK" "$toolchain_root/node_modules/js-yaml" >/dev/null 2>&1 \
        || return 1
    if [[ "$expected_schema" -eq 2 ]]; then
        installed_source_commit="$(validator_snapshot_source_commit "$toolchain_root")"
        [[ "$installed_source_commit" =~ ^[0-9a-f]{40}$ ]] || return 1
    fi
}

validator_snapshot_activation_allowed() {
    local candidate_dir="$1"
    local candidate_name="$2"
    local candidate_lock_digest="$3"
    local current_name current_dir current_lock_digest current_name_source_commit
    local candidate_source_commit candidate_name_source_commit current_source_commit

    candidate_source_commit="$(validator_snapshot_source_commit "$candidate_dir")"
    if [[ ! "$candidate_name" =~ ^v3-([0-9a-f]{64})-([0-9a-f]{40})$ ]]; then
        echo "Error: validator runtime candidate has an invalid target name: $candidate_name" >&2
        return 1
    fi
    candidate_name_source_commit="${BASH_REMATCH[2]}"
    if [[ "${BASH_REMATCH[1]}" != "$candidate_lock_digest" \
        || "$candidate_name_source_commit" != "$candidate_source_commit" ]]; then
        echo "Error: validator runtime candidate identity does not match its target name." >&2
        return 1
    fi

    if [[ ! -e "$RUNTIME_VALIDATOR_CURRENT" && ! -L "$RUNTIME_VALIDATOR_CURRENT" ]]; then
        return 0
    fi
    if ! current_name="$(/usr/bin/readlink "$RUNTIME_VALIDATOR_CURRENT")"; then
        echo "Error: failed to read validator runtime current pointer." >&2
        return 1
    fi
    if [[ "$current_name" == "$candidate_name" ]]; then
        return 0
    fi
    if [[ "$current_name" =~ ^v2-([0-9a-f]{64})$ ]]; then
        current_lock_digest="${BASH_REMATCH[1]}"
        current_dir="$RUNTIME_VALIDATOR_BASE/$current_name"
        if [[ "$current_lock_digest" != "$candidate_lock_digest" ]] \
            || ! installed_validator_toolchain_usable \
                "$current_dir" "$current_lock_digest" 1; then
            echo "Error: legacy validator runtime snapshot cannot be migrated safely: $current_dir" >&2
            return 1
        fi
        return 0
    fi
    if [[ ! "$current_name" =~ ^v3-([0-9a-f]{64})-([0-9a-f]{40})$ ]]; then
        echo "Error: validator runtime current pointer has an invalid target: $current_name" >&2
        return 1
    fi
    current_lock_digest="${BASH_REMATCH[1]}"
    current_name_source_commit="${BASH_REMATCH[2]}"
    current_dir="$RUNTIME_VALIDATOR_BASE/$current_name"
    if ! installed_validator_toolchain_usable "$current_dir" "$current_lock_digest"; then
        echo "Error: active validator runtime snapshot is incomplete: $current_dir" >&2
        return 1
    fi

    current_source_commit="$(validator_snapshot_source_commit "$current_dir")"
    if [[ "$current_source_commit" != "$current_name_source_commit" ]]; then
        echo "Error: active validator runtime source identity does not match its target name." >&2
        return 1
    fi
    if ! /usr/bin/sudo -u secpal -- /usr/bin/git -C "$RUNTIME_TOOLCHAIN_ROOT" \
        cat-file -e "$current_source_commit^{commit}" 2>/dev/null \
        || ! /usr/bin/sudo -u secpal -- /usr/bin/git -C "$RUNTIME_TOOLCHAIN_ROOT" \
            merge-base --is-ancestor \
            "$current_source_commit" "$candidate_source_commit"; then
        echo "Error: refusing to reactivate stale validator runtime snapshot: $candidate_dir" >&2
        return 1
    fi
}

install_validator_runtime_toolchain() {
    local lock_digest node_modules_digest snapshot_dir snapshot_name source_commit staging_dir temporary_link
    local validator_runtime_lock_file validator_runtime_lock_fd

    if [[ -e "$RUNTIME_VALIDATOR_CURRENT" && ! -L "$RUNTIME_VALIDATOR_CURRENT" ]]; then
        echo "Error: validator runtime current pointer must be a symlink: $RUNTIME_VALIDATOR_CURRENT" >&2
        exit 1
    fi

    /usr/bin/sudo -u secpal -- mkdir -p "$RUNTIME_VALIDATOR_BASE"
    validator_runtime_lock_file="$RUNTIME_VALIDATOR_BASE/.install.lock"
    /usr/bin/sudo -u secpal -- touch "$validator_runtime_lock_file"
    exec {validator_runtime_lock_fd}>"$validator_runtime_lock_file"
    /usr/bin/flock "$validator_runtime_lock_fd"

    read -r lock_digest _ < <(
        /usr/bin/sha256sum "$RUNTIME_TOOLCHAIN_ROOT/package-lock.json"
    )
    if ! source_commit="$(validator_source_commit)"; then
        exit 1
    fi
    snapshot_name="v3-$lock_digest-$source_commit"
    snapshot_dir="$RUNTIME_VALIDATOR_BASE/$snapshot_name"
    if [[ -e "$snapshot_dir" || -L "$snapshot_dir" ]]; then
        if [[ ! -d "$snapshot_dir" || -L "$snapshot_dir" ]]; then
            echo "Error: installed validator runtime snapshot must be a regular directory: $snapshot_dir" >&2
            exit 1
        fi
        if ! installed_validator_toolchain_usable "$snapshot_dir" "$lock_digest"; then
            echo "Error: installed validator runtime snapshot is incomplete: $snapshot_dir" >&2
            exit 1
        fi
    else
        staging_dir="$(/usr/bin/sudo -u secpal -- \
            mktemp -d "$RUNTIME_VALIDATOR_BASE/.staging-$lock_digest.XXXXXX")"
        /usr/bin/sudo -u secpal -- \
            cp "$RUNTIME_PACKAGE_JSON" "$staging_dir/package.json"
        /usr/bin/sudo -u secpal -- \
            cp "$RUNTIME_TOOLCHAIN_ROOT/package-lock.json" "$staging_dir/package-lock.json"
        if ! /usr/bin/sudo -u secpal -- /usr/bin/env \
            HOME=/home/secpal \
            NPM_CONFIG_CACHE="$RUNTIME_NPM_CACHE" \
            PATH="$SYSTEM_SERVICE_PATH" \
            npm ci --prefix "$staging_dir" --offline --ignore-scripts --no-audit --no-fund; then
            /usr/bin/sudo -u secpal -- rm -rf -- "$staging_dir"
            echo "Error: failed to install the isolated validator runtime from the committed lockfile and local npm cache." >&2
            exit 1
        fi
        if ! node_modules_digest="$(validator_node_modules_digest "$staging_dir")"; then
            /usr/bin/sudo -u secpal -- rm -rf -- "$staging_dir"
            echo "Error: failed to hash the isolated validator runtime toolchain." >&2
            exit 1
        fi
        if ! printf 'schema=2\nlock_sha256=%s\nnode_modules_sha256=%s\nsource_commit=%s\n' \
            "$lock_digest" "$node_modules_digest" "$source_commit" \
            | /usr/bin/sudo -u secpal -- \
                /usr/bin/tee "$staging_dir/.secpal-validator-snapshot" >/dev/null; then
            /usr/bin/sudo -u secpal -- rm -rf -- "$staging_dir"
            echo "Error: failed to record validator runtime snapshot integrity." >&2
            exit 1
        fi
        if ! installed_validator_toolchain_usable "$staging_dir" "$lock_digest"; then
            /usr/bin/sudo -u secpal -- rm -rf -- "$staging_dir"
            echo "Error: failed to stage a complete isolated validator runtime toolchain." >&2
            exit 1
        fi
        if ! /usr/bin/sudo -u secpal -- mv -T "$staging_dir" "$snapshot_dir" 2>/dev/null; then
            if installed_validator_toolchain_usable "$snapshot_dir" "$lock_digest"; then
                /usr/bin/sudo -u secpal -- rm -rf -- "$staging_dir"
            else
                /usr/bin/sudo -u secpal -- rm -rf -- "$staging_dir"
                echo "Error: failed to publish the validator runtime snapshot: $snapshot_dir" >&2
                exit 1
            fi
        fi
    fi

    if ! validator_snapshot_activation_allowed \
        "$snapshot_dir" "$snapshot_name" "$lock_digest"; then
        exit 1
    fi
    temporary_link="$RUNTIME_VALIDATOR_BASE/.current-$$"
    /usr/bin/sudo -u secpal -- rm -f -- "$temporary_link"
    /usr/bin/sudo -u secpal -- ln -s "$snapshot_name" "$temporary_link"
    /usr/bin/sudo -u secpal -- mv -Tf "$temporary_link" "$RUNTIME_VALIDATOR_CURRENT"
    /usr/bin/flock -u "$validator_runtime_lock_fd"
}

prefix_path() {
    printf '%s%s\n' "$DESTDIR" "$1"
}

LIBEXEC_DIR="$(prefix_path /usr/local/libexec)"
HELPER_TARGET="$LIBEXEC_DIR/secpal-polyscope-nginx-apply"
LIBRARY_TARGET="$LIBEXEC_DIR/polyscope_nginx.py"
ROLLOUT_TARGET="$LIBEXEC_DIR/polyscope-rollout.py"
SUDOERS_TARGET="$(prefix_path /etc/sudoers.d/secpal-polyscope-nginx)"
DROPIN_DIR="$(prefix_path /etc/systemd/system/polyscope-server.service.d)"
DROPIN_TARGET="$DROPIN_DIR/zz-secpal-runtime.conf"

TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/polyscope-system-components.XXXXXX")"
trap 'rm -rf "$TEMP_DIR"' EXIT

cat >"$TEMP_DIR/secpal-polyscope-nginx" <<'EOF'
secpal ALL=(root) NOPASSWD: /usr/local/libexec/secpal-polyscope-nginx-apply ""
secpal ALL=(root) NOPASSWD: /usr/local/libexec/secpal-polyscope-nginx-apply --check
EOF
chmod 0440 "$TEMP_DIR/secpal-polyscope-nginx"

cat >"$TEMP_DIR/zz-secpal-runtime.conf" <<EOF
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
[Service]
User=secpal
ExecStart=
ExecStart=/home/secpal/.local/bin/polyscope-server serve --host 127.0.0.1 --port 4321
ExecStartPost=
ExecStartPost=/usr/bin/env bash -lc 'for attempt in 1 2 3 4 5 6 7 8 9 10; do curl -sf http://127.0.0.1:4321/api/repos >/dev/null 2>&1 && exec $RUNTIME_ROLLOUT_SOURCE --workspace-root /home/secpal/code/SecPal --polyscope-api-base http://127.0.0.1:4321/api --nginx-manifest-output /home/secpal/.local/state/polyscope/nginx-manifest.json --install-nginx; sleep 1; done; echo "Polyscope API did not become ready in time." >&2; exit 1'
Environment=PATH=$SYSTEM_SERVICE_PATH
Environment=SSH_AUTH_SOCK=/run/user/$SECPAL_UID/openssh_agent
Environment=POLYSCOPE_REAL_GIT_BIN=/usr/bin/git
Environment=SECPAL_AI_VALIDATOR_TOOLCHAIN_ROOT=$RUNTIME_VALIDATOR_CURRENT
EOF
chmod 0644 "$TEMP_DIR/zz-secpal-runtime.conf"

if [[ -x /usr/sbin/visudo ]]; then
    /usr/sbin/visudo -c -f "$TEMP_DIR/secpal-polyscope-nginx" >/dev/null
elif [[ "$STAGE_ONLY" -eq 0 ]]; then
    echo "Error: /usr/sbin/visudo is required before installing sudoers policy." >&2
    exit 1
fi

install_atomic() {
    local source="$1"
    local target="$2"
    local mode="$3"
    local target_dir temporary_target

    target_dir="$(dirname -- "$target")"
    install -d -m 0755 "$target_dir"
    temporary_target="$target_dir/.${target##*/}.tmp-$$"
    install -m "$mode" -o root -g root "$source" "$temporary_target"
    mv -f "$temporary_target" "$target"
}

if [[ "$STAGE_ONLY" -eq 1 ]]; then
    install -d -m 0755 "$LIBEXEC_DIR" "$(dirname -- "$SUDOERS_TARGET")" "$DROPIN_DIR"
    install -m 0755 "$HELPER_SOURCE" "$HELPER_TARGET"
    install -m 0644 "$LIBRARY_SOURCE" "$LIBRARY_TARGET"
    install -m 0644 "$ROLLOUT_SOURCE" "$ROLLOUT_TARGET"
    install -m 0440 "$TEMP_DIR/secpal-polyscope-nginx" "$SUDOERS_TARGET"
    install -m 0644 "$TEMP_DIR/zz-secpal-runtime.conf" "$DROPIN_TARGET"
    echo "Staged Polyscope system components below $DESTDIR"
    exit 0
fi

install_validator_runtime_toolchain

backup_target() {
    local target="$1"
    local key="$2"
    if [[ -e "$target" || -L "$target" ]]; then
        cp -a -- "$target" "$TEMP_DIR/$key.backup"
    else
        : >"$TEMP_DIR/$key.absent"
    fi
}

restore_target() {
    local target="$1"
    local key="$2"
    if [[ -e "$TEMP_DIR/$key.absent" ]]; then
        rm -f -- "$target"
    elif [[ -e "$TEMP_DIR/$key.backup" || -L "$TEMP_DIR/$key.backup" ]]; then
        install -d -m 0755 "$(dirname -- "$target")"
        rm -f -- "$target"
        cp -a -- "$TEMP_DIR/$key.backup" "$target"
    fi
}

backup_target "$HELPER_TARGET" helper
backup_target "$LIBRARY_TARGET" library
backup_target "$ROLLOUT_TARGET" rollout
backup_target "$SUDOERS_TARGET" sudoers
backup_target "$DROPIN_TARGET" dropin

rollback() {
    local status=$?
    trap - ERR
    restore_target "$HELPER_TARGET" helper
    restore_target "$LIBRARY_TARGET" library
    restore_target "$ROLLOUT_TARGET" rollout
    restore_target "$SUDOERS_TARGET" sudoers
    restore_target "$DROPIN_TARGET" dropin
    /usr/bin/systemctl daemon-reload >/dev/null 2>&1 || true
    /usr/bin/systemctl restart polyscope-server.service >/dev/null 2>&1 || true
    exit "$status"
}
trap rollback ERR

install_atomic "$HELPER_SOURCE" "$HELPER_TARGET" 0755
install_atomic "$LIBRARY_SOURCE" "$LIBRARY_TARGET" 0644
install_atomic "$ROLLOUT_SOURCE" "$ROLLOUT_TARGET" 0644
install_atomic "$TEMP_DIR/secpal-polyscope-nginx" "$SUDOERS_TARGET" 0440
install_atomic "$TEMP_DIR/zz-secpal-runtime.conf" "$DROPIN_TARGET" 0644

/usr/sbin/visudo -c >/dev/null
/usr/bin/systemctl daemon-reload
/usr/bin/systemctl enable polyscope-server.service
/usr/bin/systemctl restart polyscope-server.service

trap - ERR
echo "Installed Polyscope system components with a constrained nginx helper boundary."
