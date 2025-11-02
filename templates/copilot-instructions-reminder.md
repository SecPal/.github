<!--
SPDX-FileCopyrightText: 2025 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Copilot Instructions Reminder Template

**Purpose:** Standardized reminder block for all SecPal repository-specific `copilot-instructions.md` files.

**Usage:** Copy this block to the top of `.github/copilot-instructions.md` in each repository (after SPDX headers, before content).

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

## Integration Checklist

When adding this reminder to a new or existing repository:

- [ ] Place reminder block **after** SPDX headers
- [ ] Place reminder block **before** repository-specific content
- [ ] Verify absolute GitHub URL is correct
- [ ] Ensure visual box formatting is preserved (UTF-8 box-drawing characters)
- [ ] Test that Copilot can read the instructions in the repo
- [ ] Create PR with title pattern: `docs: add org-wide instructions reminder`

---

## Validation

This reminder is **required** in all SecPal repositories. The validation script checks for presence of the marker text:

```bash
grep -q "🚨 AI MUST READ ORGANIZATION-WIDE INSTRUCTIONS FIRST" .github/copilot-instructions.md
```

See: `.github/workflows/validate-copilot-instructions.yml`

---

## Rationale

**Problem:** AI assistants might read repo-specific instructions without seeing critical org-wide policies, leading to:

- Quality gate bypasses
- Missing Copilot PR reviews
- TDD policy violations
- Security requirement oversights

**Solution:** Visual reminder block ensures AI **always** reads organization-wide instructions first, before processing repo-specific rules.

**Design Choices:**

1. **Visual Box:** High prominence, impossible to miss in file preview
2. **Absolute URL:** Clear, unambiguous path (no relative path confusion)
3. **Emoji Markers:** Searchable, distinct, attention-grabbing
4. **Critical Topics List:** Summary of what AI will miss without reading parent instructions

---

## Related

- **Organization-wide Instructions:** `.github/copilot-instructions.md`
- **Validation Workflow:** `.github/workflows/validate-copilot-instructions.yml`
- **Example Implementations:**
  - `SecPal/api` - [PR #76](https://github.com/SecPal/api/pull/76)
  - `SecPal/frontend` - [PR #54](https://github.com/SecPal/frontend/pull/54)
  - `SecPal/contracts` - [PR #38](https://github.com/SecPal/contracts/pull/38)

---

## License

Template content is CC0-1.0 (Public Domain) - copy freely without attribution.
