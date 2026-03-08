<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Copilot Review Automation

This document turns the Copilot review process into a repeatable workflow with minimal manual work.

## Important Boundary

The agent's private runtime memory is not writable from repository scripts or GitHub Actions.
What can be automated reliably is the durable equivalent:

- review-thread collection
- lesson extraction into repo-owned Markdown artifacts
- GraphQL-based thread resolution
- promotion of repeated findings into instructions, hooks, lint rules, tests, and CI

## Automation Tool

Use [scripts/copilot-review-tool.sh](../scripts/copilot-review-tool.sh).

It supports three subcommands:

- `threads`: fetch Copilot review threads from a PR
- `lessons`: turn review findings into a durable lessons artifact
- `resolve`: resolve review threads via GraphQL without posting comments

## Recommended Workflow

### 1. Export unresolved findings

```bash
./scripts/copilot-review-tool.sh threads \
  --repo SecPal/api \
  --pr 557 \
  --state unresolved \
  --format markdown \
  --output docs/copilot-review-memory/api-pr-557-threads.md
```

### 2. Generate durable lessons

```bash
./scripts/copilot-review-tool.sh lessons \
  --repo SecPal/api \
  --pr 557 \
  --state all \
  --output docs/copilot-review-memory/api-pr-557-lessons.md
```

This is the persistent replacement for chat-only memory.

### 3. Promote repeated findings

Use the generated lessons file to move recurring findings into one of these layers:

1. `.github/copilot-instructions.md`
2. `.github/instructions/*.instructions.md`
3. pre-commit or pre-push hooks
4. lint rules or validators
5. tests
6. CI workflows

Promotion order matters: prefer deterministic enforcement over chat memory.

### 4. Resolve fixed threads

```bash
./scripts/copilot-review-tool.sh resolve \
  --thread-id PRRT_example_1 \
  --thread-id PRRT_example_2
```

## Minimal Manual Overhead

The goal is not "no human judgment". The goal is "one command instead of a hand-driven process".

The safe automation boundary is:

- automatically fetch findings
- automatically write durable lessons
- automatically resolve fixed threads

The part that should stay gated by judgment is deciding whether a finding becomes:

- an instruction
- a hook
- a lint rule
- a test
- a CI rule

## Suggested Integration Points

### Local alias

```bash
alias copilot-lessons='./scripts/copilot-review-tool.sh lessons'
alias copilot-threads='./scripts/copilot-review-tool.sh threads'
alias copilot-resolve='./scripts/copilot-review-tool.sh resolve'
```

### VS Code task

Create a local task that runs `copilot-review-tool.sh lessons` for the current PR.

### GitHub Actions

Good future step:

- trigger on `pull_request_review` or `pull_request_review_thread`
- fetch Copilot findings automatically
- upload lessons as an artifact
- optionally fail when repeated findings exceed a threshold

## Best Practice

If the same Copilot finding appears twice, it should stop being only a lesson and become an enforced rule.

That is the real long-term memory mechanism.
