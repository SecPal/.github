<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# SecPal Native WorkGraph Planning And GitHub Delivery

WorkGraph organizes issue-first work using GitHub's existing relationship storage.
GitHub PR checks validate code. Planning does not require a custom PR lifecycle.

This document normatively incorporates `docs/evidence-architecture-contract.md`
for evidence pipelines and external systems. That contract directly owns invariant
definitions, real-system evidence and costly-dispatch safety. Repository baselines
may reference it directly.

## 1. Source Of Truth

Native issue state, closure reason, parent/sub-issue links, dependencies and
sub-issue order are authoritative. Markdown lists and project views are useful
presentations; they must not replace or silently override native relationships.

Keep existing native relationships intact. Correct a relationship only when the
planning task authorizes that change. An unrelated PR, prompt or source change
does not invalidate a previously observed graph; a relevant relationship or issue
change does.

## 2. Work Structure

Use an epic and native sub-issues for larger or cross-repository work when useful.
A leaf has no children and describes focused work with acceptance criteria.
Parents coordinate their children. Neither structure requires one implementation
PR per issue, mandatory prerequisite issues or a receipt for closure.

Use normal issue descriptions for intended outcomes and scope. Project views,
milestones and labels help planning without becoming another relationship store.
Preserve security, privacy, licensing and accepted product architecture boundaries.

## 3. Relationships

### 3.1 Containment

Parent/sub-issue links express containment. They do not make a parent or sibling
a dependency. A standalone issue can have no parent; native links may cross
repositories.

### 3.2 Dependencies

`A blocked by B` records an actual technical, qualification or rollout dependency.
Do not create blockers merely for preferred order or review convenience.
Dependencies are explicit, not inherited from parents or children.

Before adding a blocker, confirm that the dependent task genuinely needs an
independently deliverable output that it cannot achieve within its current scope.
Reuse an existing owner; create a prerequisite issue only when none exists.
Ordinary CI delays, workflow problems, missing local evidence and implementation
difficulties do not by themselves justify prerequisite issues. Re-evaluate
dependencies when their underlying technical requirements change.

The existing resolver treats a target closed as `completed` as satisfied.
`not planned`, duplicate or other closure reasons do not establish delivery of
its output. Reopening a target can therefore block dependents again. Remove or
retarget an obsolete edge only after reviewing what the dependent work needs.

### 3.3 Sibling Order

Native sibling order is preferred sequence, not a hard blocker. Independent ready
work may proceed in parallel.

### 3.4 Real Blockers And Preferred Order

Use native dependencies for real blockers and native order or project views for
preferences. Never maintain a second dependency registry.

### 3.5 Incomplete Or Malformed Input

Cycles, unreadable relationships and inaccessible dependencies must be reported.
An unreadable parent is not an absent parent. Do not turn incomplete observations
into a claimed ready result or flatten relationships to avoid those findings.

## 4. Read-Only Resolution

The existing `scripts/secpal-work-graph.py` reads GitHub and reports JSON or text.
It neither writes graph state nor controls PR transitions or merging.

### 4.1 Planning Predicates

The resolver's existing predicates describe issue planning:

- `BLOCKED`: an open issue has an unsatisfied, cyclic or unobservable dependency.
- `READY`: an open leaf has no unsatisfied dependency or cycle, its observable
  ancestors are open, and acceptance criteria are structurally present.
- `DONE`: native issue closure reason is `completed`; it is not production proof.
- `ACTIVE`: a ready leaf has an observable open PR closing link with a named
  author. This is coordination information, not deployment or qualification.

Malformed containment is reported separately. Acceptance criteria must be a real
top-level Markdown heading named “Acceptance Criteria”, case-insensitively,
optionally prefixed with ✅ or followed by a colon, with non-empty section content.
Code blocks, quotations and mere mentions do not qualify. Their substantive
quality remains review judgment.

### 4.2 Ready Work And Coordination

`ready <owner/repo#scope>` reports ready leaves and explains excluded work.
Closing-linked open PRs provide existing native coordination data; assignments
alone do not establish execution. No claim registry, journal or attestation is
required. Unobservable coordination data is reported rather than assumed absent.

### 4.3 Selection

`next <owner/repo#scope>` recommends one ready candidate for the authenticated
GitHub executor, excluding candidates with observable claims by another author.
Existing deterministic order is priority labels (`priority: blocker`,
`priority: high`, `priority: medium`, then others), native sibling path order,
repository name and issue number. No selection is an ordinary result when no
ready candidate is available.

`show`, `validate` and `validate-issue` explain graph structure and findings.
Use repository-qualified identities; bare issue numbers need explicit `--repo`.
The optional `secpal-work-graph-audit.py` reads native closure relationships.
These readers assist planning; their output is not a required PR merge context.

## 5. Native Delivery

Use ordinary GitHub PRs, reviews, required checks and protection rules with
existing repository-specific validation. Draft means work in progress; keep a
Ready PR Ready and request re-review directly when needed. Fix genuine findings
and merge through GitHub protection when authorized.

Preserve existing SSH signing and GitHub verification of every PR commit. Reuse
successful validation until relevant changes invalidate it. Production,
cryptographic, release and external qualification requirements remain owned by
their technical contracts and executable gates.

Custom PR lifecycle authority, merge gates, routine receipts, publication journals
and historical recovery procedures are retired. Historical Git/GitHub records
remain evidence of past work and impose no delivery ceremony on new PRs.

Related guidance: [planning](planning.md), [epics](EPIC_WORKFLOW.md),
[engineering principles](development-principles.md) and
[evidence architecture](evidence-architecture-contract.md).
