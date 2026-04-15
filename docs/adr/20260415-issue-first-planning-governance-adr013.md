<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# ADR-013: Issue-First Planning Governance And Optional Project Board Mirror

## Status

**Accepted** (Issue #354)

## Date

2026-04-15

## Deciders

@aroviqen

## Context

SecPal planning drifted across several artifacts:

- `docs/feature-requirements.md` accumulated large historical specifications
- `docs/planning.md` and `docs/project-board-integration.md` described a project-board-heavy flow
- active work increasingly happened in GitHub Issues and pull requests instead
- the public roadmap direction in `SecPal/secpal.app#61` needs a stable internal source-of-truth model

This left contributors without a single canonical planning process and made it too easy for planning status to diverge between documents, issues, and the project board.

## Decision

SecPal adopts an issue-first planning model.

- GitHub Issues are the canonical source of truth for active planning and deferred follow-up work.
- Milestones group roadmap and release intent.
- Labels capture classification such as priority, type, and component.
- ADRs record durable planning and architecture decisions when rationale matters beyond one issue.
- GitHub Projects may be used as an optional visual mirror for cross-repository tracking, but never as the canonical source of scope, acceptance criteria, or delivery evidence.
- The public roadmap must be derived from a curated, public-safe subset of issues and milestones rather than from board-only metadata.

The documentation action plan attached to this decision is:

- `docs/planning.md` becomes the canonical contributor-facing planning guide
- `docs/project-board-integration.md` remains as an optional board-operations guide only
- `docs/feature-requirements.md` is archived for active planning and kept only as historical context until remaining useful content is migrated into issues or ADRs

## Consequences

### Positive

- Planning status has one canonical home.
- Cross-repository work becomes easier to audit because issues and linked PRs already carry durable history.
- The public roadmap can be built from curated issue data without depending on internal-only board hygiene.
- Project-board automation remains useful without being a governance dependency.

### Negative

- Historical long-form planning content still needs cleanup and migration.
- Existing board collateral and helper scripts may need follow-up alignment with the new governance wording.
- Contributors used to document-first planning must change habits.

## Repo-Local Follow-Up Impact

- `.github` must track remaining migration of actionable content out of `docs/feature-requirements.md`.
- `.github` must align any remaining project-board helper collateral that still assumes `feature-requirements.md` is active planning.
- `SecPal/secpal.app#61` remains the public roadmap implementation track and must consume only public-safe planning data.

## Alternatives Considered

1. **GitHub Issues plus actively maintained Project Board as dual canonical sources**
   - Pro: strong visual planning workflow
   - Contra: creates two places where status can drift and increases maintenance cost

2. **Project Board as primary planning source**
   - Pro: easy visual triage
   - Contra: weak auditability, poor durability for acceptance criteria, and unsuitable as a public roadmap source

3. **Keep long-form planning docs as the main source**
   - Pro: rich narrative context in one place
   - Contra: hard to keep current, weak repo ownership, and not PR-sized or issue-driven

## Related

- [Issue #354](https://github.com/SecPal/.github/issues/354)
- [SecPal/secpal.app#61](https://github.com/SecPal/secpal.app/issues/61)
- [docs/planning.md](../planning.md)
- [docs/project-board-integration.md](../project-board-integration.md)
- [docs/EPIC_WORKFLOW.md](../EPIC_WORKFLOW.md)
