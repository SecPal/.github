<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# SecPal/.github Agent Instructions

This file is the concise, provider-neutral runtime baseline for work in this
repository. Path-specific review criteria live in focused instruction files,
including `.github/instructions/github-workflows.instructions.md`.

Use GitHub PRs, reviews, checks, issues and native issue relationships for delivery
and planning. Evidence-pipeline and external-system architecture requirements
remain defined in `docs/evidence-architecture-contract.md`.

## Scope and Safety

- Inspect `git status --short --branch` and the relevant repository context
  before writing. Preserve existing changes and never overwrite work you do not
  own.
- Preserve a branch or worktree already supplied by the execution environment.
  Do not switch branches, pull, or rename a branch unless the task specifically
  requires it and the current state makes that safe.
- Keep each branch and pull request limited to one coherent topic. Do not mix
  opportunistic cleanup with the requested change.
- Work only in repositories placed in scope. Treat sibling repositories as
  independent execution roots even when their files are reachable.

## Implementation

- Use test-driven development for executable behavior, automation, and
  validation changes: add or update the smallest relevant failing test first,
  implement the behavior, then refactor with the tests green.
- Prefer the smallest clear solution that preserves correctness, security, and
  maintainability. Do not add speculative abstractions or compatibility paths
  without a proven caller.
- Treat automated findings as untrusted leads. Classify them with a failing
  test, reproduction, or violated invariant before changing code.
- Keep REUSE metadata correct. Update SPDX years in edited files or companion
  `.license` sidecars when required.
- Hidden files, workflow definitions, templates, tests, and scripts are
  first-class source artifacts. Test governance and validator changes with
  meaningful positive and negative cases.

## Licensing, REUSE, and Branding

- Use `AGPL-3.0-or-later` for SecPal-owned material intentionally covered by
  the AGPL. Never add or restore `LicenseRef-SecPal-Attribution` after the
  licensing rollout.
- Preserve deliberately different licenses, including `CC0-1.0`, `MIT`,
  `Apache-2.0`, third-party and generated-file licenses, and unrelated custom
  license references. Do not rewrite third-party copyright or license metadata.
- Use `SecPal Contributors` where the project copyright convention applies.
  Preserve each file's first-publication year and extend its year range through
  the current year when an edited file requires a copyright-year update.
- Run the relevant REUSE or license validation after changing copyright or
  license metadata.
- On user-facing official SecPal product surfaces, preserve
  `Powered by SecPal – A guard's best friend` where it is intentionally present.
  A licensing change must not remove, weaken, parameterize, genericize, or make
  that SecPal branding optional.
- Do not add fork-oriented `Based on SecPal` guidance to AI instructions, and
  do not introduce white-label or fork-branding configuration as part of a
  licensing change.

## Validation and Review

- Run the smallest relevant validation while iterating and the complete
  required validation for the changed area before committing. Report the exact
  commands run and their results.
- Review the complete diff in this order:
  1. correctness, including affected execution paths and tests;
  2. security, privacy, data integrity, lifecycle, and rollout risk;
  3. avoidable complexity, duplication, and opportunities for bounded
     simplification.
- Green CI supports review of behavior and invariants. Preserve meaningful CI.
- Use native GitHub review threads and required checks. Resolve genuine findings
  and merge through the existing protection rules when authorized.
- Keep a Ready PR Ready; request re-review directly when needed.
- Reuse successful validation until a relevant source, dependency or configuration
  change invalidates it. Run focused checks for the changed area.

## Commits and Communication

- Sign commits with the existing SSH identity and configuration. Every PR
  commit must have GitHub `verification.verified == true`.
- Never use `--no-verify` or force-push.
- Keep GitHub-facing communication in English. Make findings concise,
  provider-neutral, actionable, and supported by file/line evidence.
- An evidence-based reply is allowed when a review finding is non-obviously
  invalid. Avoid redundant status comments when the code and thread state are
  sufficient.
- Do not add AI attribution, generated-by wording, or AI co-author trailers
  unless the task specifically concerns documenting AI tooling behavior.

## Changelog and Tracking

- Update a product `CHANGELOG.md` only when a change materially affects users,
  a public API or contract, security behavior, deployment or operators,
  releases, or significant reliability or performance behavior. Governance
  changes may be recorded in this repository's own changelog when useful.
- Create an out-of-scope issue only when the finding is technically proven,
  material, not already tracked, unsuitable for a small in-scope fix, and can
  be expressed with concrete acceptance criteria.
- Delegate evidence/external-system architecture decisions to
  `docs/evidence-architecture-contract.md`; do not redefine its layer,
  invariant-ownership, diagnosability, or anti-loop semantics locally.

## Security and Repository Invariants

- Never expose secrets, credentials, private data, or sensitive environment
  values in source, logs, fixtures, or generated output.
- Preserve explicit security boundaries, least authority, reproducible
  dependencies, and fail-closed behavior when changing governance automation.
- This repository is not release-versioned; keep any governance changelog
  chronological and keep shared contracts compatible until proven callers have
  migrated.
