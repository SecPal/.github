<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# Declared Evidence Architecture Enforcement

Semantics belong to the [canonical architecture contract](evidence-architecture-contract.md)
and its [work-graph entry point](work-graph-contract.md). This document describes
the executable declaration interface, its limits and source rollout obligations.
It supplies no new delivery, signing, lifecycle, integration or provider authority.

## Invocation And Bounds

Use the maintained governance checkout's executable against the actual source
or active worktree:

```bash
python3 -I scripts/secpal-evidence-architecture.py \
  --repository-root "$PWD" --repository SecPal/.github
```

Before the owning caller dispatches a costly external operation, add `--dispatch`.
That mode requires a declaration and nonempty operation inventory. It performs
read-only admission and never dispatches anything. The caller must stop on a
nonzero result. The Polyscope instruction-root boundary invokes the same owner
for source roots, provisioned worktrees and direct worktree actions. Declaration
evidence is freshly checked even when the AI-instruction result was cached.

Managed bundle mode uses `--managed-workspace-root` and repeated
`--managed-repository` names. It additionally rejects duplicate invariant owners
across the supplied managed scope. Registration-only repositories without an
active runtime instruction surface are outside automation admission.

Each input and output is bounded to 64 KiB. Lists have explicit limits. Duplicate
JSON keys, nonfinite numbers, unknown fields, symlinks, nonregular files and path
traversal fail closed. Findings retain closed diagnostic codes and fixed facts;
they do not retain source code, case inputs, stdout, stderr or environment values.
Python executes in isolated mode with a regular, explicitly owned package.
Both installers require a successful package/parser smoke test before activation.

## Declaration Interface

`.secpal/evidence-architecture.json` has exactly these fields:

- `schema`: `secpal-evidence-architecture/v1`.
- `repository`: the trusted caller's exact repository identity.
- `runtime_baseline`: `delegation` (`direct` or `transitive_work_graph`) and
  `generic_authorities` (exactly the selected canonical contract path).
- `external_operations`: objects with `id`, boolean `reachable`, `fallible`,
  `trusted`, and `diagnostic_identity`. A diagnostic is null or exactly
  `{ "id": "host.inspect", "kind": "semantic" }`. Reachable, fallible trusted
  operations require the semantic form with a unique identity within the
  declaration. Identities are bounded closed tokens;
  additional output or credential fields are rejected.
- `pure_surfaces`: objects with `id`, `responsibility` (`normalization` or
  `admission`), `capabilities`, and `source`. The only allowed pure capability is
  `deterministic_compute`. `source` names a repository-relative Python file and
  function, for example `pipeline.py#normalize`.
- `invariant_declarations`: owner objects with `id`, `invariant`, `role: owner`,
  and `surface`, or independent objects with those fields, role
  `independent_enforcement`, plus `owner`, `derivation`, and `agreement_proof`.
  The named admission surfaces bind the actual executable implementation.
  Invariant declaration IDs must be unique across the complete managed scope;
  otherwise an agreement cannot identify exactly one owner and enforcement.

An absent declaration permits baseline-only validation, but never dispatch
admission. Applicable declaration completeness remains a review obligation.
Canonical references must be operative inline-code or link references in
`AGENTS.md`; comments, quoted examples and code fences cannot satisfy delegation.
Supported transitive work-graph incorporation consumes the accepted canonical
companion; repository-specific stricter rules remain valid.

## Pure Source And Executable Agreement

The maintained pure subset consists of a one-argument, single-return Python
function. It supports bounded constants, comparisons, Boolean expressions,
conditional expressions, `len`, and closed string operations: `lower`, `upper`,
`strip`, `removeprefix`, `removesuffix`, `startswith`, and `endswith`. Functions
are parsed without importing their module. Builtin namespace shadowing and
evaluated function metadata are rejected throughout that module.
Imports, decorators, arbitrary calls,
attribute access, loops, recursion, mutation and unsupported syntax are rejected.
This subset makes the executable boundary decidable; it does not assert purity
of arbitrary Python or other languages. Broader surfaces require a separately
reviewed repository-specific enforcement path before dispatch is admissible.

`.secpal/evidence-agreement-results.json` supplies executable inputs, not a
stored status assertion. Its schema is `secpal-evidence-agreement-execution/v1`
and its only other field is `proofs`. Each proof has exactly:

- `id`, `owner`, and `enforcement`, matching the explicit invariant declarations;
- `left` and `right`, each containing `normalization` and `admission` surface IDs;
- `cases`, a bounded list of objects with `input` and Boolean `expected`.

Every proof includes accepting and rejecting reviewed representations. The left
admission must be the owner's declared surface and the right admission must be
the independent enforcement's surface. The validator freshly executes each
representation through both normalization/admission paths and requires both to
match the reviewed expected decision. It emits source and input digests with
case counts and rereads the evidence before success. No caller-supplied producer,
signature or `status: passed` creates execution authority. Case realism and
semantic sufficiency remain review obligations. Ordinary signed delivery and
Complete Registered Validation authenticate the source candidate separately;
these local agreement facts are not a canonical validation receipt or attestation.

## PR Check Publication And Activation

The unconditional `Evidence Architecture PR Gate` job in `quality.yml` validates
the repository and executes the positive, adversarial and integration suites.
It consumes the canonical Node baseline, independently checked by the maintained
Node baseline validator. Complete Registered Validation includes the same suites.

`sync-required-checks.sh --repo .github --print-pending-checks` reports this
publication identity. The gate is excluded from all activation payloads. Before
a separately authorized operator activates it, that operator must authenticate
the signed hosted candidate, successful actual job execution, and the exact
check identity and producing source. Workflow publication and source acceptance
do not establish live required-check enforcement. Existing protection and
lifecycle gates retain their own authority.

User/system installer activation and live managed-system rollout remain separate
operations. Source tests use temporary repositories and service fixtures; they
do not establish that any live provider, managed host or branch protection changed.
