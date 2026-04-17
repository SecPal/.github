<!-- SPDX-FileCopyrightText: 2025-2026 SecPal -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# Quick Reference: Project Automation

Quick reference card for daily usage of the optional GitHub Project Board mirror for SecPal.

Issues, milestones, and linked PRs remain the source of truth. The project board is an optional mirrored view.

## 🎯 Status at a Glance

| Status             | When             | How                            |
| ------------------ | ---------------- | ------------------------------ |
| 💡 **Ideas**       | New ideas        | Label: `enhancement`           |
| 💬 **Discussion**  | Needs discussion | Reopen issue                   |
| 📥 **Backlog**     | High priority    | Label: `priority: blocker`     |
| 📋 **Planned**     | Scheduled work   | Label: `core-feature`          |
| 🚧 **In Progress** | Working on it    | Create/convert to draft PR     |
| 👀 **In Review**   | Ready for review | Mark PR ready                  |
| ✅ **Done**        | Completed        | Merge PR or close as completed |
| 🚫 **Won't Do**    | Not implementing | Close as not planned           |

## 🔄 Common Workflows

### Create New Issue

```bash
# Enhancement (goes to Ideas)
gh issue create \
  --title "Add feature X" \
  --label "enhancement" \
  --body "Description..."

# Core feature (goes to Planned)
gh issue create \
  --title "Implement Y" \
  --label "core-feature" \
  --body "Description..."

# Blocker (goes to Backlog)
gh issue create \
  --title "Fix critical bug" \
  --label "priority: blocker" \
  --body "Description..."
```

### Draft PR Workflow (Recommended)

```bash
# 1. Create draft PR (→ In Progress)
gh pr create --draft \
  --title "WIP: Feature X" \
  --body "Closes #123"

# 2. Mark ready (→ In Review)
gh pr ready 456

# 3. Need changes? (→ In Progress)
gh pr ready --undo 456

# 4. Ready again (→ In Review)
gh pr ready 456

# 5. Merge (→ Done, closes issue)
gh pr merge 456 --squash
```

### Close Issue

```bash
# Completed (→ Done)
gh issue close 123 --reason "completed"

# Not planned (→ Won't Do)
gh issue close 123 --reason "not planned"
```

### Reopen Issue

```bash
# Reopened (→ Discussion)
gh issue reopen 123
```

## 📝 PR Body Template

Always link issues in PR description:

```markdown
## Description

Brief description of changes

## Related Issues

Closes #123
Fixes #456
Resolves #789

## Testing

- [ ] Unit tests added
- [ ] Manual testing done

## Checklist

- [ ] Code follows style guide
- [ ] Documentation updated
```

## 🏷️ Label Reference

| Label               | Status     | Use Case                   |
| ------------------- | ---------- | -------------------------- |
| `enhancement`       | 💡 Ideas   | New features, improvements |
| `core-feature`      | 📋 Planned | Core functionality         |
| `priority: blocker` | 📥 Backlog | Blocking issues            |

The setup script also creates: `status: discussion|BFD4F2|Needs decision before implementation`.

## 🔍 Check Status

### Via GitHub UI

If the project board is enabled:

1. Go to [SecPal Roadmap](https://github.com/orgs/SecPal/projects/1)
2. Find your issue/PR
3. Check status column

### Via CLI

```bash
# View issue with project status
gh issue view 123 --json projectItems \
  --jq '.projectItems[0].status.name'

# View PR with linked issues
gh pr view 456 --json body
```

## 🐛 Troubleshooting Quick Fixes

### Issue not in project

```bash
# Check workflow run
gh run list --workflow "Project Board Automation" --limit 5

# View latest run logs
gh run view --log
```

### Status not updating

1. Check issue has correct label
2. Check PR body has `Closes #N`
3. Wait 15-30 seconds for workflow
4. Check Actions tab for errors

### Reset status manually

1. Go to project board
2. Drag issue to correct column
3. Or edit issue status field directly

Use manual board edits only to correct the mirror after checking the underlying issue or PR state first.

## ⚡ Power User Tips

### Batch Create Issues

```bash
# Create multiple related issues
for feature in "Login" "Signup" "Logout"; do
  gh issue create \
    --label "core-feature" \
    --title "Implement $feature" \
    --body "Part of authentication system"
done
```

### Check All Open PRs

```bash
# List PRs with their status
gh pr list --json number,title,isDraft,state \
  --jq '.[] | "\(.number): \(.title) (Draft: \(.isDraft))"'
```

### Find Stale Issues

```bash
# Issues in Discussion > 30 days
gh issue list --state open --label "discussion" \
  --json number,title,updatedAt \
  --jq '.[] | select((.updatedAt | fromdateiso8601) < (now - 2592000))'
```

## 📊 Status Transitions

```
Enhancement → 💡 Ideas
           ↓ (discuss)
         💬 Discussion
           ↓ (plan)
         📋 Planned
           ↓ (start draft PR)
         🚧 In Progress
           ↓ (mark ready)
         👀 In Review
           ↓ (merge)
         ✅ Done

High Priority → 📥 Backlog → 📋 Planned → ...

Reopen → 💬 Discussion
Close (not planned) → 🚫 Won't Do
```

## 🎯 Single Maintainer Flow

When working alone:

```bash
# 1. Create issue
gh issue create --label "core-feature" --title "..."

# 2. Start work (draft PR)
gh pr create --draft --body "Closes #123"
# → Issue: 🚧 In Progress

# 3. Self-review ready
gh pr ready <PR>
# → Issue: 👀 In Review

# 4. Copilot found issues?
gh pr ready --undo <PR>
# → Issue: 🚧 In Progress (signals: "fixing issues")

# 5. Fixed and ready
gh pr ready <PR>
# → Issue: 👀 In Review

# 6. Merge
gh pr merge <PR> --squash
# → Issue: ✅ Done (auto-closed)
```

## 📱 Shortcuts

```bash
# Create enhancement issue
alias gh-idea='gh issue create --label "enhancement"'

# Create core feature issue
alias gh-feature='gh issue create --label "core-feature"'

# Create blocker issue
alias gh-blocker='gh issue create --label "priority: blocker"'

# Create draft PR
alias gh-draft='gh pr create --draft'

# Mark PR ready
alias gh-ready='gh pr ready'

# Convert to draft
alias gh-wip='gh pr ready --undo'
```

Add to your `.zshrc` or `.bashrc`.

## 🔗 Quick Links

- [Full Documentation](./PROJECT_AUTOMATION.md)
- [Rollout Guide](./ROLLOUT_GUIDE.md)
- [SecPal Roadmap](https://github.com/orgs/SecPal/projects/1)
