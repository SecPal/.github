<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# GitHub API Rate Limit Mitigation Strategy

**Date:** 2025-10-12
**Status:** IMPLEMENTED (Option B) - Options A & C documented for future
**Related:** Review Comment #3 on PR #17, PREVENTION-STRATEGY.md:585
**Decision:** Option B chosen for current scale (< 10 repos)

---

## Problem Statement

The original Weekly Configuration Audit workflow in `PREVENTION-STRATEGY.md` used nested loops with GitHub REST API calls:

```yaml
for repo in "${repos[@]}"; do
gh api repos/SecPal/$repo/contents/.license-policy.json
gh api repos/SecPal/$repo/contents/.github/workflows | while read workflow; do
gh api repos/SecPal/$repo/contents/.github/workflows/$workflow
done
done
```

**Impact at Scale:**

| Repos | API Calls/Week | Notes                                     |
| ----- | -------------- | ----------------------------------------- |
| 4     | ~28            | ✅ No problem (current state)             |
| 10    | ~70            | ⚠️ Starts to add up                       |
| 20    | ~140           | ❌ Problematic with other CI/CD workflows |
| 50+   | ~350+          | 🔴 Will compete for quota                 |

**GitHub REST API Limits:**

- **Authenticated:** 5,000 requests/hour
- **Per Workflow Run:** Usually fine
- **Problem:** Competition with other CI/CD workflows, slow execution

---

## Option B: Local Repository Cloning (IMPLEMENTED)

### Why Option B?

✅ **Pros:**

- **Zero API calls** for file access after initial clone
- **Faster** at scale (parallel file operations)
- **Offline-capable** (works without network after clone)
- **Simple implementation** (standard git operations)
- **Works with any number of repos** (no rate limits)

⚠️ **Cons:**

- Requires disk space (~5-50 MB per repo)
- Initial clone takes time (one-time cost)
- Must handle cleanup

**Decision Rationale:** For < 10 repos, disk space is negligible. Eliminates rate limit concern entirely.

### Implementation

**Location:** `.github/workflows/weekly-config-audit.yml`

```yaml
jobs:
  audit-all-repos:
    runs-on: ubuntu-latest
    steps:
      - name: Setup audit workspace
        run: |
          mkdir -p /tmp/secpal-audit
          cd /tmp/secpal-audit

      - name: Clone/update all repositories
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          repos=("contracts" ".github" "api" "frontend")

          for repo in "${repos[@]}"; do
            if [ -d "/tmp/secpal-audit/$repo" ]; then
              echo "📥 Updating $repo..."
              git -C "/tmp/secpal-audit/$repo" pull -q origin main
            else
              echo "📦 Cloning $repo..."
              gh repo clone "SecPal/$repo" "/tmp/secpal-audit/$repo" -- -q
            fi
          done

      - name: Audit license policies
        run: |
          cd /tmp/secpal-audit
          repos=("contracts" ".github" "api" "frontend")

          for repo in "${repos[@]}"; do
            echo "=== Auditing SecPal/$repo ==="

            # Check license policy (local file access, no API call)
            if [ -f "$repo/.license-policy.json" ]; then
              echo "  ✅ Has .license-policy.json"
              jq -c '{allowed: .allowedLicenses | length, denied: .deniedLicenses | length}' "$repo/.license-policy.json"
            else
              echo "  ❌ Missing .license-policy.json"
            fi

            # Check for hardcoded configs (local grep, no API call)
            if [ -d "$repo/.github/workflows" ]; then
              violations=$(grep -rn "deny-licenses:\|allow-licenses:" "$repo/.github/workflows/" \
                | grep -v "steps.policy.outputs" \
                | grep -v "# Allow hardcoded" || true)

              if [ -n "$violations" ]; then
                echo "  ❌ Hardcoded licenses found:"
                echo "$violations"
              else
                echo "  ✅ No hardcoded configurations"
              fi
            fi

            # Check action versions (local grep, no API call)
            if [ -d "$repo/.github/workflows" ]; then
              echo "  📦 Action versions:"
              grep -rh "uses:" "$repo/.github/workflows/" \
                | grep -oE '[a-z-]+/[a-z-]+@v[0-9]+' \
                | sort -u \
                | sed 's/^/    - /'
            fi

            echo ""
          done

      - name: Cleanup
        if: always()
        run: rm -rf /tmp/secpal-audit
```

**Key Changes:**

1. **Clone once** → reuse for all checks
2. **Local file access** → `cat`, `jq`, `grep`
3. **Parallel-ready** → can run checks in parallel if needed
4. **Cleanup** → remove clones after audit

**API Calls:**

- Initial: 1 per repo (clone via `gh repo clone`)
- File access: **0** (local filesystem)
- **Total: 4 calls/week** (vs 28+ with REST API approach)

---

## Option A: GraphQL Batching (FUTURE)

### When to Use

Switch to Option A when:

