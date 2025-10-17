<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Lesson #5 (Dependabot PRs Failed Dependency Review for GitHub Actions Updates)

**Category:** Critical Issues
**Priority:** HIGH
**Status:** ✅ Fixed
**Date:** 2025-10-11
**Repository:** contracts

## Problem

Dependabot PRs updating only GitHub Actions workflow files triggered dependency review, which failed because Actions aren't npm dependencies.

## Solution

Skip dependency review when PR only changes workflow files:

```yaml
- name: Check if GitHub Actions only changes
  id: check-files
  run: |
    set -euo pipefail

    files=$(gh pr view ${{ github.event.pull_request.number }} --json files -q '.files[].path')
    all_workflows=true

    while IFS= read -r file; do
      if [[ ! "$file" =~ ^\.github/workflows/ ]]; then
        all_workflows=false
        break
      fi
    done <<< "$files"

    echo "all_workflows=$all_workflows" >> $GITHUB_OUTPUT
  env:
    GH_TOKEN: ${{ github.token }}

- name: Dependency Review
  if: steps.check-files.outputs.all_workflows != 'true' || github.actor != 'dependabot[bot]'
  uses: actions/dependency-review-action@v4
```

## Action for Future Repos

Update `dependency-review.yml` template with file-checking logic.

## Related Lessons

- [Lesson #3 (Dependency Review: Invalid License)](lesson-03.md)
- [Lesson #4 (Dependabot PRs Failed Signed Commits)](lesson-04.md)

---

**Last Updated:** 2025-10-17
