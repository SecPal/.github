<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Lesson #4 (Dependabot PRs Failed Signed Commits Check)

**Category:** Critical Issues
**Priority:** HIGH
**Status:** ✅ Fixed
**Date:** 2025-10-11
**Repository:** contracts

## Problem

Signed commits check failed on all Dependabot PRs because bot commits are not GPG-signed.

## Solution

Skip signature verification for Dependabot:

```yaml
- name: Verify all commits are signed
  run: |
    set -euo pipefail

    # Skip verification for Dependabot PRs
    if [[ "${{ github.actor }}" == "dependabot[bot]" ]]; then
      echo "✅ Skipping signature verification for Dependabot"
      exit 0
    fi

    # ... rest of verification for human commits
```

## Action for Future Repos

Add Dependabot skip logic to `signed-commits.yml` template.

## Related Lessons

- [Lesson #2 (Signed Commits: GitHub API)](lesson-02.md)
- [Lesson #5 (Dependabot PRs Failed Dependency Review)](lesson-05.md)
- [Lesson #19 (Infinite Loop Prevention)](lesson-19.md) - Similar actor filtering

---

**Last Updated:** 2025-10-17
