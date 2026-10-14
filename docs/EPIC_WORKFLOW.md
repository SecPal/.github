<!-- SPDX-FileCopyrightText: 2026 SecPal -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# Epic And Sub-Issue Workflow

Use an epic when native GitHub sub-issues help coordinate larger or
cross-repository work. A focused change can use an ordinary issue or PR.

Describe the intended outcome and acceptance criteria in the owning repository.
Use native parent/sub-issue links and dependencies. Keep independent work
parallel and record actual technical blockers.

Link PRs to the work they deliver. Use `Fixes` or `Closes` only when merging the
PR completes that issue; use ordinary references for related work. Review
cross-repository results before closing their parent epic. Close superseded
issues as not planned and preserve their history.

When a change depends on live configuration or an external service, verify that
behavior in the appropriate environment. A documentation change or green unit
test does not establish production qualification.

For an optional read-only comparison of historical checklist mirrors:

```bash
bash scripts/audit-closed-epics.sh --org SecPal --repo .github
```

The report grants no delivery or mutation authority.

See [native delivery](work-graph-contract.md), [planning](planning.md) and
[contributor guidance](../CONTRIBUTING.md).
