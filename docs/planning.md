<!--
SPDX-FileCopyrightText: 2025 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Project Planning & Organization

This document explains how SecPal organizes work, tracks progress, and plans features.

## 📊 GitHub Projects

We use **GitHub Projects** (organization-level) for cross-repository planning:

### SecPal Roadmap Project

**URL:** `https://github.com/orgs/SecPal/projects/1` _(to be created)_

**Views:**

1. **📋 Kanban Board:**
   - Backlog (Ideas, not yet prioritized)
   - Discussion Needed (Requires decision before work)
   - Planned (Prioritized, ready for implementation)
   - In Progress (Active work)
   - In Review (PR open, awaiting review)
   - Done (Merged/Completed)

2. **🗓️ Roadmap View:**
   - Timeline view with milestones
   - Target dates for releases
   - Dependencies visualization

3. **📊 Table View:**
   - All issues with custom fields
   - Sortable, filterable

**Custom Fields:**

| Field            | Type          | Values                                                    |
| ---------------- | ------------- | --------------------------------------------------------- |
| Priority         | Single select | P0 (Blocker), P1 (High), P2 (Medium), P3 (Low)            |
| Component        | Single select | API, Frontend, Contracts, Infrastructure, Legal, Security |
| Type             | Single select | Feature, Bug, Documentation, Research, Decision           |
| Effort           | Single select | S (1-2 days), M (3-5 days), L (1-2 weeks), XL (2+ weeks)  |
| Target Milestone | Milestone     | 0.1.0, 0.2.0, 1.0.0, Future                               |
| Status           | Status        | Auto-synced with Kanban columns                           |

## 📁 Repository Organization

### Where to Create Issues

| Topic                    | Repository  | Examples                                |
| ------------------------ | ----------- | --------------------------------------- |
| Backend/API features     | `api`       | "Implement guard shift endpoints"       |
| Frontend features        | `frontend`  | "Add shift calendar view"               |
| API contract changes     | `contracts` | "Add pagination to shift list endpoint" |
| Cross-repo features      | `.github`   | "Digital guard book MVP"                |
| Infrastructure/CI/CD     | `.github`   | "Add performance testing workflow"      |
| Legal/licensing          | `.github`   | "Legal review of CLA"                   |
| Documentation (org-wide) | `.github`   | "Architecture Decision Records"         |
| Security/GHAS            | `.github`   | "Enable secret scanning for all repos"  |

### Label Strategy

**Priority Labels** (all repos):

- `priority: blocker` 🔴 (Blocks release/development)
- `priority: high` 🟠 (Important, should be done soon)
- `priority: medium` 🟡 (Normal priority)
- `priority: low` 🟢 (Nice to have, low urgency)

**Type Labels** (all repos):

- `type: bug` 🐛 (Something broken)
- `type: feature` ✨ (New functionality)
- `type: documentation` 📝 (Docs only)
- `type: enhancement` 💡 (Improvement to existing feature)
- `type: research` 🔬 (Investigation/spike)
- `type: security` 🔐 (Security-related)

**Status Labels** (all repos):

