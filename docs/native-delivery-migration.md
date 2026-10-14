<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Delivery governance migration

Implementation plan for the [proposed native contract](native-delivery.md).
This document introduces no runtime gate. Live rules and other repositories are unchanged.

## Verified inventory

GitHub REST was read on 2026-10-14 for all eight default branches: metadata,
recursive trees, governance instructions/validators, workflow definitions and
registrations, classic main protection, inherited/repository rulesets and
effective main rules. Raw observations remain temporary in this Polyscope
workspace under .git/native-cutover/. Private source and raw responses are excluded.

| Repository | Required contexts | Signatures                     | Central workflow/action calls |
| ---------- | ----------------- | ------------------------------ | ----------------------------- |
| .github    | 14                | Required                       | 3                             |
| android    | 12                | Required                       | 13                            |
| api        | 10                | Required                       | 13                            |
| contracts  | 9                 | Required                       | 10                            |
| deployment | 5                 | Required                       | 1                             |
| frontend   | 13                | Required                       | 11                            |
| operations | 1                 | Not enforced by observed rules | 0                             |
| secpal.app | 12                | Required                       | 14                            |

All eight baselines consume docs/work-graph-contract.md. Deployment and operations
also consume evidence-architecture-contract.md; deployment explicitly requests
the central review skill contract. These are configured callers, without a claim
that every operator currently invokes every optional command.

Five product repositories use the common bundle at
eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93; repository scanners use separate pins.
Deployment consumes an older pinned REUSE workflow. Old pins remain available in Git history.

Only .github requires Validate PR Evidence, Validate PR Title And Body Language,
Validate Signed PR Commits, Work-Graph PR Advisory, Work-Graph PR Gate, and
Evidence Architecture PR Gate through classic protection. Native required signatures
are enabled in seven repositories. The private repository uses a ruleset: its 404
from classic protection does not mean unprotected. Its effective ruleset lacks
a required-signatures rule.

Secret scanning, push protection and Dependabot security updates are enabled in
.github and five product repositories; those features are disabled in deployment
and the private repository. Verify feature availability or alternative scanners
before claiming equivalent coverage. These existing gaps do not justify disabling
another check. Main strictness is enabled in .github; the other six classic-protected
repositories have strict: false. This PR preserves all current settings.

## KEEP / REPLACE / DELETE

| Mechanism                                                                | Decision | Concrete reason or replacement                                                                   |
| ------------------------------------------------------------------------ | -------- | ------------------------------------------------------------------------------------------------ |
| Applicable build, lint, types and behavioral tests                       | KEEP     | Detect real build/runtime defects; preserve stack-specific coverage.                             |
| REUSE, license compatibility, licensing and CLA commitments              | KEEP     | Preserve redistribution guarantees; independently verify actual CLA-provider enforcement.        |
| CodeQL, repository scanners and dependency updates                       | KEEP     | Detect vulnerabilities and secrets; preserve current coverage.                                   |
| Locks, immutable action/workflow pins and least-privilege tokens         | KEEP     | Preserve reproducibility and privileged-event trust boundaries.                                  |
| Release provenance, vulnerability re-evaluation and product audit trails | KEEP     | Preserve released artifact and domain integrity, separately from PR ceremony.                    |
| Custom signed-commit check                                               | REPLACE  | Native required signatures after independently verifying SSH, unsigned and tampered cases.       |
| Work-graph advisory and merge gates                                      | REPLACE  | Native PR rules, candidate CI and resolved conversations; issues remain optional planning aids.  |
| Evidence architecture delivery gate                                      | REPLACE  | Behavioral trust-boundary tests and native CI; retain real deployment qualification separately.  |
| Mandatory PR evidence and language checks                                | REPLACE  | Short English description and validation summary without a prose parser merge gate.              |
| Lifecycle engine, finite counters and routine receipts                   | DELETE   | Native PRs/reviews/checks already persist delivery state; migrate runtime callers first.         |
| Exceptional historical recovery/admission policies                       | DELETE   | Future delivery uses current GitHub state without historical PR replay.                          |
| Lifecycle journal dependency                                             | DELETE   | Retain the protected branch as history; remove future readers/writers.                           |
| Self-referential policy tests                                            | DELETE   | Remove with retired code; retain behavioral security tests.                                      |
| Review-memory scanning, counters and issue promotion                     | DELETE   | Native reviews persist findings. Implemented in this PR.                                         |
| Board sync, draft reminder and required PR-size status                   | DELETE   | Optional native Projects workflows and advisory size output suffice after pin/context migration. |

## First coherent cut

