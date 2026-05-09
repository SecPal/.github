#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
#
# commit-msg hook: strip Co-authored-by trailers added by AI coding agents.
#
# Install as .git/hooks/commit-msg (executable) or symlink to this file.
# Polyscope provisioning installs it automatically in every managed worktree.
#
# Patterns stripped (case-insensitive match on the email address or username):
#   Co-authored-by: Cursor …<cursoragent@cursor.com>
#   Co-authored-by: Cursor Agent …<cursoragent@cursor.com>
#   Co-authored-by: GitHub Copilot <…@github.com>          (copilot bot accounts)
#   Co-authored-by: copilot-pull-request-reviewer[bot] …
#
# Human co-authors and dependabot are intentionally NOT stripped.

set -euo pipefail

COMMIT_MSG_FILE="${1:?commit-msg hook requires the commit message file path}"

if [[ ! -f "$COMMIT_MSG_FILE" ]]; then
    echo "strip-ai-trailers: commit message file not found: $COMMIT_MSG_FILE" >&2
    exit 1
fi

# Build a sed expression that removes known AI co-authored-by trailer lines.
# Use ERE (-E) for readability; match the full line including line-ending.
AI_PATTERN='Co-[Aa]uthored-[Bb]y:[[:space:]]*(Cursor[^<]*<cursoragent@cursor\.com>|[Cc]ursor[[:space:]]+[Aa]gent[^<]*<[^>]*>|GitHub[[:space:]]+Copilot[^<]*<[^>]*@github\.com>|copilot-pull-request-reviewer(\[bot\])?[^<]*<[^>]*>)'

# Write the filtered content back to the file in-place.
# Use a temp file to avoid clobbering the original on sed failure.
tmp_file="$(mktemp "${TMPDIR:-/tmp}/strip-ai-trailers.XXXXXX")"
trap 'rm -f "$tmp_file" "${tmp_file}.2"' EXIT

sed -E "/$AI_PATTERN/d" "$COMMIT_MSG_FILE" > "$tmp_file"

# Trim only trailing blank lines left behind after stripping trailers.
# Buffer all lines, then print up to and including the last non-blank line.
# This preserves intentional blank lines within the commit message body.
awk '{ lines[NR] = $0 }
END {
    last = NR
    while (last > 0 && lines[last] ~ /^[[:space:]]*$/) last--
    for (i = 1; i <= last; i++) print lines[i]
}' "$tmp_file" > "${tmp_file}.2" && mv "${tmp_file}.2" "$tmp_file"

mv "$tmp_file" "$COMMIT_MSG_FILE"
