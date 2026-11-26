#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
set -euo pipefail

repo=SecPal/.github
tag=${1:-}
sha=${2:-}
notes=${3:-}
version_pattern='^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$'

if [[ $# != 3 || ! "$tag" =~ $version_pattern || ! "$sha" =~ ^[a-f0-9]{40}$ || ! -s "$notes" ]]; then
  echo "Usage: $0 VERSION FULL_MERGE_SHA NOTES_FILE" >&2
  exit 2
fi

gh api "user/memberships/orgs/SecPal" --jq '.role == "admin" and .state == "active"' | grep -qx true
gh api "repos/$repo/immutable-releases" --jq '.enabled' | grep -qx true
main=$(gh api "repos/$repo/branches/main" --jq 'select(.protected).commit.sha')
[[ "$main" =~ ^[a-f0-9]{40}$ ]]
remote_main=$(git rev-parse FETCH_HEAD 2>/dev/null || true)
if [[ "$remote_main" != "$main" ]]; then
  git fetch --no-tags "https://github.com/$repo.git" main
fi
git merge-base --is-ancestor "$sha" "$main"

gh api "repos/$repo/commits/$sha" --jq '.commit.verification.verified' | grep -qx true
pr=$(gh api "repos/$repo/commits/$sha/pulls" --jq ".[] | select(.base.ref == \"main\" and .merged_at and .merge_commit_sha == \"$sha\") | .number")
[[ "$pr" =~ ^[1-9][0-9]*$ ]]
gh pr checks -R "$repo" --required "$pr"

latest=$(gh api "repos/$repo/releases/latest")
previous=$(jq -er 'select(.immutable and (.draft | not) and (.prerelease | not)).tag_name' <<< "$latest")
base=$(jq -er '.target_commitish' <<< "$latest")
[[ "$previous" =~ $version_pattern && "$base" =~ ^[a-f0-9]{40}$ ]]
[[ "$tag" != "$previous" && "$(printf '%s\n' "$previous" "$tag" | sort -V | tail -1)" == "$tag" ]]
[[ "$(gh api "repos/$repo/git/ref/tags/$previous" --jq '.object | select(.type == "commit").sha')" == "$base" ]]
gh release verify "$previous" -R "$repo"
[[ "$base" != "$sha" ]]
git merge-base --is-ancestor "$base" "$sha"

# Shared execution roots and their bound files. Local callers are outside
# this scope so their pin refreshes cannot trigger a release.
changes=$(git diff --name-only "$base" "$sha" -- \
  ':(glob).github/workflows/reusable-*.yml' .github/actions/trivy-repository-scan/ \
  .npmrc npm-shrinkwrap.json package.json package-lock.json requirements/requirements.txt \
  scripts/validate-ai-instructions.sh scripts/secpal-dependabot-manifest-coverage.mjs \
  scripts/secpal-trivy-repository-scan.py scripts/secpal-vulnerability-policy.py \
  scripts/secpal-vulnerability-reevaluation.py \
  policies/dependabot-manifest-catalog-v1.json policies/vulnerability-triage-v1.json \
  ':(glob)policies/trivy-repository-*.yaml' policies/trivy-repository-scan-v1.json \
  docs/schemas/openvex-0.2.0.schema.json ':(glob)docs/schemas/secpal-vulnerability-*.schema.json')
if [[ -z "$changes" ]]; then
  echo "No shared component closure changed since $previous." >&2
  exit 1
fi
printf '%s\n' "$changes"

existing=$(gh api "repos/$repo/git/matching-refs/tags/$tag" --jq ".[] | select(.ref == \"refs/tags/$tag\") | .ref")
if [[ -n "$existing" ]]; then
  echo "Ref $existing already exists. Publish with a new version tag." >&2
  exit 1
fi

gh release create "$tag" -R "$repo" --target "$sha" --latest \
  --title "SecPal shared components $tag" --notes-file "$notes"
gh api "repos/$repo/releases/tags/$tag" --jq ".immutable and .target_commitish == \"$sha\"" | grep -qx true
[[ "$(gh api "repos/$repo/git/ref/tags/$tag" --jq '.object | select(.type == "commit").sha')" == "$sha" ]]
# An immutable release can be visible before its attestation is available.
for attempt in 1 2 3 4 5; do
  if gh release verify "$tag" -R "$repo"; then
    exit 0
  fi
  if [[ "$attempt" != 5 ]]; then
    sleep 5
  fi
done
echo "Release $tag is public. Recheck its attestation before adopting it." >&2
exit 1
