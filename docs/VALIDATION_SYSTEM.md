<!--
SPDX-FileCopyrightText: 2025-2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# AI Instruction Validation System

## Purpose

SecPal validates the structure and discoverability of repository AI
instructions without requiring different instruction surfaces to repeat the
same prose. Behavioral policy belongs in the appropriate instruction layer;
deterministic file contracts belong in the validator and its regression tests.

## Independent Instruction Layers

Each managed repository can use three independent layers:

1. `AGENTS.md` is the concise, provider-neutral runtime baseline for agents
   working in that repository.
2. `.github/copilot-instructions.md` is a compact GitHub code-review profile.
   It is not generated from and does not mirror `AGENTS.md`.
3. `.github/instructions/*.instructions.md` contains focused path- or
   stack-specific review criteria. These files use `name` and `applyTo`
   frontmatter.

The same invariant should appear in only the narrowest layer that needs it.
Detailed repeatable procedures belong in skills, while rules that can be
enforced deterministically belong in scripts, linters, tests, or CI.

In this repository,
`.github/instructions/github-workflows.instructions.md` is the sole source of
workflow-specific review policy. Its body is not copied into either always-on
instruction file.

## Validator

`scripts/validate-ai-instructions.sh` accepts zero or more repository paths. It
validates the current directory when no path is supplied.

The validator checks:

- required `AGENTS.md` and `.github/copilot-instructions.md` files;
- non-empty, readable UTF-8 Markdown with a top-level heading;
- inline SPDX metadata or an allowed REUSE `.license` sidecar;
- Markdown structure for runtime, review, and focused instruction files;
- opening and closing overlay frontmatter with non-empty `name` and `applyTo`;
- the 32 KiB `AGENTS.md` discovery ceiling.

The validator deliberately does not check:

- equality between runtime and review instructions;
- mirror declarations or authoritative-source phrases;
- copied focused-overlay bodies;
- inheritance-like marker words;
- arbitrary policy keywords or repository-risk phrases.

Those textual checks could prove only that words were present, not that an
agent followed the intended behavior. Focused positive and negative fixtures
instead protect the deterministic contract.

## Markdown Tooling

The validator uses the repository-pinned `markdownlint` binary when
`node_modules` is available, then a globally installed `markdownlint` as a
fallback. It does not download tools. If neither is available, the validator
reports the lint check as skipped; CI installs the committed lockfile and is
the authoritative lint environment.

Run the validator and its regression suite with:

```bash
bash scripts/validate-ai-instructions.sh
bash tests/validate-ai-instructions.sh
```

To validate another checked-out repository with this implementation:

```bash
bash scripts/validate-ai-instructions.sh /path/to/repository
```

The legacy `validate-copilot-instructions.sh` entry point delegates to this
validator whenever a repository has `AGENTS.md`. Its limited no-`AGENTS.md`
path remains a compatibility boundary and does not define the current
three-layer architecture.

## Regression Coverage

`tests/validate-ai-instructions.sh` uses temporary repositories to prove that:

- different valid runtime and review content passes;
- missing, empty, malformed UTF-8, unlicensed, invalid Markdown, malformed
  frontmatter, and oversized instructions fail;
- focused overlays are optional but structurally validated when present;
- mirror phrases, copied overlay content, and policy keywords are unnecessary;
- repository-path arguments continue to work.

`tests/polyscope-rollout.sh` separately proves that rollout preserves an
independent Copilot profile and continues to manage the direct global Codex
`AGENTS.md` symlink without introducing copied runtime sources or instruction
modes.

## Polyscope Behavior

`scripts/polyscope-rollout.py` may discover `AGENTS.md`, the independent
Copilot profile, and focused overlays to build repository metadata and prompts.
It must not generate, reconstruct, or overwrite
`.github/copilot-instructions.md` from `AGENTS.md`.

The editable global Polyscope instructions remain in
`templates/polyscope-codex-AGENTS.md`. The installer links the configured Codex
home's `AGENTS.md` directly to that template. This validation change does not
copy the template or change the symlink lifecycle.

## CI Integration

The repository caller lives at
`.github/workflows/validate-ai-instructions.yml`; sibling repositories consume
`.github/workflows/reusable-ai-instructions.yml`. The reusable workflow checks
out the caller and the selected governance source, installs the governance
lockfile, and runs the validator against the caller.

Cross-repository caller SHA migration is a separate rollout package. Until it
is completed, this instruction-foundation change does not rewrite sibling
callers or their instruction files.

## Troubleshooting

### Required file failure

Create the missing file as an independent instruction layer. Do not copy one
instruction file into another merely to satisfy validation.

### REUSE failure

Add an allowed inline SPDX header near the start of the file or a valid
companion `.license` sidecar. The accepted instruction licenses are `CC0-1.0`
and `AGPL-3.0-or-later`.

### Markdown failure

Use the committed toolchain after dependencies are already installed:

```bash
./node_modules/.bin/markdownlint --config .markdownlint.json \
  AGENTS.md \
  .github/copilot-instructions.md \
  .github/instructions/*.instructions.md
```

### Frontmatter failure

Focused files must begin with a delimited block containing non-empty `name` and
`applyTo` values:

```yaml
---
name: Focused Rules
applyTo: "path/**/*.ext"
---
```

### Discovery-size failure

Move path-specific criteria to focused overlays and repeatable procedures to a
skill. Do not compress unrelated policies into opaque keyword lists.
