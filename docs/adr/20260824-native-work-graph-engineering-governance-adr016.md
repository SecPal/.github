<!-- SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0 -->

# ADR-016: Native Work-Graph and Engineering Governance

**Status:** Accepted
**Date:** 2026-08-24
**Decision authority:** SecPal architecture rebaseline (August 2026)

## Context

Issue-first planning needs one durable, GitHub-native model rather than competing body and board mirrors.

## Binding decision

GitHub-native parent/sub-issue relations are authoritative containment; native dependencies are the only hard blockers; native sibling order is preferred, non-blocking order. Nodes are Epics, Sub-Epics, and leaves. Epics and Sub-Epics receive no implementation PR. A leaf carries one independently reviewable contract and at most one primary delivery PR.

`READY`, `ACTIVE`, `DONE`, execution claims, deterministic `NEXT`, and closure semantics are defined normatively by [the work-graph contract](../work-graph-contract.md). A dependency is satisfied only when its target is closed `completed`; superseded work closes `not planned` and does not satisfy it. Missing, cyclic, malformed, or unresolvable graph input fails closed. Markdown/body/project-board graphs are non-authoritative mirrors.

## Invariants and boundaries

- Assignment is not an execution claim.
- Issue-first planning remains binding; a Project board is a mirror only.
- Containment is neither ordering nor blocking.

## Consequences

Work can be selected and audited consistently across repositories; graph mirrors cannot silently alter delivery state.

## Relationships

Refines ADR-013; it does not supersede ADR-013. Source: [#668](https://github.com/SecPal/.github/issues/668), [#717](https://github.com/SecPal/.github/issues/717).