- **20+ repositories** (disk space becomes concern)
- **CI speed is critical** (GraphQL is faster than clones)
- **Need real-time data** (not cached locally)

### Implementation Sketch

```graphql
query AuditAllRepos {
  organization(login: "SecPal") {
    repositories(first: 100) {
      nodes {
        name
        defaultBranchRef {
          target {
            ... on Commit {
              file(path: ".license-policy.json") {
                ... on TreeEntry {
                  object {
                    ... on Blob {
                      text
                    }
                  }
                }
              }
              workflows: tree(path: ".github/workflows") {
                ... on Tree {
                  entries {
                    name
                    object {
                      ... on Blob {
                        text
                      }
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
```

**Usage:**

```bash
gh api graphql -f query="$(cat query.graphql)" | jq '.data.organization.repositories.nodes[]'
```

**Benefits:**

- **1 API call** for entire organization
- Fast (< 5 seconds for 20 repos)
- No disk space needed

**Tradeoffs:**

- More complex query
- Harder to debug
- Limited to 100 repos per query (need pagination)

---

## Option C: GitHub App (ENTERPRISE)

### When to Use

Consider Option C when:

- **50+ repositories** across multiple organizations
- **Professional/Enterprise deployment**
- Need **15,000 req/hour** instead of 5,000

### Setup

1. **Create GitHub App**

   ```bash
   gh api -X POST /orgs/SecPal/apps \
     --field name="SecPal Config Auditor" \
     --field url="https://github.com/SecPal" \
     --field webhook_active=false
   ```

2. **Generate Private Key** → Store as repository secret

3. **Install App** on organization

4. **Update Workflow:**

   ```yaml
   - name: Get GitHub App Token
     id: app-token
     uses: actions/create-github-app-token@v1
     with:
       app-id: ${{ secrets.APP_ID }}
       private-key: ${{ secrets.APP_PRIVATE_KEY }}

   - name: Audit with higher limits
     env:
       GH_TOKEN: ${{ steps.app-token.outputs.token }}
     run: |
       # Now has 15,000 req/hour instead of 5,000
   ```

**Benefits:**

- 3× higher rate limits
- Better for multi-org
- Professional approach

**Tradeoffs:**

- Overhead (app creation, key management)
- Overkill for small orgs

---

## Decision Matrix

| Criterion            | Option B (Clone) | Option A (GraphQL) | Option C (App) |
| -------------------- | ---------------- | ------------------ | -------------- |
| **API Calls/Week**   | 4                | 1                  | Variable       |
| **Disk Space**       | ~200 MB          | 0                  | 0              |
| **Setup Time**       | 10 min           | 30 min             | 2 hours        |
| **Maintenance**      | Low              | Medium             | High           |
| **Speed (4 repos)**  | ~30 sec          | ~5 sec             | ~5 sec         |
| **Speed (20 repos)** | ~2 min           | ~10 sec            | ~10 sec        |
| **Max Scale**        | Unlimited        | 100 repos/query    | Unlimited      |
| **Offline Capable**  | ✅ Yes           | ❌ No              | ❌ No          |

**Recommendation Timeline:**

- **Now (< 10 repos):** Option B ✅
- **At 15-20 repos:** Re-evaluate → likely stay Option B
- **At 30+ repos:** Switch to Option A
- **Multi-org/Enterprise:** Switch to Option C

---

## Migration Path

If we need to switch from Option B → Option A later:

```diff
- # Clone repos
- gh repo clone "SecPal/$repo" "/tmp/audit/$repo"
- cat "/tmp/audit/$repo/.license-policy.json"

+ # Use GraphQL
+ gh api graphql -f query='...' | jq '.data.organization.repositories.nodes[]'
```

**Effort:** ~1-2 hours (update workflow, test queries)

**No Breaking Changes:** Same audit logic, different data source

---

## Monitoring

Track API usage to decide when to switch:

```yaml
- name: Check rate limit
  run: |
    gh api rate_limit | jq '{
      remaining: .rate.remaining,
      limit: .rate.limit,
      used: (.rate.limit - .rate.remaining)
    }'
```

**Alert Threshold:**

- If `used > 2000/hour` during audit runs → consider Option A
- If `remaining < 1000` regularly → consider Option C

---

## References

- **Original Issue:** Review Comment #3, PR #17
- **GitHub API Docs:** https://docs.github.com/en/rest/overview/resources-in-the-rest-api#rate-limiting
- **GraphQL API Docs:** https://docs.github.com/en/graphql/overview/resource-limitations
- **Related:** PREVENTION-STRATEGY.md Phase 3 (Cross-Repo Monitoring)

---

## Changelog

| Date       | Change                                 | Author |
| ---------- | -------------------------------------- | ------ |
| 2025-10-12 | Created document, implemented Option B | Agent  |
| TBD        | Review after 10 repos milestone        | -      |
| TBD        | Consider Option A if needed            | -      |