- `status: discussion` 💬 (Needs decision/consensus)
- `status: blocked` 🚧 (Can't proceed, waiting on something)
- `status: ready` ✅ (Ready for implementation)
- `status: wip` 🚧 (Work in progress)

**Component Labels** (repo-specific):

- API: `component: database`, `component: auth`, `component: api`
- Frontend: `component: ui`, `component: routing`, `component: state`
- All: `component: ci/cd`, `component: tests`

**Effort Labels** (all repos):

- `effort: S` (1-2 days)
- `effort: M` (3-5 days)
- `effort: L` (1-2 weeks)
- `effort: XL` (2+ weeks, consider splitting)

**Special Labels**:

- `good first issue` 👋 (For new contributors)
- `help wanted` 🙏 (Community contributions welcome)
- `breaking change` ⚠️ (Requires major version bump)
- `legal` ⚖️ (Requires legal review)

## 🎯 Milestones

### Version Strategy

SecPal follows **Semantic Versioning** (semver):

- `0.x.x` - Pre-1.0 development (breaking changes allowed)
- `1.0.0` - First production release
- `1.x.x` - Backward-compatible features
- `2.0.0+` - Breaking changes

### Current Milestones

**0.1.0 - Foundation** _(Target: TBD)_

- Basic API structure
- Database schema
- OpenAPI contracts
- CI/CD pipelines
- Development environment (DDEV)

**0.2.0 - Guard Book MVP** _(Target: TBD)_

- Event sourcing implementation
- Basic guard shift endpoints
- Guard book entry CRUD
- Simple frontend prototype

**0.3.0 - Authentication & Authorization** _(Target: TBD)_

- User management
- Role-based access control (RBAC)
- JWT authentication
- API key management

**1.0.0 - Production Ready** _(Target: TBD)_

- Complete guard book functionality
- Legal review completed
- Security audit passed
- Performance tested
- Documentation complete
- Production deployment

## 📝 Issue Templates

Located in `.github/ISSUE_TEMPLATE/` (to be created):

1. **Feature Request** (`feature_request.yml`)
2. **Bug Report** (`bug_report.yml`)
3. **Architecture Decision** (`architecture_decision.yml`)
4. **Research/Spike** (`research.yml`)
5. **Security Vulnerability** (private security advisories)

## 🔄 Workflow

### 1. Idea → Issue

1. Check if idea is in `docs/ideas-backlog.md`
2. If actionable, create GitHub Issue in appropriate repo
3. Add to GitHub Project
4. Label with priority, type, component, effort

### 2. Issue → Planning

1. Discuss in issue comments or team meeting
2. If architecture decision needed → Create ADR
3. Move to "Planned" column when ready
4. Assign to milestone

### 3. Implementation

1. Create branch: `feature/short-description` or `fix/short-description`
2. Move issue to "In Progress"
3. Implement with TDD (tests first!)
4. Follow conventional commits
5. Update CHANGELOG.md

### 4. Review → Merge

1. Open PR, link to issue (`Closes #123`)
2. Move to "In Review"
3. Wait for CI checks + code review
4. Merge with squash commit
5. Move to "Done"

### 5. Release

1. Tag release: `v0.1.0`
2. Generate release notes from CHANGELOG
3. Deploy to staging
4. Smoke test
5. Deploy to production

## 📚 Documentation Hierarchy

```
SecPal Documentation
├── README.md (per repo)           # Overview, quick start
├── CONTRIBUTING.md (per repo)     # How to contribute
├── SECURITY.md (per repo)         # Security policies
├── CODE_OF_CONDUCT.md (per repo)  # Community standards
├── CHANGELOG.md (per repo)        # Version history
│
├── .github/docs/                  # Organization-wide docs
│   ├── adr/                       # Architecture Decision Records
│   │   ├── README.md
│   │   └── YYYYMMDD-title.md
│   ├── ideas-backlog.md           # Future ideas
│   ├── planning.md                # This file
│   ├── openapi.md                 # API conventions
│   ├── labels.md                  # Label definitions
│   └── ghas-setup.md              # GitHub Advanced Security
│
├── contracts/docs/                # API specifications
│   └── openapi.yaml
│
└── api/docs/ (future)             # API-specific docs
    └── deployment.md
```

## 🤝 Decision Making (Single Maintainer)

As a single-maintainer project, you (kevalyq) make all decisions. However:

**Best Practices:**

1. **Sleep on big decisions** - Don't rush architecture choices
2. **Write ADRs** - Document reasoning for future you (or future contributors)
3. **Use issues for self-accountability** - Track what you decided and why
4. **Review backlog quarterly** - Are priorities still correct?
5. **Be open to feedback** - Even without contributors, community feedback is valuable

**When to involve others:**

- Legal decisions → Lawyer
- Security architecture → Security review
- Major license changes → Community consultation
- Breaking API changes → Document thoroughly, communicate early

## 🔮 Future: Growing Beyond Single Maintainer

**When external contributors join:**

1. **Update CONTRIBUTING.md** with:
   - How to claim issues
   - Review process
   - Commit rights process

2. **Add CODEOWNERS:**

   ```
   * @kevalyq
   /api/database/ @kevalyq @future-db-expert
   ```

3. **Enable Discussions:**
   - For questions (instead of issues)
   - For RFCs (Request for Comments)
   - For show-and-tell

4. **Regular syncs:**
   - Monthly contributor calls
   - Async updates in Discussions

## 📊 Metrics to Track (Future)

Once the project grows:

- Issue close rate
- PR merge time
- Test coverage
- Documentation coverage
- Dependency update lag
- Security vulnerability response time

## 🛠️ Tools in Use

| Purpose               | Tool                     | Notes                               |
| --------------------- | ------------------------ | ----------------------------------- |
| Planning              | GitHub Projects          | Organization-level                  |
| Issue tracking        | GitHub Issues            | Per repository                      |
| Code review           | GitHub PRs               | Required before merge               |
| CI/CD                 | GitHub Actions           | Workflows in `.github/workflows/`   |
| API docs              | OpenAPI 3.1              | In `contracts/docs/openapi.yaml`    |
| Dependency updates    | Dependabot               | Daily at 04:00 Europe/Berlin        |
| Security scanning     | GitHub Advanced Security | CodeQL, secret scanning, Dependabot |
| License compliance    | REUSE 3.3                | `reuse lint` in quality workflow    |
| Code style (API)      | Laravel Pint (PSR-12)    | Auto-fixes on pre-commit            |
| Code style (Frontend) | Prettier + ESLint        | Auto-fixes on pre-commit            |
| Testing (API)         | PEST                     | `composer test`                     |
| Testing (Frontend)    | Vitest                   | `npm test`                          |
| Static analysis (API) | PHPStan Level Max        | `composer analyse`                  |

## 🚀 Quick Reference

**Create a new feature:**

```bash
# 1. Create issue on GitHub
# 2. Assign to milestone
# 3. Add to Project
# 4. Create branch
git checkout -b feature/short-description

# 5. Implement with tests
# 6. Commit with conventional commits
git commit -m "feat: add guard shift start endpoint"

# 7. Push and open PR
git push -u origin feature/short-description
```

**Weekly planning (suggested):**

1. Review GitHub Project Kanban
2. Move issues between columns
3. Check if any issues are blocked
4. Adjust priorities
5. Update milestone target dates

**Monthly review (suggested):**

1. Review `docs/ideas-backlog.md`
2. Move actionable ideas to issues
3. Archive completed milestones
4. Create next milestone
5. Update roadmap dates

---

**Next Steps:**

1. Create GitHub Project: "SecPal Roadmap"
2. Add issue templates to `.github/ISSUE_TEMPLATE/`
3. Create first issues from ideas
4. Set up labels across all repos
