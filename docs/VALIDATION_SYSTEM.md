<!--
SPDX-FileCopyrightText: 2025-2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# AI Instruction Validation System

## Purpose

SecPal validates the structure and discoverability of repository AI
instructions without requiring different instruction surfaces to repeat the
same prose. Behavioral policy belongs in the appropriate instruction layer;
deterministic file contracts belong in the validator and its regression tests.

## Independent Instruction Layers

Each managed repository uses two required independent files and may add focused
overlays as a third layer. One required file may never replace the other:

1. `AGENTS.md` is the required, concise, provider-neutral runtime baseline for
   agents working in that repository.
2. `.github/copilot-instructions.md` is a compact GitHub code-review profile.
   It is required, review-only, and is not generated from or interpreted as a
   replacement for `AGENTS.md`.
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
- one complete policy-appropriate SPDX expression in the authoritative inline
  metadata or REUSE `.license` sidecar for every runtime, review, and focused
  instruction file, while rejecting duplicate or conflicting declarations in
  either source: plain `AGPL-3.0-or-later` for the migrated `.github` baseline,
  the intentionally `CC0-1.0` API baseline, plain `AGPL-3.0-or-later` for other
  managed baselines, and exact deliberate `AGPL-3.0-or-later`, `Apache-2.0`,
  `CC0-1.0`, or `MIT` expressions for focused overlays;
- Markdown structure for runtime, review, and focused instruction files;
- syntactically valid YAML overlay frontmatter with opening and closing
  delimiters plus non-empty string `name` and `applyTo` values;
- repository-local regular files and directories rather than symlinks for all
  instruction discovery paths;
- the 32 KiB discovery ceiling for each required instruction file.

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
fails with a blocked-tool message and a nonzero result. CI installs the
committed lockfile and is the authoritative lint environment. Focused-overlay
frontmatter is parsed with the repository-pinned `js-yaml`. When focused
overlays exist, a missing parser also fails closed.

Run the validator and its regression suite with:

```bash
bash scripts/validate-ai-instructions.sh
bash tests/validate-ai-instructions.sh
```

To validate another checked-out repository with this implementation:

```bash
bash scripts/validate-ai-instructions.sh /path/to/repository
```

Repository-path mode derives identity independently for each target and clears
ambient `GITHUB_REPOSITORY`, `SECPAL_REPOSITORY_NAME`, and `REPO_TYPE` values
before recursion. Without a path argument, canonical callers may supply trusted
identity through `GITHUB_REPOSITORY` or `SECPAL_REPOSITORY_NAME`. The legacy
`REPO_TYPE` hint remains available for local compatibility, but cannot select
the API policy unless the repository has the exact `secpal/api` manifest.
Trusted `SecPal/deployment` identity is reported explicitly and uses the same
strict plain-AGPL baseline as other migrated managed repositories.

## Regression Coverage

`tests/validate-ai-instructions.sh` uses temporary repositories to prove that:

- different valid runtime and review content passes;
- managed runtime and review baselines require plain `AGPL-3.0-or-later`, the
  API baseline requires its intentional `CC0-1.0`, and focused overlays retain
  exact `AGPL-3.0-or-later`, `Apache-2.0`, `CC0-1.0`, and `MIT` support;
- the obsolete expression
  `AGPL-3.0-or-later AND LicenseRef-SecPal-Attribution`, duplicate identifiers,
  and a wrong repository-baseline license fail;
- the migrated `SecPal/deployment` identity accepts plain-AGPL runtime and
  review instructions, is reported explicitly, and rejects the obsolete
  attribution expression;
- API, frontend-with-Composer, historical GuardGuide, and `guardguide.de` fixtures exercise
  trusted repository identity, path-local fallback detection, and legacy type
  hints so ambient identity and misleading manifest values cannot select
  another repository's licensing policy;
- missing, empty, malformed UTF-8, unlicensed, invalid Markdown, malformed
  frontmatter, and oversized instructions fail;
- focused overlays are optional but structurally validated when present;
- mirror phrases, copied overlay content, and policy keywords are unnecessary;
- repository-path arguments continue to work.

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

Add one policy-appropriate inline SPDX header near the start of the file or a
valid companion `.license` sidecar. When both sources declare a license, each
must contain exactly one identical expression. Managed baselines require
`AGPL-3.0-or-later`; the API requires its intentional `CC0-1.0`. Focused
overlays may retain an intentional exact
`AGPL-3.0-or-later`, `Apache-2.0`, `CC0-1.0`, or `MIT` expression. Longer
expressions that merely begin with one of those identifiers are rejected.

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
