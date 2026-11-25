<!--
SPDX-FileCopyrightText: 2025-2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# Planning work in GitHub

[ADR-016](adr/20260824-native-work-graph-engineering-governance-adr016.md)
defines issue-first planning. The [native work graph](work-graph-contract.md)
owns relationship and delivery semantics.

1. Open or refine the issue in the repository that owns the change and keep the
   scope and acceptance criteria there.
2. Add useful [labels](labels.md) and a milestone. Use an
   [epic and native sub-issues](EPIC_WORKFLOW.md) when several independently
   deliverable changes need coordination.
3. Record a durable architecture decision in an ADR when the change needs one.
4. Work on a topic branch, sign commits and open a pull request. Use Draft
   while work is in progress and follow the repository's review, checks and
   protected merge process.

## Repository ownership

| Scope                                                         | Repository   |
| ------------------------------------------------------------- | ------------ |
| Backend and application state                                 | `api`        |
| Product UI                                                    | `frontend`   |
| Shared API contracts                                          | `contracts`  |
| Android and native integration                                | `android`    |
| Public website and roadmap                                    | `secpal.app` |
| Portable self-hosting and deployment contracts                | `deployment` |
| Private Managed operation and policy                          | `operations` |
| Shared governance, cross-repository planning and architecture | `.github`    |

Public roadmap content uses a curated subset of issues and milestones suitable
for publication. Contributors use English for GitHub communication and follow
the repository's instructions for code and documentation.
