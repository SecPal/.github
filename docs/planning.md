<!--
SPDX-FileCopyrightText: 2025-2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Project Planning Governance

This document is the canonical planning guide for SecPal contributors.

## Governance Decision

SecPal uses an issue-first planning model.

- GitHub Issues are the single source of truth for active work, decisions, and deferred follow-up.
- Milestones group issues into release horizons or roadmap buckets.
- Labels classify priority, type, and component.
- ADRs capture planning or architecture decisions that need durable rationale.
- GitHub Projects may be used as an optional visual layer, but they are never the canonical record of scope, acceptance criteria, priority, or delivery evidence.

The decision rationale is recorded in ADR-013: `docs/adr/20260415-issue-first-planning-governance-adr013.md`.

## What Counts As Canonical

### Active Planning

- GitHub Issues in the correct repository
- linked PRs and review state
- milestones and labels
- epic plus sub-issue structure for multi-PR work

### Supporting But Non-Canonical

- GitHub Project board views
- `docs/ideas-backlog.md` for long-horizon or non-actionable notes
- historical specifications kept only for context

If planning data exists only on a board card or in a long-form doc, it is not governed well enough.

## Public Roadmap Relationship

The public roadmap must be derived from a curated, public-safe subset of issues and milestones.

- internal planning stays issue-first inside GitHub
- the public roadmap must not expose internal-only issue details, board metadata, or sensitive discussions
- the board may inform internal prioritization, but it is not the public roadmap source of truth

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
3. If the work needs more than one PR, create an epic first and split it into sub-issues.
4. If the issue needs durable rationale, write an ADR.
5. Implement from a dedicated topic branch and open a draft PR linked to the issue.
6. Let board automation mirror progress only if the project board is enabled.

## Documentation Roles

| Document                            | Role                                          | Status                       |
| ----------------------------------- | --------------------------------------------- | ---------------------------- |
| `docs/planning.md`                  | Canonical planning and contributor onboarding | Active                       |
| `docs/project-board-integration.md` | Optional board setup and usage guide          | Active, non-canonical        |
| `docs/feature-requirements.md`      | Historical specification archive              | Archived for active planning |

## Board Usage Rules

When the SecPal Roadmap board is enabled:

- use it for status visualization, cross-repo triage, and work-in-progress awareness
- do not store acceptance criteria only on project items
- do not treat board fields as authoritative when they disagree with issues, milestones, or linked PRs
- do not use the board as the public roadmap feed without a separate public-safe curation step

If the board is unavailable or out of date, planning continues through issues, labels, milestones, and PRs without process loss.

## Related Guidance

- `docs/EPIC_WORKFLOW.md`
- `docs/labels.md`
- `docs/project-board-integration.md`
- `docs/workflows/PROJECT_AUTOMATION.md`
- `docs/adr/20260415-issue-first-planning-governance-adr013.md`
