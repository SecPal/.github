#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -eEuo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROXY_SOURCE="$SCRIPT_DIR/polyscope-postgresql-socket-proxy.py"
RENDERER_SOURCE="$SCRIPT_DIR/render-polyscope-container-caddy.py"
IMAGE="${POLYSCOPE_PREVIEW_IMAGE:-localhost/secpal-polyscope-api-toolchain:php84}"
NETWORK="${POLYSCOPE_PREVIEW_NETWORK:-polyscope-preview-db}"
PREVIEW_PORT="${POLYSCOPE_PREVIEW_PORT:-18080}"
POSTGRES_SOCKET="${POLYSCOPE_POSTGRES_SOCKET:-/var/run/postgresql/.s.PGSQL.5432}"
CLONE_ROOT="${POLYSCOPE_CLONE_ROOT:-$HOME/.polyscope/clones}"
CADDYFILE="${POLYSCOPE_PREVIEW_CADDYFILE:-$HOME/.config/polyscope-preview/Caddyfile}"
POLYSCOPE_DB_PATH="${POLYSCOPE_DB_PATH:-$HOME/.polyscope/polyscope.db}"
BIN_DIR="${POLYSCOPE_BIN_DIR:-$HOME/.local/bin}"
LIBEXEC_DIR="${POLYSCOPE_LIBEXEC_DIR:-$HOME/.local/libexec}"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

usage() {
    echo "Usage: $0 [--image IMAGE] [--network NAME] [--preview-port PORT] [--postgres-socket PATH] [--caddyfile PATH]" >&2
    exit 2
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --image) IMAGE="$2"; shift 2 ;;
        --network) NETWORK="$2"; shift 2 ;;
        --preview-port) PREVIEW_PORT="$2"; shift 2 ;;
        --postgres-socket) POSTGRES_SOCKET="$2"; shift 2 ;;
        --caddyfile) CADDYFILE="$2"; shift 2 ;;
        *) usage ;;
    esac
done

if [[ "$(id -u)" -eq 0 ]]; then
    echo "Error: run this installer as the dedicated Polyscope runtime user, not root." >&2
    exit 1
fi

if [[ ! "$IMAGE" =~ ^[A-Za-z0-9._/:@+-]+$ ]]; then
    echo "Error: image reference contains unsupported characters." >&2
    exit 1
fi
if [[ ! "$NETWORK" =~ ^[A-Za-z0-9_.-]+$ ]]; then
    echo "Error: network name contains unsupported characters." >&2
    exit 1
fi
for path_name in POSTGRES_SOCKET CLONE_ROOT CADDYFILE POLYSCOPE_DB_PATH BIN_DIR LIBEXEC_DIR UNIT_DIR; do
    path_value="${!path_name}"
    if [[ ! "$path_value" =~ ^/[A-Za-z0-9._/+-]+$ ]]; then
        echo "Error: $path_name must be an absolute path containing only supported characters." >&2
        exit 1
    fi
done
if [[ ! "$PREVIEW_PORT" =~ ^[0-9]+$ || "$PREVIEW_PORT" -lt 1 || "$PREVIEW_PORT" -gt 65535 ]]; then
    echo "Error: preview port must be between 1 and 65535." >&2
    exit 1
fi

for required_file in "$PROXY_SOURCE" "$RENDERER_SOURCE" "$POSTGRES_SOCKET" "$POLYSCOPE_DB_PATH"; do
    if [[ ! -e "$required_file" ]]; then
        echo "Error: required runtime input is missing: $required_file" >&2
        exit 1
    fi
done
if [[ ! -S "$POSTGRES_SOCKET" ]]; then
    echo "Error: PostgreSQL endpoint is not a Unix socket: $POSTGRES_SOCKET" >&2
    exit 1
fi
if [[ ! -d "$CLONE_ROOT" ]]; then
    echo "Error: Polyscope clone root is unavailable: $CLONE_ROOT" >&2
    exit 1
fi

for command_name in podman python3 systemctl; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        echo "Error: required command is unavailable: $command_name" >&2
        exit 1
    fi
done

