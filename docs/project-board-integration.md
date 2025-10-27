<!--
SPDX-FileCopyrightText: 2025 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# GitHub Project Board Integration

**Purpose:** This document explains how SecPal's feature management workflow integrates with GitHub Projects for Kanban-style tracking.

**Last Updated:** 2025-10-27

---

## 🎯 Overview

SecPal uses a **three-tier system** for feature management:

1. **Documentation Layer** (`ideas-backlog.md` + `feature-requirements.md`)
2. **Issue Tracking** (GitHub Issues with structured templates)
3. **Visual Management** (GitHub Project Board)

```
┌────────────────────────────────────────────────────────────────┐
│                   SecPal Feature Workflow                      │
└────────────────────────────────────────────────────────────────┘

 💡 New Idea
     │
     ├──► docs/ideas-backlog.md (Quick Capture)
     │
     ▼
 📋 Specification Phase
     │
     ├──► docs/feature-requirements.md (Detailed Spec)
     │
     ▼
 🎫 Issue Creation
     │
     ├──► GitHub Issue (via core_feature.yml template)
     │    ↓
     │    Automatically added to Project Board
     │
     ▼
 📊 Project Board Tracking
     │
     └──► Kanban Board: Ideas → Backlog → Ready → In Progress → Done
```

---

## 📊 Project Board Structure

### Recommended Columns

| Column             | Status              | Description                                                  |
| ------------------ | ------------------- | ------------------------------------------------------------ |
| 💡 **Ideas**       | `status: backlog`   | Raw ideas from `ideas-backlog.md`, not yet specified         |
| 📋 **Backlog**     | `status: specified` | Specified in `feature-requirements.md`, ready for refinement |
| 🎯 **Ready**       | `status: ready`     | Ready for development, acceptance criteria defined           |
| 🚧 **In Progress** | In development      | Active work, assigned to developer                           |
| 👀 **In Review**   | PR open             | Code review in progress                                      |
| ✅ **Done**        | Closed              | Merged and deployed                                          |

### Custom Fields (Optional)

Add these fields to your GitHub Project for better tracking:

- **Priority**: `P0`, `P1`, `P2`, `P3` (auto-populated from labels)
- **Feature Area**: `RBAC`, `Employee Mgmt`, `Shift Planning`, etc.
- **Size**: `XS`, `S`, `M`, `L`, `XL`, `XXL`
- **Target Phase**: `Phase 1`, `Phase 2`, `Phase 3`, `Phase 4`
- **Estimated Effort**: Number field (story points or days)

---

## 🔄 Workflow: From Idea to Implementation

### Step 1: Capture the Idea

**When:** You have a new feature idea (e.g., "Sub-Contractor Management", "BWR Integration")

**Action:**

```bash
# Edit ideas-backlog.md
vim docs/ideas-backlog.md

# Add new section under appropriate category
## 🏢 Sub-Contractor Management
**Context:** ...
**Concept:** ...
**When to revisit:** ...
**Complexity:** High
**Priority:** Later
```

**No GitHub Issue yet!** Ideas stay in the backlog until they're ready for specification.

---

### Step 2: Specify the Feature

**When:** Idea has been validated and is ready for detailed planning

**Action:**

```bash
# Move to feature-requirements.md
vim docs/feature-requirements.md

# Add detailed specification
## Sub-Contractor Management
### Business Requirements
...
### Data Model
...
### API Design
...
```

**Still no Issue!** Features are specified first, then broken into Issues.

---

### Step 3: Create GitHub Issue(s)

**When:** Feature is specified and ready to be implemented (or next phase)

**Action:**

1. Go to: <https://github.com/SecPal/.github/issues/new/choose>
2. Choose: **🎯 Core Feature Implementation**
3. Fill out the template:
   - **Feature Reference**: "Employee Management - BWR Integration (see feature-requirements.md)"
   - **User Stories**: "As a HR manager, I want to..."
   - **Acceptance Criteria**: Clear, testable criteria
   - **Priority**: Select P0-P3
   - **Feature Area**: Select category
   - **Affected Repos**: `api`, `frontend`, `contracts`

4. Issue is **automatically added** to Project Board (via GitHub Actions)

---

### Step 4: Manage on Project Board

**Automation (via `.github/workflows/project-automation.yml`):**

- ✅ New issues → Automatically added to Project
- ✅ Labels determine initial column:
  - `core-feature` → 📋 Backlog
  - `priority: blocker` → 🎯 Ready
  - Default → 💡 Ideas

**Manual Actions:**

- **Refine:** Add labels, link dependencies, update description
- **Prioritize:** Move between columns based on roadmap
- **Assign:** Set developer when work starts
- **Track:** Update status as work progresses

---

## 🏷️ Label Strategy

### Priority Labels

- `priority: blocker` → P0 (Must have for MVP)
- `priority: high` → P1 (Should have for Phase 1-2)
- `priority: medium` → P2 (Nice to have for Phase 3)
- `priority: low` → P3 (Future consideration)

### Area Labels

Create labels for each feature area (run these commands):

