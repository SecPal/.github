<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Lesson #0 (Start Here - Essential Rules for AI Assistants)

**Category:** Meta-Lessons / Onboarding
**Priority:** CRITICAL
**Status:** ✅ Implemented
**Date:** 2025-10-18
**Repository:** .github

## Purpose

This lesson provides the **fundamental rules** that AI assistants must follow when working in SecPal repositories. Read this FIRST before making any changes.

## Critical Rules

### 1. Quality First - Think Before You Act

**Rule:** Systematic review BEFORE commit. Never rush. Verify facts, don't blindly accept suggestions.

**What This Means:**

- **Before every commit**: Review ALL changes comprehensively
- **Before accepting review comments**: Verify against actual code/implementation
- **Before declaring "ready"**: Check everything systematically
- **Never blindly accept**: Not from Copilot, not from any source - verify first!

**Example from This Session:**

```
❌ WRONG: Copilot says "keep private: true" → Accept without checking
✅ CORRECT: Copilot says "keep private: true" → Check package.json → See private: false → Recognize contradiction
```

**Why:**

- Prevents introducing errors while fixing other issues
- Catches contradictions between suggestions and reality
- Ensures documentation matches implementation
- Single most important rule - enables all others

**Target:** Max 3 review cycles per PR. Ideal: 1 cycle, 0 comments.

