<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# SecPal Evidence And External-System Architecture Contract

## Status

Canonical companion to `docs/work-graph-contract.md` for evidence pipelines,
validators, conformance harnesses, migration/check tooling, and other code that
observes or grades external systems. Repository baselines may add stricter
stack-specific rules but MUST NOT weaken this contract.

This contract exists because the same structural failure class recurred in
SecPal cloud conformance after it had already been identified in the historical
Debian evidence work: a large collector combined observation, representation
normalization, provenance checks, admission, and document assembly; semantic
rules were independently restated across multiple boundaries; repository-authored
fixtures encoded the implementation's own assumptions; and real-system failures
collapsed into broad phases that did not identify the failed operation.

## 1. Evidence Pipeline Responsibilities

An evidence or external-system validation pipeline MUST make these responsibilities
explicit:

1. **Observation** performs side effects needed to read the external system. It
   may execute commands, read files, query APIs, or inspect runtime state. It
   emits bounded typed observations and MUST NOT decide conformance.
2. **Representation normalization** converts reviewed external representations
   into canonical facts. It MUST be pure with respect to process execution,
   filesystem mutation/observation, clock, network, and other mutable external
   state.
3. **Admission** consumes canonical facts and returns named contract/invariant
   decisions. It MUST be pure and MUST NOT reach back into the external system.
4. **Assembly** constructs the closed evidence/result document from already
   observed, normalized, or admitted facts. It MUST NOT perform new external
   observation or independently redefine semantic admission rules.

A transport constraint MAY require several responsibilities to live in one
physical file. That does not permit them to collapse semantically. Their public
surfaces and boundaries MUST remain explicit and executable-testable.

A single function or module SHOULD NOT directly own several unrelated external
subsystem domains. When it does, the design requires an explicit architecture
review that either demonstrates one coherent contract or decomposes the
responsibilities before implementation continues.

## 2. Authoritative Invariant Ownership

`docs/work-graph-contract.md` section 11 remains authoritative: every semantic
invariant has exactly one owner. This contract makes the consequence explicit
for evidence systems.

Preparation, collection, normalization, schema validation, admission, cleanup,
or another phase MUST NOT independently reimplement the same semantic rule merely
because they execute at different times.

Sharing the implementation is the default when the trust and transport model
allows it. Independent enforcement at a trust boundary remains valid, but it
MUST name the authoritative invariant and MUST have executable agreement evidence
when the two boundaries cannot share implementation. Agreement evidence must
show that the independent enforcement points accept and reject the same reviewed
real-world values after their respective normalization.

A fix that corrects one enforcement point MUST include a search/audit of other
enforcement points for the same invariant before another real-system run is
authorized.

## 3. Realistic And Real-System Representation Evidence

Repository-authored fixtures prove repository behavior. They do not prove that
an external provider, operating system, framework, database, runtime, protocol,
or API emits the representation the repository assumed.

For a seam whose risk is representation compatibility, tests MUST start from a
reviewed realistic representation and exercise the complete applicable path:

`external representation -> normalization -> closed schema -> independent validation/admission`

Where the owning contract promises a real-system result, reviewed real-system
evidence remains mandatory under `docs/work-graph-contract.md` section 9.

A repeated real-system mismatch between authored fixtures and actual external
representations is an architecture signal. Before another external run, the
owning work MUST audit adjacent representations, bounds, parsers, and duplicate
invariant implementations for the same failure class. Adding one isolated
compatibility branch and immediately rerunning is insufficient.

## 4. Diagnosable External-System Runs

Before a paid, destructive, privileged, or otherwise costly real external-system
run, every reachable fallible trusted operation before the promised result MUST
have a closed bounded diagnostic identity sufficient to locate the semantic
operation that failed.

A broad phase such as `bootstrap`, `evidence-collection`, `migration`, or
`validation` is insufficient when it contains multiple independently fallible
operations.

The diagnostic contract MUST remain bounded and non-secret. It MUST NOT solve
observability by retaining arbitrary stdout/stderr, environment dumps, secrets,
credentials, or attacker-controlled strings.

If repository validation cannot prove that every reachable failure boundary is
locatable, the external-system run MUST NOT be dispatched. The work is not ready
for real-system execution yet.

## 5. Anti-Loop Replanning Rule

A sequence of real-system runs that repeatedly discovers adjacent representation,
parser, duplicated-invariant, hidden-boundary, or insufficient-diagnostic defects
MUST NOT continue as an unbounded patch/rerun loop.

Before the next run, classify whether the failures share a structural cause. If
they do, the structural correction is a prerequisite under the canonical
replanning rules. The current real-system leaf is blocked until that prerequisite
is delivered or its own contract is legitimately replanned.

The purpose is not to forbid iterative integration work. The purpose is to stop
using a paid or destructive external system as a one-assertion-at-a-time debugger
for architecture that repository validation can make reviewable first.

## 6. Repository Enforcement

Repositories containing evidence or external-system tooling SHOULD enforce the
applicable parts of this contract in repository preflight rather than relying on
agent memory or issue prose alone. Proportionate enforcement includes:

- purity tests or guards for normalization/admission;
- duplicate-invariant agreement tests;
- cross-layer representation tests;
- mutation tests proving architecture checks are live;
- static or behavioral checks that every external observation maps to a closed
  diagnostic operation;
- a dispatch/preflight gate that refuses real-system execution when a reachable
  failure is only identifiable by a broad phase.

The enforcement mechanism is repository-specific. The semantics above are not.

## Historical Source Evidence

The contract generalizes lessons already documented in `SecPal/deployment`:

- deployment issue #64 identified the structural drift caused by combining
  collection, representation normalization, provenance checks, and admission,
  and by restating the same contract across collector, schema, validators,
  tests, and documentation;
- deployment epic #67 made one authoritative definition per semantic invariant
  a binding invariant;
- deployment issue #72 recorded that repository-authored fixtures cannot replace
  replay of reviewed real-system evidence;
- deployment PRs #63, #66, #73, and #74 contain the associated Debian evidence
  and review history;
- the Rocky replacement epic #117 retained those lessons but sequenced generic
  layer/purity reapplication after semantic evidence and scoped #120, #121, and
  #122 to the later #119 workload evidence path, leaving #118 host evidence able
  to recreate the same structural problem;
- Rocky PRs #145 and #146 successively exposed and repaired adjacent unbounded
  preparation failures; #147 added more granular diagnostics after those broad
  real-run failures; #148 fixed real Podman digest representation semantics;
  #149 then fixed the same semantic invariant independently duplicated in the
  preparation collector; real run `33021568439` subsequently failed again only
  at the broad `evidence-collection` boundary.

These historical references are evidence for why the organization-wide rule
exists. They do not import Debian, Podman, Rocky, cloud-provider, or deployment
semantics into unrelated repositories.