Delete the active scheduled/review-triggered Review Memory workflow, its 796-line
CLI, two exclusive regression scripts and operational guide. Remove four npm
commands and preflight/governance-suite/focused-instruction callers. Detach only
retired memory assertions from retained review-skill and Dependabot tests.

Historical changelog entries and version_collision.py snapshot path bindings remain:
they authenticate old Git objects rather than execute the removed current files.
No required context references this workflow. No current workflow in another
repository calls it or its CLI. This removes the organization-App-token scan of
four repositories and its automatic recurring tracking-issue write path.

## Actual migration blockers

- The linked-issue work-graph gate does not govern issue-free PRs: a direct
  enforced observation of draft #1209 returned pass with status not_a_delivery_pr
  and owning_issue null. This is not a first-PR blocker. Its broader written
  lifecycle requirements still need retirement; do not invent an issue to enroll
  this explicitly authorized simplification.
- PR-body/language checks execute trusted base code; a template edit cannot
  replace them. Keep exact-body validation until required contexts are retired.
- All eight baselines request the work-graph contract; deployment requests the
  review skill. Deleting those shared paths now breaks configured consumers.
- Polyscope rollout and user/system installers load the evidence validator/package.
  Replace and independently qualify fail-closed setup before bundle deletion or
  service changes. This PR performs no operational installation.
- SHA-pinned shared workflows/actions require later repository-scoped migration.
  Old Git objects and required producers must stay available.
- Independent verification of the complete native replacement is outstanding.
  This first cut performs no administrative protection changes.

## Safe sequence and rollback

1. Review and validate the signed deletion candidate. Independently verify
   retained licensing/security/integrity negative cases. This cut deletes no
   required producer and needs no replacement security workflow.
2. Independently verify native PR rules, required candidate CI, signatures and
   conversation resolution preserve merge guarantees without issue graphs.
   Only then may an administrator remove Work-Graph PR Advisory and Work-Graph
   PR Gate from .github required contexts. Retain producers until that edit.
   No protection edit is needed merely to open this issue-free first cut.
3. Merge through ordinary GitHub rules. Reverting the cut restores memory
   automation; historical reviews/issues are untouched.
4. Migrate seven external baselines and deployment's skill reference, then central
   instructions and generated Polyscope prompts. Qualify workspace setup/deployment
   separately. Record previous deployed commit/service state and restore both on rollback.
5. Verify SSH-signed, unsigned and tampered commits against native signing rules.
   Include an unsigned intermediate commit beneath a signed HEAD and the actual
   squash merge mode: destination-commit verification must not silently replace
   the current all-PR-commits guarantee. Retain the custom check unless the native
   rule enforces the agreed signature contract or an independent reviewer explicitly
   approves the narrower contract. Only then remove Validate Signed PR Commits
   from required contexts and delete its workflow, script and exclusive tests.
6. Verify short PR bodies and failing required CI under native rules. Remove
   Validate PR Evidence and Validate PR Title And Body Language required contexts;
   then remove workflows, scripts, exclusive tests and template evidence fields.
   Do not build another prose-validation program.
7. Qualify runtime trust boundaries; remove Evidence Architecture PR Gate from
   required contexts, then its delivery-only implementation/artifacts. Keep real
   deployment, privacy and product-integrity checks.
8. After callers migrate, delete review engine, recovery policies, routine receipt
   schemas, skill installer, finite-policy tests and obsolete delivery guides
   together. Keep journal deletion/non-fast-forward protection and historic records;
   remove future delivery reads/writes.
9. Remove board/reminder workflows after pinned callers migrate. Remove required
   PR-size contexts after confirming advisory intent. Consolidate duplicated jobs
   only with verified coverage.
10. Save fresh before/after protection snapshots and source-App bindings for every
    edit. Preserve REUSE/license, CodeQL, applicable build/test/security checks,
    signatures, admin enforcement, linear history, resolved conversations and
    disabled force pushes/deletion. Rollback restores old producers first, then
    their required contexts. Never require a deleted job.

Keep strict current-base validation in .github. A merge queue is optional and needs
plan/repository support plus merge_group coverage for every required workflow;
independently verify it before replacing strictness. See GitHub's
[protected branch contract](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches).

## Measurable acceptance

This PR: five files, four npm commands and one scheduled/App-write workflow removed;
net tracked lines decrease; required producers remain; relevant regressions, lint
and REUSE pass; final PR commits have GitHub-verified SSH signatures; other
repositories and live protection match captured observations.

