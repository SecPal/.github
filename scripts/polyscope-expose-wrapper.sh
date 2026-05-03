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
		announce_direct_preview "$2" "$direct_preview_url"
	fi
fi

if [[ ! -x "$REAL_EXPOSE_BIN" ]]; then
	echo "Error: Expose fallback binary not found at $REAL_EXPOSE_BIN" >&2
	exit 1
fi

exec "$REAL_EXPOSE_BIN" "$@"
