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
DESTDIR="${DESTDIR:-}"
STAGE_ONLY=0

if [[ $# -gt 1 || ( $# -eq 1 && "$1" != "--stage-only" ) ]]; then
    echo "Usage: $0 [--stage-only]" >&2
    exit 2
fi
if [[ ${1:-} == "--stage-only" ]]; then
    STAGE_ONLY=1
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

if [[ "$STAGE_ONLY" -eq 0 ]]; then
    for runtime_file in \
        "$RUNTIME_ROLLOUT_SOURCE" \
        "$RUNTIME_SCRIPT_DIR/validate-ai-instructions.sh" \
        "$RUNTIME_SCRIPT_DIR/polyscope_nginx.py" \
        "$RUNTIME_TOOLCHAIN_ROOT/package-lock.json" \
        "$RUNTIME_TOOLCHAIN_ROOT/node_modules/.package-lock.json" \
        "$RUNTIME_TOOLCHAIN_ROOT/node_modules/js-yaml/index.js"; do
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
fi

if ! SECPAL_UID="$(id -u secpal 2>/dev/null)"; then
    echo "Error: required service user 'secpal' does not exist." >&2
    exit 1
fi

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
Environment=PATH=/home/secpal/.local/lib/polyscope/bin:/home/secpal/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin
Environment=SSH_AUTH_SOCK=/run/user/$SECPAL_UID/openssh_agent
Environment=POLYSCOPE_REAL_GIT_BIN=/usr/bin/git
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
