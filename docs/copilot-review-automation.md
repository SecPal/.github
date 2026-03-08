<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Copilot Review Automation

This document defines the durable, automatable part of the Copilot review workflow.

## Boundary

Repository automation cannot write into the agent's private runtime memory.
The durable substitute is:

- export review threads
- generate lessons artifacts
- resolve fixed threads via GraphQL
- promote repeated findings into instructions, hooks, lint rules, tests, or CI

## CLI

Use [scripts/copilot-review-tool.sh](../scripts/copilot-review-tool.sh).

- `threads`: export Copilot review threads for one PR
- `lessons`: turn one PR's findings into a durable lessons file
- `scan`: walk open non-draft PRs across multiple repositories
- `resolve`: resolve review threads without posting comments

## Preferred Non-Manual Path

The workflow [copilot-review-memory.yml](../.github/workflows/copilot-review-memory.yml) runs this scan automatically for:

- `SecPal/api`
- `SecPal/frontend`
- `SecPal/contracts`
- `SecPal/.github`

It uploads a workflow artifact containing:

- `summary.md`
- one `threads` report per matching PR
- one `lessons` report per matching PR

## Local Usage

```bash
./scripts/copilot-review-tool.sh scan \
  --repo SecPal/api \
  --repo SecPal/frontend \
  --repo SecPal/contracts \
  --repo SecPal/.github \
  --state unresolved \
  --output-dir tmp/copilot-review-memory
```

For single PR work:

```bash
./scripts/copilot-review-tool.sh threads --repo SecPal/api --pr 557 --state unresolved
./scripts/copilot-review-tool.sh lessons --repo SecPal/api --pr 557 --state all
./scripts/copilot-review-tool.sh resolve --thread-id PRRT_example_1
```

## Promotion Rule

If the same Copilot finding appears repeatedly, it should stop living only in artifacts and become an enforced rule in one of these layers:

1. `.github/copilot-instructions.md`
2. `.github/instructions/*.instructions.md`
3. hooks or validators
4. tests or CI
