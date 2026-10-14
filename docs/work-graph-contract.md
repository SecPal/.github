<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# Native GitHub Planning And Delivery

Use GitHub issues, parent/sub-issues and dependencies to describe work. Record
actual technical dependencies; independent repository changes can proceed in
parallel. Keep each PR focused on a reviewable change. An issue or epic is useful
when the work needs tracking, rather than a prerequisite for every source change.

Delivery uses ordinary GitHub PRs, review threads, required checks and branch
protection. Draft denotes work in progress. Once Ready, keep the PR Ready and
request re-review directly when needed. Fix genuine blocking feedback and merge
through the repository's protection rules when authorized. Preserve existing SSH
signing and require GitHub verification of every PR commit.

Use existing repository-specific technical and security validation. Reuse
successful results until a relevant change invalidates them; validate the affected
behavior after a change. Production qualification, cryptographic evidence and
release integrity remain owned by their product contracts and executable gates.

This document normatively incorporates
`docs/evidence-architecture-contract.md` for evidence pipelines and external
systems. That contract remains the authoritative definition of those security
boundaries; repository baselines should reference it directly.

Custom PR lifecycle, review counters, receipts, journals and recovery procedures
are retired. Historical commits and GitHub records remain evidence of past work
and confer no requirements on new PRs.

Related guidance: [planning](planning.md), [epics](EPIC_WORKFLOW.md) and
[engineering principles](development-principles.md).
