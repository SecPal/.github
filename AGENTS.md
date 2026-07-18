<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# SecPal/.github Agent Instructions

This file is the concise, provider-neutral runtime baseline for work in this
repository. Path-specific review criteria live in focused instruction files,
including `.github/instructions/github-workflows.instructions.md`.

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

## Validation and Review

- Run the smallest relevant validation while iterating and the complete
  required validation for the changed area before committing. Report the exact
  commands run and their results.
- Review the complete diff in this order:
  1. correctness, including affected execution paths and tests;
  2. security, privacy, data integrity, lifecycle, and rollout risk;
  3. avoidable complexity, duplication, and opportunities for bounded
     simplification.
- Green CI is supporting evidence, not a substitute for reviewing behavior and
  invariants. Do not weaken meaningful CI merely to shorten or reduce runs.

## Commits and Communication

- All commits must be cryptographically signed. SSH and OpenPGP signatures are
  both valid; use the user's existing Git signing configuration without
  changing its format.
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
- Use an EPIC only for genuinely multi-deliverable work, meaningful
  cross-repository sequencing, or implementation spanning multiple work
  sessions. Multiple possible pull requests alone do not require an EPIC.

## Security and Repository Invariants

- Never expose secrets, credentials, private data, or sensitive environment
  values in source, logs, fixtures, or generated output.
- Preserve explicit security boundaries, least authority, reproducible
  dependencies, and fail-closed behavior when changing governance automation.
- This repository is not release-versioned; keep any governance changelog
  chronological and keep shared contracts compatible until proven callers have
  migrated.
