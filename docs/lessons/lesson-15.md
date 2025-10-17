<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Lesson #15 (Configuration Centralization)

**Category:** Meta-Lessons
**Priority:** HIGH
**Status:** ✅ Implemented
**Date:** 2025-10-14
**Repository:** .github

## Problem

License policies hardcoded in workflow files → difficult maintenance, inconsistencies, changes require editing multiple files.

## Solution

Create centralized configuration files:

```json
// .license-policy.json
{
  "allowedLicenses": ["MIT", "Apache-2.0", "BSD-2-Clause", ...],
  "deniedLicenses": ["GPL-2.0", "LGPL-2.0", ...],
  "description": "License policy for AGPL-3.0-or-later compatibility"
}
```

Load in workflows:

```yaml
- name: Load license policy
  run: |
    set -euo pipefail
    ALLOWED=$(jq -r '.allowedLicenses | join(";")' .license-policy.json)
    echo "allowed=$ALLOWED" >> $GITHUB_OUTPUT
```

## Action for Future Repos

1. Extract hardcoded configuration → centralized files
2. Review ALL code review comments (including "nitpicks")
3. Use REUSE.toml for licensing JSON files
4. Always format config files with prettier

## Related Lessons

- [Lesson #16 (Review Comment Discipline)](lesson-16.md)
- [Lesson #8 (REUSE.toml Needs Headers)](lesson-08.md)

---

**Last Updated:** 2025-10-17