**Related:** [Lesson #25](lesson-25.md)

### 2. Branch Protection - NEVER Push to Main Directly

**Rule:** ALL changes must go through pull requests. Main branch is protected.

**What This Means:**

```bash
# ❌ WRONG - Will be rejected by branch protection
git checkout main
git commit -m "fix: something"
git push origin main  # ERROR: Protected branch hook declined

# ✅ CORRECT - Always use feature branches
git checkout -b feature/my-change
git commit -m "fix: something"
git push origin feature/my-change
gh pr create --base main
```

**Why:**

- `enforce_admins: true` - Even admins must follow rules
- Required status checks must pass
- Linear history enforcement
- Signed commits required

**Related:** [Lesson #1](lesson-01.md), [Lesson #6](lesson-06.md), [Lesson #13](lesson-13.md)

### 3. Pre-commit Hook - Prettier Runs Automatically

**Rule:** Pre-commit hook runs Prettier automatically. If files are formatted, you must re-stage them.

**What This Means:**

```bash
# Step 1: Stage your changes
git add file.md

# Step 2: Commit (hook runs Prettier automatically)
git commit -m "docs: update"

# Step 3: If hook reports "unstaged changes"
# This means Prettier formatted files
git status  # See what changed
git add -A  # Re-stage formatted files
git commit -m "docs: update"  # Commit again
```

**Common Error Pattern:**

```
🎨 Checking code formatting (Prettier)...
Checking formatting...
All matched files use Prettier code style!
✅ All files properly formatted

🔎 Checking for unstaged changes (formatter detection)...
⚠️  WARNING: Unstaged changes detected!
Modified files:
  docs/lessons/lesson-29.md
❌ Blocking commit to prevent inconsistent state
```

**Fix:** `git add -A && git commit`

**Manual Formatting (when needed):**

```bash
# Check formatting before commit
npm run format:check

# Fix formatting issues
npm run format

# Then commit
git add -A
git commit -m "style: apply formatting"
```

**Why This Exists:**

- Ensures committed code is properly formatted
- Prevents CI failures due to formatting issues
- Catches formatter-modified files (Lesson #17)
- Pre-commit hook runs `npm run format:check` automatically

**Related:** [Lesson #17](lesson-17.md), [Lesson #11](lesson-11.md)

### 4. Lesson Writing - No User Quotes

**Rule:** Document processes and solutions, not conversation history or user feedback.

**What This Means:**

```markdown
# ❌ WRONG - Contains user quote

**User immediately stopped: "Stop ... Wir erlauben kein UNLICENSED!"**

# ✅ CORRECT - Documents the decision

Proposal rejected due to security implications. UNLICENSED would allow
proprietary dependencies, compromising open source compliance.
```

**Guidelines:**

- ✅ Use English for all lessons
- ✅ Focus on reusable patterns
- ✅ Make lessons self-contained
- ✅ Document WHY, not just WHAT
- ❌ No direct user quotes
- ❌ No conversation history

**Why:**

- Lessons are documentation, not meeting notes
- Focus on teaching patterns, not recording events
- Should be understandable without context

**Related:** [README.md Writing Guidelines](README.md#writing-guidelines), [Lesson #25](lesson-25.md)

### 5. License Policy - Never Modify Without Approval

**Rule:** `.license-policy.json` is a security boundary. Never modify without explicit user approval.

**What This Means:**

```bash
# ❌ WRONG - Modifying policy to "fix" a check
# License check failed, let me add this license...
{
  "allowedLicenses": [..., "UNLICENSED"]
}

# ✅ CORRECT - Analyze root cause, propose options
# The check is failing because X.
# Three options:
# 1. Exclude root package (technical fix)
# 2. Change package.json private setting
# 3. Add license to policy (requires approval)
# Which approach do you prefer?
```

**Why:**

- License policy defines legal boundaries
- Wrong decision = legal liability
- User must understand implications
- May require legal review

**Related:** [Lesson #29](lesson-29.md)

### 6. Admin Override - Only for Bootstrap Paradoxes

**Rule:** Use `--admin` flag ONLY for bootstrap paradoxes (Lesson #22). Never to bypass failing checks.

**Valid Use Case (Lesson #22):**

- Fix is IN the PR branch
- Workflow runs with `@main` (doesn't have fix yet)
- Check fails because fix isn't in main yet
- Can't merge because check fails
- **This is a bootstrap paradox** → `--admin` is appropriate

**Invalid Use Cases:**

- ❌ "Check is taking too long, let me bypass it"
- ❌ "I don't understand why it's failing, let me skip it"
- ❌ "Branch is out of date, let me force merge"

**Why:**

- Defeats the purpose of branch protection
- Nullifies all carefully configured safeguards
- Should trigger "what am I missing?" reflection

**Related:** [Lesson #6](lesson-06.md), [Lesson #13](lesson-13.md), [Lesson #22](lesson-22.md)

## Quick Reference Card

```
┌─────────────────────────────────────────────────────────────┐
│ CRITICAL RULES - AI Assistant Quick Reference              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ 1. QUALITY FIRST                                            │
│    ✓ Systematic review before commit                       │
│    ✗ Never blindly accept suggestions - verify first!      │
│                                                             │
│ 2. BRANCH PROTECTION                                        │
│    ✓ Always create PR branch                               │
│    ✗ Never push to main directly                           │
│                                                             │
│ 3. PRE-COMMIT HOOK                                          │
│    ✓ If "unstaged changes": git add -A && git commit       │
│    ✗ Don't use -n to skip hook (except when hanging)       │
│                                                             │
│ 4. LESSON WRITING                                           │
│    ✓ English, patterns, self-contained                     │
│    ✗ No user quotes, no conversation history               │
│                                                             │
│ 5. LICENSE POLICY                                           │
│    ✓ Ask before modifying .license-policy.json             │
│    ✗ Never modify to "fix" a check                         │
│                                                             │
│ 6. ADMIN OVERRIDE                                           │
│    ✓ Use for bootstrap paradoxes only                      │
│    ✗ Never use to bypass failing checks                    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## For New AI Assistants

**Before making ANY changes:**

1. ✅ Read this lesson (Lesson #0)
2. ✅ Check current branch: `git branch`
3. ✅ If on main: Create feature branch immediately
4. ✅ Review [copilot-instructions.md](../../copilot-instructions.md)
5. ✅ Skim [README.md](README.md) for lesson overview

**When in doubt:**

- Ask questions BEFORE taking action
- Propose multiple solutions, explain trade-offs
- Never assume you know what the user wants for security-critical changes

## Common Mistakes to Avoid

### Mistake 1: "I'll just quickly fix this on main"

**Why it fails:** Branch protection rejects the push
**Fix:** Always use feature branches

### Mistake 2: "Pre-commit hook failed, let me skip it with -n"

**Why it's wrong:** Hook catches real issues (formatting, REUSE compliance)
**Fix:** Read hook output, fix the issue, commit properly

### Mistake 3: "Let me document what the user said"

**Why it's wrong:** Lessons are patterns, not transcripts
**Fix:** Document the pattern, not the conversation

### Mistake 4: "Check is failing, I'll allow this license"

**Why it's dangerous:** License policy is a security boundary
**Fix:** Analyze root cause, propose options, get approval

### Mistake 5: "Check is failing, I'll use --admin"

**Why it's wrong:** Bypasses all protections without understanding
**Fix:** Understand WHY it's failing, fix root cause, use --admin only for bootstrap paradoxes

## Related Lessons

Critical lessons to understand:

- [Lesson #1 (Branch Protection: Check Names)](lesson-01.md)
- [Lesson #6 (Branch Protection: Admin Bypass)](lesson-06.md)
- [Lesson #13 (Never Use --admin for Normal Merges)](lesson-13.md)
- [Lesson #17 (Pre-commit Hooks)](lesson-17.md)
- [Lesson #22 (Bootstrap Paradox)](lesson-22.md)
- [Lesson #25 (Lesson Quality Standards)](lesson-25.md)
- [Lesson #29 (License Policy Security)](lesson-29.md)

## Updating This Lesson

This lesson should be updated when:

- New critical rules are established
- Existing rules change significantly
- Common mistakes emerge that need highlighting

Keep this lesson **concise** - it's an entry point, not comprehensive documentation.

---

**Last Updated:** 2025-10-18
**Status:** Living document - update as new patterns emerge
