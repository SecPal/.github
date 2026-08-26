#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail
umask 077

if [[ $# -ne 7 ]]; then
    echo "Usage: $0 RENDERER CLEANUP DB_PATH CLONE_ROOT REPOSITORY_ROOT CADDYFILE PREVIEW_SERVICE" >&2
    exit 2
fi

renderer="$1"
cleanup="$2"
db_path="$3"
clone_root="$4"
repository_root="$5"
caddyfile="$6"
preview_service="$7"
attempts="${POLYSCOPE_PREVIEW_REFRESH_ATTEMPTS:-600}"
delay="${POLYSCOPE_PREVIEW_REFRESH_DELAY_SECONDS:-2}"

if [[ ! "$attempts" =~ ^[1-9][0-9]*$ || ! "$delay" =~ ^[1-9][0-9]*$ ]]; then
    echo "Error: refresh attempts and delay must be positive integers." >&2
    exit 2
fi

error_file="$(mktemp "${TMPDIR:-/tmp}/polyscope-preview-refresh.XXXXXX")"
trap 'rm -f -- "$error_file"' EXIT

for ((attempt = 1; attempt <= attempts; attempt++)); do
    if python3 "$cleanup" \
        --db-path "$db_path" \
        --clone-root "$clone_root" \
        --repository-root "$repository_root" \
        2>"$error_file" \
        && python3 "$renderer" \
        --db-path "$db_path" \
        --container-root /workspaces \
        --clone-root "$clone_root" \
        --repository-root "$repository_root" \
        --output "$caddyfile" \
        2>"$error_file"; then
        systemctl --user restart "$preview_service"
        exit 0
    fi
    if ((attempt < attempts)); then
        sleep "$delay"
    fi
done

echo "Error: Polyscope preview routes did not become renderable after $attempts attempts." >&2
cat "$error_file" >&2
exit 1
