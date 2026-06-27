<!--
SPDX-FileCopyrightText: 2025-2026 SecPal
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# SecPal Organization

[![Code Coverage](https://codecov.io/gh/SecPal/api/branch/main/graph/badge.svg?flag=backend)](https://codecov.io/gh/SecPal/api)
[![Code Coverage](https://codecov.io/gh/SecPal/frontend/branch/main/graph/badge.svg?flag=frontend)](https://codecov.io/gh/SecPal/frontend)

This repository contains general project documentation, settings, and community health files for the [SecPal organization](https://github.com/SecPal).

## About SecPal

SecPal is the operations software for German private security services. Everything the day-to-day operation needs — in one system that just works.

## Repositories

- [`.github`](https://github.com/SecPal/.github): Organization-wide settings and documentation
- [`api`](https://github.com/SecPal/api): Laravel backend API
- [`android`](https://github.com/SecPal/android): React/TypeScript Android app via Capacitor
- [`changelog`](https://github.com/SecPal/changelog): Public changelog site for SecPal releases
- [`contracts`](https://github.com/SecPal/contracts): OpenAPI 3.1 API specifications
- [`frontend`](https://github.com/SecPal/frontend): React/TypeScript frontend application
- [`GuardGuide`](https://github.com/SecPal/GuardGuide): Laravel/React operations platform for GuardGuide
- [`guardguide.de`](https://github.com/SecPal/guardguide.de): Public website for GuardGuide
- [`secpal.app`](https://github.com/SecPal/secpal.app): Astro public website

## Multi-Repository Workspace Setup

For setting up a local development environment with all repositories, see [WORKSPACE_SETUP.md](WORKSPACE_SETUP.md).

## Development Setup

### Feature Management & Project Tracking

SecPal uses an issue-first planning model:

- **🎫 GitHub Issues**: Canonical source of truth for active work and deferred follow-up
- **🏷️ Labels and Milestones**: Priority, type, component, and release grouping
- **🧭 ADRs**: Durable records for planning and architecture decisions
- **📊 Project Board**: Optional mirrored view for cross-repository status tracking

**Quick Start:**

```bash
# Read the canonical planning guide
cat docs/planning.md

# Optional: read the board mirror guide
cat docs/project-board-integration.md
```

**Workflow:**

1. **Open or refine an issue** in the repository that owns the work
2. **Add labels and milestone** to make priority and delivery intent explicit
3. **Split multi-PR work** into an epic plus sub-issues before implementation
4. **Open a draft PR** linked to the issue; board automation mirrors progress only when enabled

See [docs/planning.md](docs/planning.md) for the canonical process and [docs/project-board-integration.md](docs/project-board-integration.md) for the optional board layer.

### 🤖 Automated Project Board Management

SecPal uses automated workflows to manage the optional [SecPal Roadmap](https://github.com/orgs/SecPal/projects/1) project board. Issues and pull requests are automatically added and their status is updated based on labels, PR state, and review activity, but the board remains a mirrored view rather than the planning source of truth.

**Status Flow:**

```mermaid
graph LR
    Enhancement[Enhancement Issue] --> Ideas[💡 Ideas]
    CoreFeature[Core Feature] --> Planned[📋 Planned]
    Blocker[Priority: Blocker] --> Backlog[📥 Backlog]
    Ideas --> Discussion[💬 Discussion]
    Discussion --> Planned
    Planned --> InProgress[🚧 In Progress]
    InProgress --> InReview[👀 In Review]
    InReview --> Done[✅ Done]
    InReview -.convert to draft.-> InProgress
    Any --> WontDo[🚫 Won't Do]
```

**Key Features:**

- **Automatic issue assignment** to project board based on labels
- **Draft PR workflow**: Draft PRs → In Progress, Ready PRs → In Review
- **Single-maintainer support**: Convert to draft to signal "changes needed"
- **Auto-close on merge**: Linked issues automatically marked as Done

**Quick Commands:**

```bash
# Create enhancement (→ Ideas)
gh issue create --label "enhancement" --title "..."

# Create core feature (→ Planned)
gh issue create --label "core-feature" --title "..."

# Create blocker (→ Backlog)
gh issue create --label "priority: blocker" --title "..."

# Draft PR workflow (recommended)
tmpfile=$(mktemp "${TMPDIR:-/tmp}/pr-body.XXXXXX")
trap 'rm -f "$tmpfile"' EXIT
printf '%s\n' "Closes #123" > "$tmpfile"
gh pr create --draft --body-file "$tmpfile"  # → In Progress
gh pr ready <PR>                            # → In Review
gh pr ready --undo <PR>                     # → In Progress (changes needed)
gh pr merge <PR> --squash                   # → Done (auto-closes issue)
```

**Documentation:**

- [📖 Project Automation Guide](docs/workflows/PROJECT_AUTOMATION.md) - Complete documentation
- [📋 Quick Reference](docs/workflows/QUICK_REFERENCE.md) - Daily usage commands
- [🚀 Rollout Guide](docs/workflows/ROLLOUT_GUIDE.md) - Deployment to repositories

See [docs/project-board-integration.md](docs/project-board-integration.md) for board-specific guidance and [docs/planning.md](docs/planning.md) for the canonical planning model.

### Pre-commit Hooks

We use pre-commit hooks to ensure code quality before commits are made. This catches issues locally before CI/CD runs.

**Installation:**

```bash
# Install pre-commit (if not already installed)
pip install pre-commit
# or: brew install pre-commit

# Run the setup script
./scripts/setup-pre-commit.sh
```

**Manual Usage:**

```bash
# Run all hooks manually
pre-commit run --all-files

# Update hooks to latest versions
pre-commit autoupdate
```

**Included Checks:**

- REUSE 3.3 compliance

### Pre-push Hooks

We use a pre-push hook to run comprehensive quality checks before pushing to GitHub. This includes formatting, linting, testing, and PR size checks.

**Installation:**

Run the setup scripts to install both pre-commit and pre-push hooks:

```bash
# Install pre-commit hooks (formatting, linting, REUSE compliance)
./scripts/setup-pre-commit.sh

# Install pre-push hook (comprehensive quality checks)
./scripts/setup-pre-push.sh
```

The hooks are installed as symlinks in `.git/hooks/`, ensuring they automatically update when scripts change.

**What it checks:**

- Code formatting (Prettier, markdownlint)
- REUSE 3.3 compliance
- Workflow linting coverage via pre-commit hooks and CI (local preflight does not invoke `actionlint` directly because it has caused hangs in some environments)
- Language-specific checks:
  - **PHP/Laravel**: Pint, PHPStan, tests
  - **Node.js**: ESLint, TypeScript, tests, npm audit
  - **OpenAPI**: Spectral/Redocly linting
- PR size limit (600 lines, configurable with `.preflight-allow-large-pr`)

**Manual Usage:**

```bash
# Run preflight checks manually
./scripts/preflight.sh

# Optional local workflow lint (prefer this to avoid environment-specific hangs)
pre-commit run actionlint --all-files
# or, if you need a direct run: timeout 30 actionlint

# Bypassing hooks is not allowed
# Fix the failing check instead of skipping it
```

Install `actionlint` via your package manager or a release binary if you want to run it outside pre-commit.

**Included Checks (pre-commit):**

- Prettier formatting (Markdown, YAML, JSON)
- Markdownlint
- yamllint
- actionlint (GitHub Actions workflows)
- ShellCheck (shell scripts)
- File size limits
- Trailing whitespace
- Line ending normalization

### 🤖 AI Instructions

SecPal uses a provider-neutral **AI instructions system**:

1. **Authoritative repo baseline** (`AGENTS.md` in each repository)
2. **Focused overlays** (`.github/instructions/*.instructions.md` where supported)
3. **Copilot compatibility mirror** (`.github/copilot-instructions.md`, generated or maintained as a mirror where tooling expects that path)

**All repository-specific runtime baselines MUST keep `AGENTS.md` authoritative.**

#### Setup Model

When setting up AI instructions in a new repository:

1. **Create or update** `AGENTS.md` as the authoritative baseline
2. **Add focused overlays** under `.github/instructions/` only when path- or stack-specific rules need to stay separate
3. **Keep `.github/copilot-instructions.md` aligned** as a compatibility mirror for tools that auto-load that path
4. **Create a PR** with title pattern: `docs: align ai instructions`

**Example Implementations:**

- [SecPal/api #76](https://github.com/SecPal/api/pull/76) ✅ Merged
- [SecPal/frontend #54](https://github.com/SecPal/frontend/pull/54) ✅ Merged
- [SecPal/contracts #38](https://github.com/SecPal/contracts/pull/38) ✅ Merged

#### Validation

The AI runtime baseline is validated in CI:

```bash
bash .github/scripts/validate-ai-instructions.sh
```

See: [`.github/workflows/validate-ai-instructions.yml`](.github/workflows/validate-ai-instructions.yml)

#### Why This Matters

**Without a clear authoritative baseline:** AI assistants might read a compatibility mirror or a partial overlay without the full repo runtime policy, leading to:

- Quality gate bypasses
- Missing review or governance expectations
- TDD policy violations
- Security requirement oversights

**With `AGENTS.md` as source of truth:** AI tooling gets one stable runtime baseline first, with overlays and compatibility mirrors only extending or reflecting it.

## Build & Test Commands

Quick reference commands for local development across SecPal projects.

### PHP/Laravel Backend

```bash
# Dependencies
composer install --no-interaction --no-progress --prefer-dist --optimize-autoloader

# Code Style Check
./vendor/bin/pint --test

# Static Analysis
./vendor/bin/phpstan analyse --level=max

# Tests (parallel)
php artisan test --parallel
```

### Node.js/React Frontend

```bash
# Dependencies (use exact versions)
npm ci
# or for pnpm projects:
pnpm install --frozen-lockfile

# Linting
npm run lint

# Type Checking
npm run typecheck
# or:
npx tsc --noEmit

# Tests
npm test
# or:
pnpm test
```

### OpenAPI Validation

```bash
# Lint OpenAPI spec
npx @stoplight/spectral-cli lint docs/openapi.yaml
```

### Code Formatting (all files)

```bash
# Check formatting
npx prettier --check '**/*.{md,yml,yaml,json,ts,tsx,js,jsx}'

# Auto-fix
npx prettier --write '**/*.{md,yml,yaml,json,ts,tsx,js,jsx}'
```

### REUSE Compliance

```bash
# Install REUSE tool
pip install reuse

# Validate compliance
reuse lint

# Add missing headers
reuse annotate --copyright "SecPal" --license "AGPL-3.0-or-later" <file>
```

## License

### Dual-Licensing Model

SecPal projects use a **dual-licensing** model:

#### 1. Open Source License (AGPL-3.0-or-later)

All projects are licensed under the [AGPL-3.0-or-later](LICENSES/AGPL-3.0-or-later.txt) for:

- ✅ **Open source projects** that comply with AGPL terms
- ✅ **Personal use** and experimentation
- ✅ **Educational purposes**
- ✅ **Community contributions**

**Key AGPL Requirements:**

- Distribute source code to users (including network users)
- Share modifications under AGPL
- Preserve copyright and license notices

#### 2. Commercial License

For use cases **incompatible with AGPL**, we offer commercial licenses that allow:

- ❌ **No requirement** to disclose source code
- ❌ **No copyleft obligations** for your applications
- ✅ **Proprietary** product integration
- ✅ **SaaS** offerings without AGPL compliance
- ✅ **Commercial support** and maintenance

**Interested in a commercial license?** Contact us at [legal@secpal.app](mailto:legal@secpal.app)

---

### Contributing

By contributing to SecPal projects, you agree to our [Contributor License Agreement (CLA)](CLA.md), which:

- Grants us rights to distribute your contributions under **both** licensing models
- Allows you to **retain copyright** ownership
- Ensures your work can benefit both open source and commercial users

**CLA Signing Process:**

When you submit your first pull request, [CLA Assistant](https://cla-assistant.io/) will automatically comment with instructions. Simply:

1. Click the link in the comment
2. Sign in with GitHub (OAuth)
3. Click "I agree" to sign the CLA
4. Your PR status will update automatically

All signatures are stored securely in a GDPR-compliant database hosted in Europe.

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

---

### For Repository Maintainers

To enable CLA checks in your SecPal repository:

1. Go to [CLA Assistant](https://cla-assistant.io/) and sign in with GitHub
2. Click "Configure CLA"
3. Select your repository from the dropdown
4. Link it to the SecPal CLA Gist (ask an organization admin for the Gist URL)
5. Add automated bot identities such as `dependabot[bot]`, `dependabot-preview[bot]`, `copilot-swe-agent`, and `cursoragent` to the CLA Assistant allowlist
6. Verify that `cla/check` passes on a recent automated PR instead of blocking on signature
7. If the live CLA Assistant state does not match the documented setup, track that drift in `SecPal/.github` before closing the repository-local symptom issue
8. Done! CLA Assistant will automatically monitor all pull requests

**Unlike the previous GitHub Action approach, no workflow files are needed** – CLA Assistant uses GitHub webhooks directly.

All CLA signatures are stored centrally in a secure database (Azure Europe, GDPR-compliant).

---

For full license information, see the [LICENSES](LICENSES/) directory.
