<!--
SPDX-FileCopyrightText: 2025 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Copilot Compatibility Reminder Template

**Purpose:** Historical reminder block for repositories that still maintain a human-written `.github/copilot-instructions.md` compatibility file.

**Status:** `AGENTS.md` is now the authoritative runtime baseline. Prefer updating `AGENTS.md` and keeping `.github/copilot-instructions.md` as a compatibility mirror instead of copying this block into new repositories.

---

## Template Block

```html
<!--
╔════════════════════════════════════════════════════════════════╗
║  🚨 AI MUST READ ORGANIZATION-WIDE INSTRUCTIONS FIRST 🚨       ║
╠════════════════════════════════════════════════════════════════╣
║  Location: https://github.com/SecPal/.github/blob/main/.github/copilot-instructions.md ║
║                                                                ║
║  Critical Topics Defined There:                                ║
║  - 🛡️ Copilot Review Protocol (ALWAYS request after PR)       ║
║  - 🧪 Quality Gates (NEVER bypass)                            ║
║  - 📝 TDD Policy (Write tests FIRST)                          ║
║  - 🔐 Security Requirements                                    ║
║                                                                ║
║  ⚠️ This file contains REPO-SPECIFIC rules only               ║
╚════════════════════════════════════════════════════════════════╝
-->
```

---

## Compatibility Checklist

When adding this reminder to a new or existing repository:

- [ ] Place reminder block **after** SPDX headers
- [ ] Place reminder block **before** repository-specific content
- [ ] Verify absolute GitHub URL is correct
- [ ] Ensure visual box formatting is preserved (UTF-8 box-drawing characters)
- [ ] Test that Copilot can read the instructions in the repo
- [ ] Create PR with title pattern: `docs: add org-wide instructions reminder`

---

## Validation

This reminder is no longer required for all SecPal repositories. Current validation focuses on `AGENTS.md` as the authoritative baseline plus a valid `.github/copilot-instructions.md` mirror when present.

```bash
grep -q "🚨 AI MUST READ ORGANIZATION-WIDE INSTRUCTIONS FIRST" .github/copilot-instructions.md
```

See: `.github/workflows/validate-ai-instructions.yml`

---

## Rationale

**Historical problem:** AI assistants could read repo-specific instructions without seeing critical org-wide policies, leading to:

- Quality gate bypasses
- Missing Copilot PR reviews
- TDD policy violations
- Security requirement oversights

**Current solution:** Use `AGENTS.md` as the primary runtime surface. Keep this reminder only where a manual Copilot compatibility file still benefits from it.

**Design Choices:**

1. **Visual Box:** High prominence, impossible to miss in file preview
2. **Absolute URL:** Clear, unambiguous path (no relative path confusion)
3. **Emoji Markers:** Searchable, distinct, attention-grabbing
4. **Critical Topics List:** Summary of what AI will miss without reading parent instructions

---

## Related

- **Authoritative Runtime Baseline:** `AGENTS.md`
- **Copilot Compatibility Mirror:** `.github/copilot-instructions.md`
- **Validation Workflow:** `.github/workflows/validate-ai-instructions.yml`
- **Example Implementations:**
  - `SecPal/api` - [PR #76](https://github.com/SecPal/api/pull/76)
  - `SecPal/frontend` - [PR #54](https://github.com/SecPal/frontend/pull/54)
  - `SecPal/contracts` - [PR #38](https://github.com/SecPal/contracts/pull/38)

---

## License

Template content is CC0-1.0 (Public Domain) - copy freely without attribution.
