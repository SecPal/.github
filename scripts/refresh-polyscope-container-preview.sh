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
caddy_directory="$(dirname -- "$caddyfile")"
rendered_file="$(mktemp "$caddy_directory/.Caddyfile.refresh.XXXXXX")"
previous_file="$(mktemp "$caddy_directory/.Caddyfile.previous.XXXXXX")"
had_previous=false
trap 'rm -f -- "$error_file" "$rendered_file" "$previous_file"' EXIT

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
        --output "$rendered_file" \
        2>"$error_file"; then
        if [[ -f "$caddyfile" ]] && cmp -s -- "$rendered_file" "$caddyfile"; then
            exit 0
        fi
        if [[ -f "$caddyfile" ]]; then
            cp -p -- "$caddyfile" "$previous_file"
            had_previous=true
        else
            had_previous=false
        fi
        mv -f -- "$rendered_file" "$caddyfile"
        if systemctl --user restart "$preview_service" 2>"$error_file"; then
            rm -f -- "$previous_file"
            exit 0
        fi
        if [[ "$had_previous" == true ]]; then
            mv -f -- "$previous_file" "$caddyfile"
        else
            rm -f -- "$caddyfile"
        fi
    fi
    if ((attempt < attempts)); then
        sleep "$delay"
    fi
done

echo "Error: Polyscope preview routes did not become renderable after $attempts attempts." >&2
cat "$error_file" >&2
exit 1