if command -v getenforce >/dev/null 2>&1 && [[ "$(getenforce)" == Enforcing ]]; then
    clone_context="$(ls -Zd -- "$CLONE_ROOT")"
    if [[ "$clone_context" != *:container_file_t:* ]]; then
        echo "Error: SELinux Enforcing requires container_file_t on $CLONE_ROOT." >&2
        echo "Observed: $clone_context" >&2
        exit 1
    fi
fi

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"

podman image exists "$IMAGE"
network_created=0

temporary_dir="$(mktemp -d "${TMPDIR:-/tmp}/polyscope-container-preview.XXXXXX")"
trap 'rm -rf "$temporary_dir"' EXIT

python3 "$RENDERER_SOURCE" \
    --db-path "$POLYSCOPE_DB_PATH" \
    --container-root /workspaces \
    --output "$temporary_dir/Caddyfile"

cat >"$temporary_dir/php" <<EOF
#!/bin/sh
set -eu
export XDG_RUNTIME_DIR="\${XDG_RUNTIME_DIR:-/run/user/\$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="\${DBUS_SESSION_BUS_ADDRESS:-unix:path=\$XDG_RUNTIME_DIR/bus}"
exec podman run --rm \\
  --network '$NETWORK' \\
  -e DB_HOST=polyscope-postgresql-proxy \\
  -e DB_PORT=5432 \\
  -v "\$PWD":/app:rw \\
  -v '$CLONE_ROOT':'$CLONE_ROOT':rw \\
  --workdir /app \\
  '$IMAGE' php "\$@"
EOF

cat >"$temporary_dir/composer" <<EOF
#!/bin/sh
set -eu
export XDG_RUNTIME_DIR="\${XDG_RUNTIME_DIR:-/run/user/\$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="\${DBUS_SESSION_BUS_ADDRESS:-unix:path=\$XDG_RUNTIME_DIR/bus}"
exec podman run --rm \\
  -v "\$PWD":/app:rw \\
  -v '$CLONE_ROOT':'$CLONE_ROOT':rw \\
  --workdir /app \\
  --entrypoint composer \\
  '$IMAGE' "\$@"
EOF

cat >"$temporary_dir/polyscope-postgresql-proxy.service" <<EOF
[Unit]
Description=Polyscope PostgreSQL container-network proxy
ConditionPathIsSocket=$POSTGRES_SOCKET

