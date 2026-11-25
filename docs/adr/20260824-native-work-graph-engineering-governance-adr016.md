<!-- SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0 -->

# ADR-016: Native Work-Graph and Engineering Governance

**Status:** Accepted for native issue planning
**Date:** 2026-08-24
**Decision authority:** SecPal maintainers

**Decision provenance:** This ADR records architecture decisions deliberately
adopted during the August 2026 rebaseline. 2026-08-24 is the durable ADR record
date, not an assertion that this PR first made those decisions.

## Context

Issue-first planning needs one durable, GitHub-native model rather than competing body and board mirrors.

## Binding decision

GitHub Issues own current work and deferred follow-up. Milestones group
release and roadmap intent, labels classify work, and ADRs record durable
architecture decisions. The public roadmap uses a curated, public-safe subset
of issue and milestone information.

GitHub-native parent/sub-issue relationships own containment. A native dependency
blocks only the work that actually requires it. Native sibling order gives a
preference, and assignment does not claim execution.

The [work-graph contract](../work-graph-contract.md) defines read-only resolution
and completion semantics. GitHub pull requests, reviews, checks and protection
rules own delivery.

## Consequences

Work can be selected and audited consistently across repositories; graph
mirrors cannot silently alter delivery state. Work that needs a different graph
semantic must use an explicit architecture decision, rather than a leaf issue
or implementation convenience.

## Relationships

Issue-first planning was accepted in [#354](https://github.com/SecPal/.github/issues/354). Its native relationships and engineering boundaries were refined in [#668](https://github.com/SecPal/.github/issues/668) and [#717](https://github.com/SecPal/.github/issues/717).
