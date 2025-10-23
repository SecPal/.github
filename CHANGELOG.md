<!-- SPDX-FileCopyrightText: 2025 SecPal -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **copilot-instructions.md optimization (2025-10-23):**
  - Compressed from 1,047 lines to 393 lines (62% reduction) for AI efficiency
  - Removed Change History section (historical information irrelevant for AI)
  - Restructured to terse, constraint-based format (AI-only optimization)
  - Added AI Self-Check Protocol with trigger events and validation checklist
  - Added Multi-Repo Coordination strategy (contracts → api/frontend)
  - Added Breaking Changes Process (0.x.x vs 1.x.x+ distinction)
  - Added CHANGELOG Maintenance guidelines (Keep a Changelog format)
  - Expanded Critical Rules from 6 to 10 (test coverage, commit signing, documentation, templates)
  - Added Database Strategy (PostgreSQL prod, SQLite test, reversible migrations)
  - Added API Guidelines (REST, JSON, URL versioning, JWT authentication)
  - Enhanced Security section (SECURITY.md reference, response timelines)
  - Made Copilot Review mandatory (was "recommended")
  - Updated last modified date to 2025-10-23

### Added

- Nothing yet

### Deprecated

- Nothing yet

### Removed

- Nothing yet

### Fixed

- Nothing yet

### Security

- Nothing yet

## [0.0.1] - 2025-01-23

### Added

#### Documentation & Governance

- Initial repository structure and governance documentation
- `README.md` with project overview and setup instructions
- `CONTRIBUTING.md` with detailed contribution guidelines
- `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1)
- `SECURITY.md` with vulnerability disclosure process and security policies
- `LICENSE` files for AGPL-3.0-or-later, CC0-1.0, and MIT
- `copilot-instructions.md` with comprehensive development guidelines (1,218 lines)
  - Core Development Philosophy (6 non-negotiable principles)
  - Versioning & Release Strategy (Semantic Versioning 2.0.0)
  - Licensing Strategy with dependency compatibility matrix
  - Dependency Management strategy (Dependabot configuration)
  - Repository Visibility policy (Public by default)
  - Local vs CI Quality Gate Enforcement (3-stage gates)
  - PR Size & Scope Discipline ("One PR = One Topic" rule)
  - Branch Protection Rules and merge strategy

#### Templates

- Pull Request template with quality checklist and "One PR = One Topic" enforcement
- 5 Issue Templates:
  - Bug Report (structured, severity-based)
  - Feature Request (with priority assessment)
  - Documentation (improvement tracking)
  - Security (responsible disclosure workflow)
  - Config/Infrastructure (build, CI/CD, dependencies)
- Issue template configuration (`.github/ISSUE_TEMPLATE/config.yml`)

#### CI/CD & Automation

- Dependabot configuration for 5 ecosystems:
  - GitHub Actions
  - npm (JavaScript/TypeScript)
  - Composer (PHP)
  - pip (Python)
  - Docker (Container images)
- Daily dependency checks at 04:00 CET
- Auto-update strategy for all version types (patch, minor, major)

#### Quality Standards

- REUSE 3.3 compliance setup with SPDX headers
- Documentation for REUSE.toml (replacing deprecated .reuse/dep5)
- Pre-commit and pre-push hook guidelines
- Comprehensive linting standards (Prettier, Markdownlint, ESLint, PHPStan)

#### Technology Stack Documentation

- Backend: Laravel 12, PHP 8.4, Pest, PHPStan (level: max)
- Frontend: React, Node 22.x, TypeScript (strict), Vite, ESLint, Vitest
- API: OpenAPI 3.1 as single source of truth
- Version Control: Git with signed commits, linear history

### Changed

- Nothing (initial release)

### Security

- Secret scanning enabled with push protection
- Dependabot security updates prioritized
- CodeQL analysis configured (JavaScript/TypeScript only, PHP excluded)
- Branch protection enforced with required status checks
- All repositories public by default (AGPL compliance, transparency)

### Notes

This is the foundational release establishing:

- Project governance and contribution workflows
- Quality gates and testing philosophy (TDD mandatory)
- Licensing strategy (AGPL-3.0-or-later for code, CC0-1.0 for config/docs, MIT for scripts)
- Security-first development practices
- Semantic Versioning commitment starting at 0.0.1

**Development Phase:** This is a 0.x.x release. APIs may change without notice. Breaking changes are allowed in minor version bumps. No backward compatibility guarantees until 1.0.0.

**Open Discussions:**

- [Issue #36](https://github.com/SecPal/.github/issues/36): Dependabot auto-merge implementation strategy
- [Issue #37](https://github.com/SecPal/.github/issues/37): Dependabot check frequency (daily vs weekly)
- [Issue #38](https://github.com/SecPal/.github/issues/38): AGPL-3.0-or-later license strategy review
- [Issue #39](https://github.com/SecPal/.github/issues/39): TDD mandatory policy vs exploration exceptions

---

## Version History

- **0.0.1** (2025-01-23) - Initial foundation and governance

[Unreleased]: https://github.com/SecPal/.github/compare/v0.0.1...HEAD
[0.0.1]: https://github.com/SecPal/.github/releases/tag/v0.0.1
