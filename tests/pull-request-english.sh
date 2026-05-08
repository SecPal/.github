#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VALIDATOR="$REPO_ROOT/scripts/validate-pull-request-english.sh"
WORKFLOW="$REPO_ROOT/.github/workflows/pull-request-english.yml"
TEMPLATE="$REPO_ROOT/.github/pull_request_template.md"
QUICK_REFERENCE="$REPO_ROOT/docs/workflows/QUICK_REFERENCE.md"

if [ ! -f "$VALIDATOR" ]; then
  echo "Expected validator script was not found: $VALIDATOR" >&2
  exit 1
fi

if [ ! -f "$WORKFLOW" ]; then
  echo "Expected workflow was not found: $WORKFLOW" >&2
  exit 1
fi

if [ ! -f "$TEMPLATE" ]; then
  echo "Expected PR template was not found: $TEMPLATE" >&2
  exit 1
fi

if [ ! -f "$QUICK_REFERENCE" ]; then
  echo "Expected quick reference doc was not found: $QUICK_REFERENCE" >&2
  exit 1
fi

if ! grep -Fq 'GitHub-facing communication in pull request titles and bodies must be in English.' "$TEMPLATE"; then
  echo "PR template must remind authors that pull request titles and bodies must be in English." >&2
  exit 1
fi

if ! grep -Fq 'scripts/validate-pull-request-english.sh' "$WORKFLOW"; then
  echo "Workflow does not invoke the pull-request English validator script." >&2
  exit 1
fi

if ! grep -Fq 'github.event.pull_request.title' "$WORKFLOW"; then
  echo "Workflow does not pass the pull request title into the validator." >&2
  exit 1
fi

if ! grep -Fq 'github.event.pull_request.body' "$WORKFLOW"; then
  echo "Workflow does not pass the pull request body into the validator." >&2
  exit 1
fi

if ! grep -Fq 'edited' "$WORKFLOW"; then
  echo "Workflow must rerun when the pull request title or body is edited." >&2
  exit 1
fi

if ! grep -Fq 'CI blocks obvious German PR title/body markers.' "$QUICK_REFERENCE"; then
  echo "Quick reference must document that obvious German PR title/body markers are CI-blocked." >&2
  exit 1
fi

if ! grep -Fq 'Comments and review text remain reviewer-enforced for now.' "$QUICK_REFERENCE"; then
  echo "Quick reference must document that comments and review text remain reviewer-enforced." >&2
  exit 1
fi

english_title='feat(governance): align onboarding attachment copy'
english_body="$(cat <<'EOF'
## Description

Clarify the onboarding copy and keep BewachV, GewO, and Steuer-ID terminology unchanged where the domain requires it.

Made with [Cursor](https://cursor.com)

<!-- CURSOR_SUMMARY -->
## Zusammenfassung

- Deutsche Marker inside the generated summary must not affect the author-facing PR language check.
<!-- /CURSOR_SUMMARY -->
EOF
)"

if ! PR_TITLE="$english_title" PR_BODY="$english_body" bash "$VALIDATOR" >/tmp/pull-request-english-positive.log 2>&1; then
  cat /tmp/pull-request-english-positive.log >&2
  echo "Validator rejected an English PR title/body that only contains German markers inside an ignored generated summary block." >&2
  exit 1
fi

german_title='feat: [US-009] Einladung und Wizard-Inhalte abgleichen'
german_body="$(cat <<'EOF'
## US-009: Einladung und Wizard-Inhalte abgleichen

- Einladungs-E-Mail listet nur noch unterstützte Schritte: persönliche Pflichtangaben, optionale Abschnitte sowie Belege pro Schritt.

**Weitere Repos:** Branch `onboarding-review-stories` (**frontend**), `onboarding-review-stories-link-3` (**api**).
EOF
)"

if PR_TITLE="$german_title" PR_BODY="$german_body" bash "$VALIDATOR" >/tmp/pull-request-english-negative.log 2>&1; then
  echo "Validator unexpectedly accepted an obviously German pull request title/body." >&2
  exit 1
fi

if ! grep -Fq 'PR title/body must be in English.' /tmp/pull-request-english-negative.log; then
  cat /tmp/pull-request-english-negative.log >&2
  echo "Validator did not explain the non-English failure." >&2
  exit 1
fi

if ! grep -Fq 'einladung' /tmp/pull-request-english-negative.log; then
  cat /tmp/pull-request-english-negative.log >&2
  echo "Validator did not report the detected German markers." >&2
  exit 1
fi