```bash
gh label create "area: RBAC" --color "0E8A16" --description "Role-Based Access Control" --repo SecPal/.github
gh label create "area: employee-mgmt" --color "0E8A16" --description "Employee Management" --repo SecPal/.github
gh label create "area: qualifications" --color "0E8A16" --description "Qualifications & Certifications" --repo SecPal/.github
gh label create "area: shift-planning" --color "0E8A16" --description "Shift Planning & Scheduling" --repo SecPal/.github
gh label create "area: compliance" --color "D93F0B" --description "Legal & Compliance (BWR, DSGVO)" --repo SecPal/.github
gh label create "area: guard-book" --color "0E8A16" --description "Guard Book & Incidents" --repo SecPal/.github
gh label create "area: signatures" --color "0E8A16" --description "Digital Signatures" --repo SecPal/.github
gh label create "area: works-council" --color "0E8A16" --description "Works Council Management" --repo SecPal/.github
```

### Status Labels

- `status: backlog` → In ideas-backlog.md
- `status: specified` → In feature-requirements.md
- `status: ready` → Ready for implementation
- `core-feature` → Core platform feature (not a small enhancement)

---

## 📈 Example: BWR Integration Journey

### Phase 1: Idea Capture (Today)

```markdown
# docs/ideas-backlog.md

## 🆔 BWR Integration

**Context:** Manual BWR checking is error-prone
**Concept:** Store BWR-ID in employee record, track status
**Priority:** Soon
**Complexity:** Medium
```

### Phase 2: Specification (Next Week)

```markdown
# docs/feature-requirements.md

## BWR Integration

### Overview

...

### Data Model

- employee.bwr_id (string, unique)
- employee.bwr_status (enum: active, suspended, expired)
- employee.bwr_expiry_date (date)
  ...
```

### Phase 3: Issue Creation (Sprint Planning)

Create Issue using **Core Feature Template**:

**Title:** `[Feature]: BWR Integration in Employee Management`

**Labels:** `core-feature`, `area: employee-mgmt`, `area: compliance`, `priority: high`

**Auto-added to Project Board** → Column: **📋 Backlog**

### Phase 4: Development

1. Move to **🎯 Ready** column
2. Assign to developer
3. Create branch: `feature/bwr-integration`
4. Move to **🚧 In Progress**
5. Open PR → Move to **👀 In Review**
6. Merge → Automatically closes issue → Move to **✅ Done**

---

## 🔧 Setup Instructions

### 1. Create GitHub Project

1. Go to: <https://github.com/orgs/SecPal/projects>
2. Click **New project**
3. Choose **Board** layout
4. Name: `SecPal Feature Roadmap`
5. Create columns:
   - 💡 Ideas
   - 📋 Backlog
   - 🎯 Ready
   - 🚧 In Progress
   - 👀 In Review
   - ✅ Done

### 2. Update Automation Workflow

Edit `.github/workflows/project-automation.yml`:

```yaml
project-url: https://github.com/orgs/SecPal/projects/YOUR_PROJECT_NUMBER
```

Replace `YOUR_PROJECT_NUMBER` with the actual number (found in the project URL).

### 3. Create Area Labels

Run the label creation commands from the "Label Strategy" section above.

### 4. Test the Workflow

1. Create a test issue using the **Core Feature Template**
2. Verify it appears on the Project Board
3. Move it between columns to test the flow
4. Close the test issue

---

## 💡 Best Practices

### Do's

✅ **Keep docs and issues in sync**

- Update `feature-requirements.md` when significant changes occur
- Reference docs in issue descriptions

✅ **Use templates consistently**

- Use **Core Feature Template** for planned features
- Use **Feature Request Template** for new ideas from users

✅ **Break down large features**

- If a feature is >2 weeks effort, split into multiple issues
- Use "Depends on" to link related issues

✅ **Review backlog regularly**

- Monthly: Review `ideas-backlog.md` → promote to `feature-requirements.md`
- Sprint Planning: Review `feature-requirements.md` → create Issues

### Don'ts

❌ **Don't create issues for every idea**

- Ideas go in `ideas-backlog.md` first
- Only create issues when you're ready to specify/implement

❌ **Don't skip specification**

- Features need clear acceptance criteria
- Use `feature-requirements.md` to think through design

❌ **Don't leave issues unassigned in "Ready"**

- If it's ready, assign it or move back to Backlog
- "Ready" means someone can start work immediately

---

## 🔗 Related Resources

- [Issue #67: Convert feature-requirements.md to GitHub Issues](https://github.com/SecPal/.github/issues/67)
- [docs/ideas-backlog.md](./ideas-backlog.md) - Feature idea parking lot
- [docs/feature-requirements.md](./feature-requirements.md) - Detailed specifications
- [GitHub Projects Documentation](https://docs.github.com/en/issues/planning-and-tracking-with-projects)
- [GitHub Project Automation](https://docs.github.com/en/issues/planning-and-tracking-with-projects/automating-your-project)

---

## 📞 Questions?

If you're unsure where something belongs:

- **"I have a vague idea"** → `ideas-backlog.md`
- **"I want to design this properly"** → `feature-requirements.md`
- **"I'm ready to build this"** → Create GitHub Issue
- **"I want to track progress visually"** → Check Project Board

**When in doubt, start with the docs!** It's easier to promote an idea from docs to an Issue than to clean up premature Issues.