[Service]
Type=simple
Environment=XDG_RUNTIME_DIR=%t
Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=%t/bus
ExecStart=/usr/bin/podman run --replace --rm --name polyscope-postgresql-proxy --network $NETWORK --read-only --cap-drop=all --security-opt no-new-privileges --security-opt label=disable -v %h/.local/libexec/polyscope-postgresql-socket-proxy.py:/usr/local/bin/polyscope-postgresql-socket-proxy.py:ro -v ${POSTGRES_SOCKET%/*}:${POSTGRES_SOCKET%/*}:ro --entrypoint python3 $IMAGE /usr/local/bin/polyscope-postgresql-socket-proxy.py --listen-host 0.0.0.0 --listen-port 5432 --upstream $POSTGRES_SOCKET
ExecStop=/usr/bin/podman stop -t 10 polyscope-postgresql-proxy
Restart=on-failure
RestartSec=3
UMask=0077

[Install]
WantedBy=default.target
EOF

cat >"$temporary_dir/polyscope-preview.service" <<EOF
[Unit]
Description=SecPal Polyscope workspace preview runtime
After=network-online.target polyscope-postgresql-proxy.service
Wants=network-online.target
Requires=polyscope-postgresql-proxy.service

[Service]
Type=simple
Environment=XDG_RUNTIME_DIR=%t
Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=%t/bus
ExecStart=/usr/bin/podman run --replace --rm --name polyscope-preview --network $NETWORK -e DB_HOST=polyscope-postgresql-proxy -e DB_PORT=5432 -p 127.0.0.1:$PREVIEW_PORT:18080 -v $CADDYFILE:/etc/frankenphp/Caddyfile:ro -v $CLONE_ROOT:/workspaces:rw -v $CLONE_ROOT:$CLONE_ROOT:rw --entrypoint /usr/local/bin/frankenphp $IMAGE run --config /etc/frankenphp/Caddyfile --adapter caddyfile
ExecStop=/usr/bin/podman stop -t 10 polyscope-preview
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
EOF

install -d -m 0755 "$BIN_DIR" "$LIBEXEC_DIR" "$UNIT_DIR"
install -d -m 0700 "$(dirname -- "$CADDYFILE")"
backup_dir="$HOME/.local/state/polyscope/backups/$(date -u +%Y%m%dT%H%M%SZ)-container-preview"
install -d -m 0700 "$backup_dir"

backup_target() {
    local target="$1"
    local backup_name="$2"

    if [[ -e "$target" || -L "$target" ]]; then
        cp -a -- "$target" "$backup_dir/$backup_name"
    else
        : >"$backup_dir/$backup_name.absent"
    fi
}

install_managed() {
    local source="$1"
    local target="$2"
    local mode="$3"
    local temporary_target

    temporary_target="${target}.tmp-$$"
    install -m "$mode" "$source" "$temporary_target"
    mv -f -- "$temporary_target" "$target"
}

restore_target() {
    local target="$1"
    local backup_name="$2"

    if [[ -e "$backup_dir/$backup_name.absent" ]]; then
        rm -f -- "$target"
    elif [[ -e "$backup_dir/$backup_name" || -L "$backup_dir/$backup_name" ]]; then
        rm -f -- "$target"
        cp -a -- "$backup_dir/$backup_name" "$target"
    fi
}

proxy_target="$LIBEXEC_DIR/polyscope-postgresql-socket-proxy.py"
renderer_target="$LIBEXEC_DIR/render-polyscope-container-caddy.py"
php_target="$BIN_DIR/php"
composer_target="$BIN_DIR/composer"
proxy_unit_target="$UNIT_DIR/polyscope-postgresql-proxy.service"
preview_unit_target="$UNIT_DIR/polyscope-preview.service"
caddyfile_target="$CADDYFILE"

backup_target "$proxy_target" proxy.py
backup_target "$renderer_target" renderer.py
backup_target "$php_target" php
backup_target "$composer_target" composer
backup_target "$proxy_unit_target" postgresql-proxy.service
backup_target "$preview_unit_target" preview.service
backup_target "$caddyfile_target" Caddyfile

rollback() {
    local status=$?
    trap - ERR
    restore_target "$proxy_target" proxy.py
    restore_target "$renderer_target" renderer.py
    restore_target "$php_target" php
    restore_target "$composer_target" composer
    restore_target "$proxy_unit_target" postgresql-proxy.service
    restore_target "$preview_unit_target" preview.service
    restore_target "$caddyfile_target" Caddyfile
    systemctl --user daemon-reload >/dev/null 2>&1 || true
    systemctl --user restart polyscope-postgresql-proxy.service >/dev/null 2>&1 || true
    systemctl --user restart polyscope-preview.service >/dev/null 2>&1 || true
    if [[ "$network_created" -eq 1 ]]; then
        podman network rm "$NETWORK" >/dev/null 2>&1 || true
    fi
    echo "Error: installation failed; previous managed files were restored from $backup_dir" >&2
    exit "$status"
}
trap rollback ERR

if ! podman network exists "$NETWORK"; then
    podman network create "$NETWORK" >/dev/null
    network_created=1
fi

install_managed "$PROXY_SOURCE" "$proxy_target" 0755
install_managed "$RENDERER_SOURCE" "$renderer_target" 0755
install_managed "$temporary_dir/Caddyfile" "$caddyfile_target" 0600
install_managed "$temporary_dir/php" "$php_target" 0755
install_managed "$temporary_dir/composer" "$composer_target" 0755
install_managed "$temporary_dir/polyscope-postgresql-proxy.service" "$proxy_unit_target" 0644
install_managed "$temporary_dir/polyscope-preview.service" "$preview_unit_target" 0644

systemctl --user daemon-reload
systemctl --user enable --now polyscope-postgresql-proxy.service
systemctl --user enable --now polyscope-preview.service
systemctl --user is-active --quiet polyscope-postgresql-proxy.service
systemctl --user is-active --quiet polyscope-preview.service

trap - ERR
echo "Installed the Polyscope container preview runtime."
echo "Previous managed files, when present, were saved below $backup_dir"
