#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

POLYSCOPE_HOME="${POLYSCOPE_HOME:-$HOME/.polyscope}"
REAL_EXPOSE_BIN="${POLYSCOPE_EXPOSE_REAL_BIN:-$POLYSCOPE_HOME/bin/expose-linux-x64.real}"

normalize_preview_url() {
	local raw_url="$1"
	local scheme_and_rest rest host_port host path host

	case "$raw_url" in
		http://*|https://*)
			;;
		*)
			return 1
			;;
	esac

	scheme_and_rest="${raw_url#*://}"
	rest="$scheme_and_rest"
	host_port="$rest"
	path=""

	if [[ "$rest" == */* ]]; then
		host_port="${rest%%/*}"
		path="/${rest#*/}"
	fi

	host="${host_port%%:*}"

	if [[ ! "$host" =~ ^[A-Za-z0-9.-]+\.preview\.secpal\.dev$ ]]; then
		return 1
	fi

	printf 'https://%s' "$host"
	if [[ -n "$path" && "$path" != "/" ]]; then
		printf '%s' "$path"
	fi
	printf '\n'
}

canonicalize_preview_url_from_marker() {
	local direct_url="$1"
	local marker_path="${POLYSCOPE_PROVISION_MARKER_PATH:-$PWD/.polyscope-secpal-provisioned.json}"
	local clone_root="${POLYSCOPE_CLONE_ROOT:-$HOME/.polyscope/clones}"

	python3 - "$direct_url" "$marker_path" "$clone_root" <<'PY'
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

direct_url = sys.argv[1]
marker_path = Path(sys.argv[2])
clone_root = Path(sys.argv[3])

repo_prefixes = {
    "api": "api",
    "frontend": "frontend",
    "GuardGuide": "guardguide",
    "guardguide.de": "guardguide-de",
    "secpal.app": "secpal-app",
    "changelog": "changelog",
}
url = urlsplit(direct_url)
host_match = re.fullmatch(
    r"(api|frontend|guardguide-de|guardguide|secpal-app|changelog)-([a-z0-9](?:[a-z0-9-]*[a-z0-9])?)\.preview\.secpal\.dev",
    url.hostname or "",
)
if host_match is None:
    raise SystemExit(1)

prefix, physical_workspace = host_match.groups()
marker_paths = []
if marker_path.is_file():
    marker_paths.append(marker_path)
if clone_root.is_dir():
    marker_paths.extend(clone_root.glob(f"*/{physical_workspace}/.polyscope-secpal-provisioned.json"))

canonical_urls = set()
seen_marker_paths = set()
for candidate in marker_paths:
    try:
        resolved_candidate = candidate.resolve()
    except OSError:
        resolved_candidate = candidate
    if resolved_candidate in seen_marker_paths:
        continue
    seen_marker_paths.add(resolved_candidate)

    try:
        marker = json.loads(candidate.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        continue
    if not isinstance(marker, dict):
        continue

    repo = marker.get("repo")
    workspace = marker.get("workspace")
    marker_physical_workspace = marker.get("physical_workspace")
    if repo_prefixes.get(repo) != prefix or marker_physical_workspace != physical_workspace:
        continue
    if not isinstance(workspace, str) or not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", workspace):
        continue

    canonical_host = f"{prefix}-{workspace}.preview.secpal.dev"
    canonical_urls.add(urlunsplit((url.scheme, canonical_host, url.path, url.query, url.fragment)))

if len(canonical_urls) != 1:
    raise SystemExit(1)

print(canonical_urls.pop())
PY
}

api_preview_origin() {
	local direct_url="$1"
	local host_and_path host

	[[ "$direct_url" == https://* ]] || return 1
	host_and_path="${direct_url#https://}"
	host="${host_and_path%%/*}"
	[[ "$host" =~ ^api-[A-Za-z0-9-]+\.preview\.secpal\.dev$ ]] || return 1

	printf 'https://%s\n' "$host"
}

wait_for_api_preview_readiness() {
	local direct_url="$1"
	local readiness_url="${direct_url}/health/ready"
	local retry_seconds="${POLYSCOPE_EXPOSE_WRAPPER_RETRY_SECONDS:-2}"
	local max_attempts="${POLYSCOPE_EXPOSE_WRAPPER_MAX_ATTEMPTS:-302}"
	local attempt status_code

	if [[ ! "$retry_seconds" =~ ^[0-9]+$ || ! "$max_attempts" =~ ^[1-9][0-9]*$ ]]; then
		echo "Error: preview readiness retry settings must be non-negative seconds and positive attempts" >&2
		return 1
	fi

	for ((attempt = 1; attempt <= max_attempts; attempt++)); do
		if status_code="$(curl -fsS --max-time 3 -o /dev/null -w '%{http_code}' "$readiness_url")" \
			&& [[ "$status_code" =~ ^2[0-9][0-9]$ ]]; then
			return 0
		fi

		printf 'Waiting for API preview readiness (%s, attempt %s)\n' "$readiness_url" "$attempt" >&2
		if ((attempt < max_attempts)); then
			sleep "$retry_seconds"
		fi
	done

	echo "Error: API preview did not become ready after $max_attempts attempts" >&2
	return 1
}

announce_direct_preview() {
	local shared_site="$1"
	local direct_url="$2"

	printf '%s\n' 'Expose'
	printf 'Shared site              %s\n' "$shared_site"
	printf 'Public URL               %s\n' "$direct_url"

	if [[ "${POLYSCOPE_EXPOSE_WRAPPER_EXIT_AFTER_ANNOUNCE:-0}" == "1" ]]; then
		exit 0
	fi

	trap 'exit 0' INT TERM HUP
	while true; do
		sleep 3600 &
		wait "$!"
	done
}

if [[ $# -ge 2 && "$1" == "share" ]]; then
	direct_preview_url="$(normalize_preview_url "$2" || true)"
	if [[ -n "$direct_preview_url" ]]; then
		canonical_preview_url=""
		if canonical_preview_url="$(canonicalize_preview_url_from_marker "$direct_preview_url")"; then
			direct_preview_url="$canonical_preview_url"
		elif [[ "$direct_preview_url" =~ ^https://(api|frontend|guardguide-de|guardguide|secpal-app|changelog)-[A-Za-z0-9-]+-[0-9a-fA-F]{8}\.preview\.secpal\.dev(/|$) ]]; then
			echo "Error: refusing to announce physical hash-suffixed preview URL without a canonical workspace host: $direct_preview_url" >&2
			exit 1
		fi
		api_preview_url="$(api_preview_origin "$direct_preview_url" || true)"
		if [[ -n "$api_preview_url" ]]; then
			wait_for_api_preview_readiness "$api_preview_url"
		fi
		announce_direct_preview "$direct_preview_url" "$direct_preview_url"
	fi
fi

if [[ ! -x "$REAL_EXPOSE_BIN" ]]; then
	echo "Error: Expose fallback binary not found at $REAL_EXPOSE_BIN" >&2
	exit 1
fi

exec "$REAL_EXPOSE_BIN" "$@"
