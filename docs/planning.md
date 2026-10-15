<!--
SPDX-FileCopyrightText: 2025-2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# Project Planning Governance

This document is the canonical planning guide for SecPal contributors.

Use native GitHub issue relationships and ordinary PR delivery as described in
`docs/work-graph-contract.md`. This guide covers where work is planned.

## Governance Decision

SecPal uses an issue-first planning model.

- GitHub Issues are the single source of truth for active work, decisions, and deferred follow-up.
- Milestones group issues into release horizons or roadmap buckets.
- Labels classify priority, type, and component.
- ADRs capture planning or architecture decisions that need durable rationale.
- The unused GitHub Projects board and its automation are retired under [#1217](https://github.com/SecPal/.github/issues/1217); they have no planning or delivery role.

The decision rationale is recorded in ADR-013: `docs/adr/20260415-issue-first-planning-governance-adr013.md`.

## What Counts As Canonical

### Active Planning

- GitHub Issues in the correct repository
- linked PRs and review state
- milestones and labels
- epic plus sub-issue structure for work holding more than one deliverable contract

### Supporting But Non-Canonical

- `docs/ideas-backlog.md` for long-horizon or non-actionable notes
- historical specifications kept only for context

Move any still-needed board-only scope or acceptance criteria into the owning issue before separately authorized board closure. Historical project records do not replace native issue relationships.

## Public Roadmap Relationship

The public roadmap must be derived from a curated, public-safe subset of issues and milestones.

- internal planning stays issue-first inside GitHub
- the public roadmap must not expose internal-only issue details, board metadata, or sensitive discussions
- retiring the internal board does not remove or change the public product-roadmap page

Implementation planning for the public roadmap is tracked in `SecPal/secpal.app#61`.

## Repository Routing

Create work in the repository that owns the change.

| Topic                    | Repository   | Examples                                |
| ------------------------ | ------------ | --------------------------------------- |
| Backend/API features     | `api`        | "Implement guard shift endpoints"       |
| Frontend features        | `frontend`   | "Add shift calendar view"               |
| API contract changes     | `contracts`  | "Add pagination to shift list endpoint" |
| Android app work         | `android`    | "Add Device Owner enrollment bridge"    |
| Public website / roadmap | `secpal.app` | "Implement public roadmap page"         |
| Cross-repo features      | `.github`    | "Digital guard book MVP"                |
| Infrastructure/CI/CD     | `.github`    | "Add performance testing workflow"      |
| Legal/licensing          | `.github`    | "Legal review of CLA"                   |
| Documentation (org-wide) | `.github`    | "Planning governance ADR"               |
| Security/GHAS            | `.github`    | "Enable secret scanning for all repos"  |

## Minimal Contributor Workflow

1. Open or refine a GitHub Issue in the correct repository.
2. Add the smallest useful labels and milestone.
3. Use an epic and native sub-issues when they help coordinate larger work.
4. If the issue needs durable rationale, write an ADR.
5. Implement from a topic branch and open a PR; use Draft for work in progress.
6. Use native PR reviews, checks and protected merging; no board status or bot is required.

Signed commit verification is enforced by CI. English-only GitHub communication remains reviewer-enforced for now.

## Documentation Roles

| Document                       | Role                                          | Status                       |
| ------------------------------ | --------------------------------------------- | ---------------------------- |
| `docs/work-graph-contract.md`  | Native GitHub planning and delivery           | Active                       |
| `docs/planning.md`             | Canonical planning and contributor onboarding | Active                       |
| `docs/feature-requirements.md` | Historical specification archive              | Archived for active planning |

## Retired Board Automation

There is no supported board setup or status-mirroring workflow. Issues, native
relationships, read-only WorkGraph planning, PRs, reviews, CI and protection
remain authoritative; no replacement lifecycle machinery is introduced.

Project records, App installation and credentials require separate administrator
authorization after source retirement and a complete consumer inventory.

## Related Guidance

- `docs/work-graph-contract.md`
- `docs/EPIC_WORKFLOW.md`
- `docs/labels.md`
- `docs/adr/20260415-issue-first-planning-governance-adr013.md`
