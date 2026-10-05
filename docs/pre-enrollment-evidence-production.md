<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# Pre-enrollment integration evidence production

`prepare-pre-enrollment-draft-integration` composes maintained observations into
the existing `PRE_ENROLLMENT_DRAFT_INTEGRATION` package. It supplies evidence to
the [existing integration contract](secpal-pr-review-workflow.md#pre-enrollment-draft-current-main-integration);
that contract's verifier remains the admission authority.

Run the preparation command from freshly authenticated central protected-main
tooling, with a separate candidate checkout at the live Draft head:

```bash
python3 scripts/secpal-pr-review-actions.py prepare-pre-enrollment-draft-integration \
  --repo SecPal/REGISTERED_REPOSITORY \
  --delivery-issue DELIVERY_ISSUE --pr PRIMARY_DRAFT_PR \
  --repo-root /path/to/candidate \
  --authorization-id OPERATION_ID \
  --output /path/to/session/integration.json
```

The output must be a new file outside candidate inputs and Git metadata. Within
the central tooling checkout, use its ignored `.context` directory. Preparation
does not stage source, create a candidate commit, push, enroll a lifecycle, or
change GitHub state. Missing local parent objects fail closed; acquire those
exact objects before preparation.

The production seams retain these existing owners:

| Facts or decisions                                                   | Maintained owner                                                                         |
| -------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| PR representation and exact live default-branch head                 | `LiveGitHub.observe_ready_integration_authority`                                         |
| Registered protected-main identity and signature                     | `_authenticate_protected_bridge_main`                                                    |
| Native READY, dependencies and sole primary PR inventory             | `secpal-work-graph.py validate-issue`                                                    |
| CURRENT, native genesis and lifecycle-aware advancement absence      | `lifecycle_publication.verify_pre_enrollment_absence`                                    |
| Registry and command-set projection                                  | `fast_path.validation_registry_projection`                                               |
| Authorization and signer policy                                      | `pre_enrollment_integration.create_authorization` and maintained transition signing role |
| Mechanical merge, conflict inventory, resolution delta and markers   | Shared Git integration helpers                                                           |
| Closed schema, current-state and tree admission                      | Existing pre-enrollment verifier                                                         |
| Complete Validation, receipt, final attestation and sole branch push | Existing attestation and `integrate-pre-enrollment-draft` paths                          |

Observation uses authenticated maintained adapters. The GitHub adapter normalizes
provider representations; pure `admit_live_observation` enforces the canonical
pre-enrollment PR/main invariant. Pure assembly projects admitted facts into the
unchanged schema. Independent admission re-observes the graph, absence, PR and
protected main, compares their exact digests, and verifies the signed selection.
Preparation never substitutes a caller-authored observation or verifier result.

A clean merge derives its exact mechanical tree. For conflicts, preparation
reads the fully resolved staged tree and derives its delta against the
mechanical tree. Existing admission bounds that delta to the exact conflict
inventory. Neither case permits unrelated staged source changes.

Preparation is not Complete Validation. Supply its exact evidence file to
`attest-validation --pre-enrollment-integration-evidence` or the existing
`integrate-pre-enrollment-draft` executor. Execution still requires the exact
resolved tree in the index and rechecks current authority before its sole
non-force branch push. Read-only qualification stops after preparation and
independent verifier acceptance; it never invokes execution.
