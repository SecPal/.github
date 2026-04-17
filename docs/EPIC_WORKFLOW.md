<!-- SPDX-FileCopyrightText: 2026 SecPal -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# Epic And Sub-Issue Workflow

## Why This Exists

Large SecPal work often spans multiple repositories, multiple PRs, or both. When that happens, a parent epic can look complete before all acceptance criteria are actually satisfied.

This guide defines the minimum structure and closure evidence required so an epic reflects reality instead of just merged PR count.

## When To Use An Epic

Create an epic before implementation when work:

- needs more than one PR or probably will
- spans multiple repositories
- has distinct implementation phases or milestones
- cannot be reviewed safely as one topic-sized change

For single-PR work, use a regular issue instead.

## Required Structure

### 1. Create The Parent Epic First

Use the organization issue template: `🗺️ Epic (Multi-PR Feature)`.

The epic must define:

- a clear goal
- acceptance criteria
- non-goals
- a sub-issue work plan

### 2. Split Work Into Sub-Issues

Use one sub-issue per PR-sized slice of work.

Each sub-issue must:

- link back to the parent epic
- stay focused on one logical change
- carry its own acceptance criteria
- note dependencies when order matters

### 3. Link PRs To Sub-Issues, Not The Epic

Every PR should close its sub-issue, not the parent epic.

Use:

```markdown
Fixes #<sub-issue-number>
Part of: #<epic-number>
```

Only the final PR may close the epic, and only when the epic closure checklist below is satisfied.

## Parent Epic Closure Checklist

Do not close a parent epic until all of the following are true:

- every linked acceptance criterion is satisfied by merged work, not just planned work
- the exact child issues and PRs that satisfy each acceptance slice are identified
- any discovered acceptance gap was reopened or re-filed before closure
- deferred but still relevant work was linked as dedicated follow-up issues before closure
- the sub-issue tasklist reflects reality across all touched repositories

If any item above is still unclear, the epic stays open.

## Cross-Repo Verification

Before closing a cross-repository epic, review the linked work repo by repo.

For each repository involved:

- identify the merged PRs that delivered the intended scope
- verify the corresponding sub-issues are actually closed or explicitly superseded
- check whether any promised acceptance slice was only partially implemented
- check whether follow-up issues were created for deferred scope discovered during delivery

This verification is required even if project board automation already moved issues to a done-like state.

## Required Closure Comment

When an epic is closed, add a closure comment that maps acceptance criteria to the exact child issues and PRs.

Use this structure:

```markdown
## Epic Closure Evidence

### Acceptance Criteria Mapping

- Criterion: <acceptance slice>
  Delivered by: <child issue>, <PR>, <repo>
- Criterion: <acceptance slice>
  Delivered by: <child issue>, <PR>, <repo>

### Deferred Follow-Up

- <issue link> — <why it remains out of scope>

### Notes

- <optional clarification about superseded or reopened work>
```

The comment should make it possible to audit why the epic was closed without reconstructing the full history from scratch.

## What To Do When You Find A Gap Late

If epic closure review finds that something was assumed complete but is not actually complete:

1. Reopen the relevant issue if the original scope still applies.
2. Create a new follow-up issue if the remaining work is distinct.
3. Link that issue from the parent epic before closing it.
4. Keep the epic open until the remaining scope is either done or explicitly tracked as deferred.

Do not close the epic first and clean up the tracking later.

## Retrospective Audit Helper

When you need to verify already-closed epics, use the audit helper in this
repository:

```bash
bash scripts/audit-closed-epics.sh
```

You can scope it to specific repositories when investigating a narrower set of
epics:

```bash
bash scripts/audit-closed-epics.sh --org SecPal --repo .github --repo api
```

This catches stale checklist state, open child issues, and checked items that do
not resolve to closed issues. It also catches open epics whose child issues are
already closed but whose checklist was never updated, so closure-ready epics do
not silently drift.

## CLA And Other External Services

If a workflow depends on repository settings or external services, merged code alone is not enough evidence. Verify the live configuration separately and track any missing operational step as its own issue.

## Quick Reference

- Each PR closes one sub-issue.
- The parent epic stays open until closure evidence exists.
- Cross-repo acceptance checks must happen before epic closure.
- Deferred work must be linked before, not after, closure.

## Related Guidance

- [README.md](../README.md)
- [CONTRIBUTING.md](../CONTRIBUTING.md)
- [.github/ISSUE_TEMPLATE/epic.yml](../.github/ISSUE_TEMPLATE/epic.yml)
- [.github/ISSUE_TEMPLATE/sub-issue.yml](../.github/ISSUE_TEMPLATE/sub-issue.yml)
