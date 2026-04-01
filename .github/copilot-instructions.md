<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# SecPal Copilot Instructions

These instructions are authoritative when working inside the `.github` repository itself.
Other repositories must keep their own self-contained runtime instructions.

## Always-On Rules

- Run `git status --short --branch` before any write action. Never start implementation on local `main`, and stop if a dirty non-`main` branch contains unrelated work.
- Keep one topic per change, fail fast, and never use bypasses such as `--no-verify` or force-push.
- Update `CHANGELOG.md` for real fixes, features, and breaking changes in the same change set.
- Create a GitHub issue immediately for out-of-scope bugs, technical debt, missing tests, documentation gaps, and actionable warnings you cannot fix now.
- Keep GitHub-facing communication in English and reference files and lines instead of pasting large code blocks.
- Treat warnings, audit findings, and deprecations as actionable. Fix them in scope or track them immediately.
- Keep `SPDX-FileCopyrightText` years current in edited files or companion `.license` sidecars.
- Never reply to Copilot review comments with GitHub comment tools. Fix the code, push, and resolve threads
  using the approved non-comment workflow (`docs/copilot-review-automation.md` or `scripts/copilot-review-tool.sh`).
- Use EPIC plus sub-issues before starting work that will span more than one PR.

## Required Validation

Before any commit, PR, or merge, announce the checklist you are executing and stop on the first failed item.
At minimum verify:

- the smallest relevant validation for the touched area passed, and `./scripts/preflight.sh` ran for substantial governance or workflow changes
- `CHANGELOG.md` was updated for real changes
- commits are GPG-signed
- REUSE compliance was checked when changed files require it
- the local 4-pass review was completed
- no bypass was used

## Local Review Standard

Run these four passes before creating a PR:

1. Comprehensive review: correctness, tests, docs, no stray TODOs.
2. Deep-dive review: domain policy, licensing, security-sensitive patterns.
3. Best-practices review: hidden files, governance docs, package metadata, workflow hygiene.
4. Security review: explicit permissions, secret handling, ignore rules, automation safety.

Create PRs as draft first. Mark them ready only after local review finds zero issues.

## Domain Policy

Use only these domains and identifiers:

- `secpal.app` for the public homepage and real email addresses
- `api.secpal.dev` for the live API host
- `app.secpal.dev` for the live PWA/frontend host
- `secpal.dev` for dev, staging, testing, and examples
- `app.secpal.app` only as the Android application identifier

Treat `api.secpal.app` and `app.secpal.app` as deprecated web hosts.

## Repository Conventions

- This repository is not versioned; keep its changelog chronological.
- Hidden files and automation files are first-class source artifacts.
- For GitHub workflows, set explicit permissions, set `timeout-minutes` on every job, pin external actions, and never expose secrets in logs.
- Workflow templates for other repositories live in `workflow-templates/`.
  Reusable workflow definitions live in `.github/workflows/reusable-*.yml` and are invoked via `uses:`.
- Keep changes repo-local, minimal, and aligned with the existing governance and automation patterns.
