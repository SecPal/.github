#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

REAL_GIT_BIN="${POLYSCOPE_REAL_GIT_BIN:-/usr/bin/git}"

has_commit_signing_flag() {
	for arg in "$@"; do
		case "$arg" in
			-S|--gpg-sign|--gpg-sign=*|--no-gpg-sign)
				return 0
				;;
		esac
	done

	return 1
}

if [[ ! -x "$REAL_GIT_BIN" ]]; then
	echo "Error: git fallback binary not found at $REAL_GIT_BIN" >&2
	exit 1
fi

argv=("$@")
prefix=()
subcommand=""
subcommand_index=-1
index=0

while (( index < ${#argv[@]} )); do
	arg="${argv[index]}"
	case "$arg" in
		-C|--git-dir|--work-tree|--namespace|--super-prefix|-c|--config-env)
			if (( index + 1 >= ${#argv[@]} )); then
				break
			fi
			prefix+=("$arg" "${argv[index + 1]}")
			((index += 2))
			;;
		--exec-path=*|--git-dir=*|--work-tree=*|--namespace=*|--super-prefix=*|--config-env=*|-c*)
			prefix+=("$arg")
			((index += 1))
			;;
		--literal-pathspecs|--no-literal-pathspecs|--glob-pathspecs|--noglob-pathspecs|--icase-pathspecs|--no-pager|--paginate|--no-optional-locks|--no-replace-objects|--bare)
			prefix+=("$arg")
			((index += 1))
			;;
		--)
			break
			;;
		-*)
			prefix+=("$arg")
			((index += 1))
			;;
		*)
			subcommand="$arg"
			subcommand_index=$index
			break
			;;
	esac
done

if [[ "$subcommand" == "commit" ]]; then
	commit_args=("${argv[@]:subcommand_index + 1}")
	if ! has_commit_signing_flag "${commit_args[@]}"; then
		exec "$REAL_GIT_BIN" "${prefix[@]}" commit -S "${commit_args[@]}"
	fi
fi

exec "$REAL_GIT_BIN" "$@"