Completion: eight native-delivery baselines; zero future journal readers/writers,
routine receipts/attestations, finite review counters or historical recovery
steps; zero required issue-graph/PR-body parser gates; exclusive tests, schemas,
fixtures and guides removed with retired code; every required context has an
applicable producer; unsigned/tampered commits and failing security/build/tests
block merge; release/domain integrity preserved; no strictness reduction without
verified integrated-candidate validation. Delivery becomes branch, PR, CI/review, merge.

Earlier qualification remains evidence for its original revision and scope.
It does not qualify this changed tree or the unimplemented full cutover.
Re-run relevant checks on the final candidate; retain historical evidence as
records without requiring future PRs to consume it.

## Public workflow caller references

- .github/.github/workflows/dependabot-auto-merge.yml:42 → SecPal/.github/.github/workflows/reusable-dependabot-auto-merge.yml@6982aa6d7e9d2b739d884f4987858efa97f5e9e5
- .github/.github/workflows/deploy-main.yml:17 → SecPal/.github/.github/workflows/reusable-deploy-main.yml@6982aa6d7e9d2b739d884f4987858efa97f5e9e5
- .github/.github/workflows/check-conflict-markers.yml:19 → SecPal/.github/.github/workflows/reusable-check-conflict-markers.yml@6982aa6d7e9d2b739d884f4987858efa97f5e9e5
- android/.github/workflows/reusable-repository-security.yml:29 → SecPal/.github/.github/actions/trivy-repository-scan@226180bd610af77313057141dca23b7dce88a46c
- android/.github/workflows/dependabot-auto-merge.yml:37 → SecPal/.github/.github/workflows/reusable-dependabot-auto-merge.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- android/.github/workflows/quality.yml:26 → SecPal/.github/.github/workflows/reusable-reuse.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- android/.github/workflows/quality.yml:31 → SecPal/.github/.github/workflows/reusable-license-compatibility.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- android/.github/workflows/quality.yml:35 → SecPal/.github/.github/workflows/reusable-prettier.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- android/.github/workflows/quality.yml:41 → SecPal/.github/.github/workflows/reusable-markdown-lint.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- android/.github/workflows/quality.yml:47 → SecPal/.github/.github/workflows/reusable-ai-instructions.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- android/.github/workflows/quality.yml:53 → SecPal/.github/.github/workflows/reusable-node-lint.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- android/.github/workflows/quality.yml:59 → SecPal/.github/.github/workflows/reusable-node-build.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- android/.github/workflows/project-automation.yml:55 → SecPal/.github/.github/workflows/project-automation-core.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- android/.github/workflows/project-automation.yml:62 → SecPal/.github/.github/workflows/draft-pr-reminder.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- android/.github/workflows/pr-size.yml:17 → SecPal/.github/.github/workflows/reusable-pr-size.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- android/.github/workflows/check-conflict-markers.yml:19 → SecPal/.github/.github/workflows/reusable-check-conflict-markers.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- api/.github/workflows/reusable-repository-security.yml:30 → SecPal/.github/.github/actions/trivy-repository-scan@f8cabffc336002e72bb7a25ef40331fc58b0e83d
- api/.github/workflows/dependabot-auto-merge.yml:32 → SecPal/.github/.github/workflows/reusable-dependabot-auto-merge.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- api/.github/workflows/quality.yml:26 → SecPal/.github/.github/workflows/reusable-reuse.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- api/.github/workflows/quality.yml:105 → SecPal/.github/.github/workflows/reusable-markdown-lint.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- api/.github/workflows/quality.yml:111 → SecPal/.github/.github/workflows/reusable-ai-instructions.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- api/.github/workflows/quality.yml:117 → SecPal/.github/.github/workflows/reusable-php-lint.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- api/.github/workflows/quality.yml:123 → SecPal/.github/.github/workflows/reusable-php-stan.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- api/.github/workflows/project-automation.yml:33 → SecPal/.github/.github/workflows/project-automation-core.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- api/.github/workflows/project-automation.yml:39 → SecPal/.github/.github/workflows/draft-pr-reminder.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- api/.github/workflows/pr-size.yml:17 → SecPal/.github/.github/workflows/reusable-pr-size.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- api/.github/workflows/php-ci.yml:20 → SecPal/.github/.github/workflows/reusable-php-lint.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- api/.github/workflows/php-ci.yml:24 → SecPal/.github/.github/workflows/reusable-php-stan.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- api/.github/workflows/check-conflict-markers.yml:18 → SecPal/.github/.github/workflows/reusable-check-conflict-markers.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- contracts/.github/workflows/dependabot-auto-merge.yml:33 → SecPal/.github/.github/workflows/reusable-dependabot-auto-merge.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- contracts/.github/workflows/quality.yml:25 → SecPal/.github/.github/workflows/reusable-reuse.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- contracts/.github/workflows/quality.yml:30 → SecPal/.github/.github/workflows/reusable-license-compatibility.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- contracts/.github/workflows/quality.yml:39 → SecPal/.github/.github/workflows/reusable-markdown-lint.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- contracts/.github/workflows/quality.yml:47 → SecPal/.github/.github/workflows/reusable-ai-instructions.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- contracts/.github/workflows/quality.yml:59 → SecPal/.github/.github/workflows/reusable-actionlint.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- contracts/.github/workflows/project-automation.yml:35 → SecPal/.github/.github/workflows/project-automation-core.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- contracts/.github/workflows/project-automation.yml:43 → SecPal/.github/.github/workflows/draft-pr-reminder.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- contracts/.github/workflows/pr-size.yml:14 → SecPal/.github/.github/workflows/reusable-pr-size.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- contracts/.github/workflows/check-conflict-markers.yml:18 → SecPal/.github/.github/workflows/reusable-check-conflict-markers.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- deployment/.github/workflows/quality.yml:58 → SecPal/.github/.github/workflows/reusable-reuse.yml@75bd30d419c5a85422cec10cc5480bf198ee9424
- frontend/.github/workflows/reusable-repository-security.yml:30 → SecPal/.github/.github/actions/trivy-repository-scan@0c9430aa4743f7ba4281f7fb51098dc4899a128f
- frontend/.github/workflows/quality.yml:27 → SecPal/.github/.github/workflows/reusable-reuse.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- frontend/.github/workflows/quality.yml:51 → SecPal/.github/.github/workflows/reusable-prettier.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- frontend/.github/workflows/quality.yml:58 → SecPal/.github/.github/workflows/reusable-markdown-lint.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- frontend/.github/workflows/quality.yml:65 → SecPal/.github/.github/workflows/reusable-ai-instructions.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- frontend/.github/workflows/quality.yml:72 → SecPal/.github/.github/workflows/reusable-node-lint.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- frontend/.github/workflows/quality.yml:79 → SecPal/.github/.github/workflows/reusable-node-build.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- frontend/.github/workflows/project-automation.yml:34 → SecPal/.github/.github/workflows/project-automation-core.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- frontend/.github/workflows/project-automation.yml:42 → SecPal/.github/.github/workflows/draft-pr-reminder.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- frontend/.github/workflows/pr-size.yml:18 → SecPal/.github/.github/workflows/reusable-pr-size.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- frontend/.github/workflows/check-conflict-markers.yml:19 → SecPal/.github/.github/workflows/reusable-check-conflict-markers.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- secpal.app/.github/workflows/dependabot-auto-merge.yml:33 → SecPal/.github/.github/workflows/reusable-dependabot-auto-merge.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- secpal.app/.github/workflows/quality.yml:21 → SecPal/.github/.github/workflows/reusable-reuse.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- secpal.app/.github/workflows/quality.yml:26 → SecPal/.github/.github/workflows/reusable-license-compatibility.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- secpal.app/.github/workflows/quality.yml:30 → SecPal/.github/.github/workflows/reusable-prettier.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- secpal.app/.github/workflows/quality.yml:36 → SecPal/.github/.github/workflows/reusable-markdown-lint.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- secpal.app/.github/workflows/quality.yml:43 → SecPal/.github/.github/workflows/reusable-ai-instructions.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- secpal.app/.github/workflows/quality.yml:50 → SecPal/.github/.github/workflows/reusable-node-lint.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- secpal.app/.github/workflows/quality.yml:56 → SecPal/.github/.github/workflows/reusable-node-build.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- secpal.app/.github/workflows/quality.yml:63 → SecPal/.github/.github/workflows/reusable-node-build.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- secpal.app/.github/workflows/quality.yml:70 → SecPal/.github/.github/workflows/reusable-node-test.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- secpal.app/.github/workflows/project-automation.yml:54 → SecPal/.github/.github/workflows/project-automation-core.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- secpal.app/.github/workflows/project-automation.yml:61 → SecPal/.github/.github/workflows/draft-pr-reminder.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- secpal.app/.github/workflows/pr-size.yml:17 → SecPal/.github/.github/workflows/reusable-pr-size.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
- secpal.app/.github/workflows/check-conflict-markers.yml:18 → SecPal/.github/.github/workflows/reusable-check-conflict-markers.yml@eab46aa7a3d828e0f1b2e75a48a8ff8f135dec93
