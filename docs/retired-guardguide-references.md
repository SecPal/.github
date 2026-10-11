<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# Retired GuardGuide Reference Audit

Issue [#990](https://github.com/SecPal/.github/issues/990) removes live
organization-tooling membership for `SecPal/GuardGuide` and
`SecPal/guardguide.de`. Authenticated GitHub inventory on 2026-10-11 contains
eight accessible repositories: `.github`, `api`, `frontend`, `contracts`,
`android`, `secpal.app`, `deployment`, and `operations`. Direct authenticated
reads of both retired identities return HTTP 404.

GitHub availability, configured Polyscope specifications, local registrations,
and historical workspaces are distinct facts. A saved registration, source
reference, classifier result, or worktree does not establish live membership.
The local Polyscope registration inventory also contains only the eight active
identities. This source cleanup does not delete historical workspaces or apply
a live rollout.

## Removed Operational References

The `ACTIVE_OPERATIONAL_REFERENCE` entries removed by #990 were:

- Repository inventories in `README.md` and `.github/CLA_SETUP.md`.
- Polyscope specifications, generated tasks and checks, preview environment,
  seed and watch commands, and nginx routing in `scripts/polyscope-rollout.py`.
- Privileged nginx manifest membership in `scripts/polyscope_nginx.py`, Caddy
  routes in `scripts/render-polyscope-container-caddy.py`, and marker-based
  preview URL routing in `scripts/polyscope-expose-wrapper.sh`.
- Installer watch paths in `scripts/install-polyscope-rollout.sh`.
- Required-check membership in `scripts/sync-required-checks.sh`, hook setup in
  `setup-hooks.sh`, closed-epic discovery in `scripts/audit-closed-epics.sh`, and
  work-graph audit discovery in `scripts/secpal_work_graph/audit.py`.
- Current required-check usage and membership examples in `scripts/README.md`.
- Positive tests for retired generated configuration and actions in the rollout,
  installer, nginx, required-check, and setup suites. Shared admission,
  failure-isolation, profile-preservation, lockfile, and routing invariants
  continue to run against supported repositories.

The existing review/lifecycle registry already excludes both names. Its
immutable initialization, signature, publication, receipt, and historical
compatibility entries remain unchanged. Scope-specific inventories keep their
existing active subsets: required-check synchronization and hook setup cover
six repositories, work-graph audit discovery and review tooling cover seven,
Polyscope specifications cover eight, and preview routing covers three. This
issue introduces no additional checks, repository topology, or preview route.

## Remaining References

Every remaining occurrence belongs to one of these categories. Paths identify
the complete retained surface, including its explanatory comments and labels.

| Classification                | Files                                                                                                                                                                                                                                | Retained purpose                                                                                                      |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------- |
| `HISTORICAL_EVIDENCE`         | `CHANGELOG.md`; `docs/adr/README.md`; `docs/adr/BRAND-0001-brand-architecture.md` through `docs/adr/BRAND-0006-app-ui-stack.md`                                                                                                      | Preserve the recorded decisions, supersession notes, rollout history, and retirement evidence.                        |
| `GENERIC_TEST_FIXTURE`        | `scripts/validate-ai-instructions.sh`; `tests/validate-ai-instructions.sh`; `tests/polyscope-rollout.sh`; `docs/VALIDATION_SYSTEM.md`                                                                                                | Preserve archived-root classification, exact package detection, website detection, and manifest-over-label priority.  |
| `GENERIC_TEST_FIXTURE`        | `scripts/check-domains.sh`; `tests/check-domains.sh`; `scripts/README.md`                                                                                                                                                            | The historical non-`secpal` domain demonstrates the scanner's namespace boundary; it grants no live domain authority. |
| `GENERIC_TEST_FIXTURE`        | `tests/polyscope-rollout-followups-unit.py`; `tests/render-polyscope-container-caddy.py`; `tests/polyscope-nginx-helper.sh`; `tests/sync-required-checks.sh`                                                                         | Prove that saved retired registrations cannot re-enroll repositories, create routes, or enter live check manifests.   |
| `RETAINED_NON_LIVE_REFERENCE` | `docs/adr/BRAND-0007-secpal-product-family-architecture.md`; `docs/product-positioning.md`; `docs/brand/brand-architecture.md`; `docs/brand/naming.md`; `docs/secpal-pr-review-workflow.md`; `docs/retired-guardguide-references.md` | Document retirement and existing brand/review boundaries without changing their authority or restoring membership.    |

This audit changes no product-family, name, brand, slogan, public-positioning,
or historical-source authority. It does not establish Assure or Visit
repositories, activate required checks, deploy Polyscope changes, reopen #1175,
or close #675.
