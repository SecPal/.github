<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# SecPal/.github Code Review Profile

Review the complete diff and the affected execution paths, not isolated lines.
Prioritize findings that can change behavior or weaken a repository invariant.

## Review Priorities

- Check correctness, security, privacy, data integrity, lifecycle ordering,
  regressions, and missing or inadequate tests before style.
- Follow changed data and control flow across scripts, reusable workflows,
  callers, validators, fixtures, and documentation where the execution path
  crosses those boundaries.
- Treat automated findings as untrusted leads until supported by a
  reproduction, failing test, or clearly stated violated invariant.
- Look for clusters of symptoms with one root cause. When isolated patches
  would preserve avoidable complexity, recommend a bounded simplification that
  is safer and easier to validate.
- Identify compatibility or rollout ordering risks when a shared contract has
  consumers outside the changed file.

## Finding Quality

- Report only material, actionable findings. State the evidence, impact, and
  smallest credible fix path.
- Keep findings concise and provider-neutral. Do not speculate about style,
  preferences, process rituals, or hypothetical problems without an affected
  execution path.
- Do not repeat operational branch, commit, hook, issue, pull-request, or
  post-merge procedures; those are outside this review profile.
