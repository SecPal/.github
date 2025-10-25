<!--
SPDX-FileCopyrightText: 2025 SecPal
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# GitHub Labels - Organization Standards

Organization-wide label standards for all SecPal repositories.

## Purpose

Consistent labels across all repositories enable:

- Better issue/PR tracking and filtering
- Clear communication of issue/PR type and priority
- Automated workflows and integrations
- Easier project management

## Label Categories

### Type Labels (What)

Labels that describe the **type** of issue or PR.

| Label                   | Color   | Description                                 | Usage                    |
| ----------------------- | ------- | ------------------------------------------- | ------------------------ |
| `bug`                   | #d73a4a | Something isn't working                     | Issues, PRs              |
| `enhancement`           | #a2eeef | New feature or request                      | Issues, PRs              |
| `documentation`         | #0075ca | Improvements or additions to documentation  | Issues, PRs              |
| `config-infrastructure` | #ededed | Configuration or infrastructure changes     | Issues, PRs              |
| `security`              | #b60205 | Security-related changes or vulnerabilities | Issues, PRs              |
| `dependencies`          | #0366d6 | Pull requests that update a dependency file | PRs (often auto-labeled) |
| `breaking-change`       | #d93f0b | Changes that break backward compatibility   | PRs, Issues              |
| `developer-experience`  | #ededed | Improvements to developer experience (DX)   | Issues, PRs              |
| `legal`                 | #ededed | Legal compliance, licensing, CLA            | Issues, PRs              |

### Priority Labels (When)

Labels that indicate **urgency** and **importance**.

| Label              | Color   | Description               | Usage       |
| ------------------ | ------- | ------------------------- | ----------- |
| `priority: high`   | #ededed | Needs immediate attention | Issues, PRs |
| `priority: medium` | #ededed | Important but not urgent  | Issues, PRs |
| _(no label)_       | -       | Normal priority (default) | Issues, PRs |

**Note:** No `priority: low` label. If something is low priority, don't label it at all.

### Status Labels (State)

Labels that describe the **current state** of an issue or PR.

| Label              | Color   | Description                                    | Usage       |
| ------------------ | ------- | ---------------------------------------------- | ----------- |
| `help wanted`      | #008672 | Extra attention is needed                      | Issues      |
| `good first issue` | #7057ff | Good for newcomers                             | Issues      |
| `discussion`       | #ededed | Needs further discussion before implementation | Issues      |
| `duplicate`        | #cfd3d7 | This issue or pull request already exists      | Issues, PRs |
| `invalid`          | #e4e669 | This doesn't seem right                        | Issues, PRs |
| `wontfix`          | #ffffff | This will not be worked on                     | Issues, PRs |
| `question`         | #d876e3 | Further information is requested               | Issues      |

### Automation Labels

Labels used by automated tools and workflows.

| Label               | Color   | Description                                             | Usage      |
| ------------------- | ------- | ------------------------------------------------------- | ---------- |
| `dependabot`        | #0366d6 | Pull requests created by Dependabot                     | PRs (auto) |
| `large-pr-approved` | #FFA500 | Approved large PR (boilerplate/templates, cannot split) | PRs        |

## Label Usage Guidelines

### Issue Labeling

**Required:**

- At least **one type label** (`bug`, `enhancement`, `documentation`, etc.)

**Optional:**

- **One priority label** (if urgent)
- **Status labels** as needed

**Example:**

```text
Issue: "API returns 500 on invalid JWT"
Labels: bug, security, priority: high
```

### PR Labeling

**Required:**

- At least **one type label** matching the change type

**Optional:**

- `breaking-change` if backward incompatible
- `large-pr-approved` if > 600 lines and legitimate (see [CONTRIBUTING.md](../CONTRIBUTING.md#pr-size-limit))
- `dependencies` (usually auto-added by Dependabot)

**Example:**

```text
PR: "feat: add user authentication endpoint"
Labels: enhancement, security
```

## Label Sync Script

Use the provided script to sync labels across all SecPal repositories:

```bash
# From .github repository
./scripts/sync-labels.sh contracts
./scripts/sync-labels.sh api
./scripts/sync-labels.sh frontend
```

See [`scripts/sync-labels.sh`](../scripts/sync-labels.sh) for details.

## Creating New Labels

Before creating a **new label**:

1. **Check this document** - Does a similar label already exist?
2. **Propose in `.github` repo** - Open an issue to discuss
3. **Update this document** - Add to the standard list
4. **Sync across repos** - Use `sync-labels.sh`

**Don't create ad-hoc labels in individual repositories!** This breaks cross-repo tracking, complicates automation, and requires manual cleanup.

## Label Maintenance

### Regular Tasks

- **Monthly:** Review label usage, remove unused labels
- **On new repo:** Run `sync-labels.sh` to apply standards
- **On label change:** Update this document and sync

### Label Colors

We follow a consistent color scheme:

- **Red (#d73a4a, #b60205)**: Problems/Bugs/Security
- **Orange-Red (#d93f0b)**: Breaking changes (critical warnings)
- **Blue (#0075ca, #0366d6)**: Documentation/Dependencies
- **Green (#008672)**: Help/Community
- **Purple (#7057ff, #d876e3)**: Newcomers/Questions
- **Orange (#FFA500)**: Special approvals
- **Gray (#ededed, #cfd3d7)**: Neutral/Infrastructure
- **Yellow (#e4e669)**: Invalid/Warning
- **White (#ffffff)**: Won't fix

## Examples by Repository Type

### Backend (API)

Common label combinations:

- `bug` + `security` + `priority: high`
- `enhancement` + `breaking-change`
- `config-infrastructure` + `developer-experience`
- `dependencies` + `dependabot`

### Frontend

Common label combinations:

- `bug` + `priority: medium`
- `enhancement` + `developer-experience`
- `documentation`
- `dependencies` + `dependabot`

### Contracts (OpenAPI)

Common label combinations:

- `breaking-change` + `documentation`
- `enhancement` (new endpoints)
- `bug` (spec errors)
- `large-pr-approved` (template updates)

## FAQ

### Why no `priority: low`?

Low priority items clutter the backlog. If something is truly low priority, close it with `wontfix` or don't label it at all.

### Can I add repository-specific labels?

**No.** All labels should be organization-wide and documented here. This ensures consistency and makes cross-repo tracking possible.

### What about GitHub's default labels?

We **keep** GitHub's default labels and **extend** them with SecPal-specific ones. This ensures compatibility with third-party tools.

### How do I handle multiple types?

Choose the **primary** type. If a PR is both `enhancement` and `documentation`, choose based on the main change. Don't over-label.

## References

- [GitHub Labels Documentation](https://docs.github.com/en/issues/using-labels-and-milestones-to-track-work/managing-labels)
- [Label Sync Script](../scripts/sync-labels.sh)
- [Organization Contributing Guide](../CONTRIBUTING.md)

## Change Log

### 2025-10-25

- Initial label standards documentation
- Defined 20 standard labels across 4 categories
- Created `large-pr-approved` for legitimate large PRs
- Added label sync script

---

**Questions?** Open an issue in [SecPal/.github](https://github.com/SecPal/.github/issues).
