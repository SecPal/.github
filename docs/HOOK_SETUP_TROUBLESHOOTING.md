<!-- SPDX-FileCopyrightText: 2025 SecPal Contributors -->
<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->

# Git Hook Setup & Troubleshooting

## Overview

SecPal uses Git hooks to enforce quality standards before commits and pushes. These hooks are managed as **symlinks** pointing to scripts in the repository, ensuring they stay synchronized with updates.

## Hook Architecture

### Design Principle

```
.git/hooks/pre-push    →  symlink  →  ../../scripts/preflight.sh
.git/hooks/pre-commit  →  managed by Python pre-commit framework
```

**Note:**

- The **pre-push** hook is a symlink to a repository script, so it updates automatically with script changes.
- The **pre-commit** hook is managed by the [Python pre-commit framework](https://pre-commit.com/), which installs its own hook script in `.git/hooks/pre-commit` and manages updates via `pre-commit install` and `.pre-commit-config.yaml`.

**Why Symlinks? (for pre-push)**

- ✅ Hooks automatically update when scripts change
- ✅ No manual sync needed after pulling updates
- ✅ Single source of truth in version control
- ❌ Direct copies get outdated and cause conflicts

### Setup Scripts

Each repository provides setup scripts:

```bash
./scripts/setup-pre-push.sh    # Installs pre-push hook
./scripts/setup-pre-commit.sh  # Installs pre-commit hook
```

## Common Problems

### Problem: Merge Conflicts in Hooks

**Symptoms:**

```bash
$ git push
.git/hooks/pre-push: line 73: syntax error near unexpected token '<<<'
```

**Cause:**
The hook file is a **direct copy** (not a symlink) that contains unresolved merge conflict markers:

```bash
<<<<<<< Updated upstream
[old code version]
=======
[new code version]
>>>>>>> Stashed changes
```

**Solution:**

1. **Check if hook is a symlink:**

   ```bash
   ls -la .git/hooks/pre-push
   ```

   ✅ **Good** (symlink):

   ```
   lrwxrwxrwx [...] .git/hooks/pre-push -> ../../scripts/preflight.sh
   ```

   ❌ **Bad** (regular file):

   ```
   -rwxr-xr-x [...] .git/hooks/pre-push
   ```

2. **Fix: Reinstall as symlink:**

   ```bash
   rm .git/hooks/pre-push
   ./scripts/setup-pre-push.sh
   ```

3. **Verify:**

   ```bash
   ls -la .git/hooks/pre-push  # Should show symlink arrow →
   git push --dry-run          # Should succeed
   ```

### Problem: Hook Not Executing

**Symptoms:**

- Pre-push hook doesn't run
- Quality checks are skipped

**Solution:**

1. **Check hook exists:**

   ```bash
   ls -la .git/hooks/pre-push
   ```

2. **If missing, install:**

   ```bash
   ./scripts/setup-pre-push.sh
   ```

3. **Check permissions:**

   ```bash
   # Symlink itself doesn't need +x
   # Target script needs +x
   ls -la scripts/preflight.sh  # Should be -rwxr-xr-x
   ```

### Problem: Hook Fails After Backup Restore

**Cause:**
Git hooks in `.git/hooks/` are **not included in Git backups** (they're in `.git/`, which is local-only).

**Solution:**

Re-run setup scripts after restore:

```bash
./scripts/setup-pre-push.sh
./scripts/setup-pre-commit.sh
```

## Installation

### Fresh Clone

After cloning any SecPal repository:

```bash
git clone https://github.com/SecPal/api.git
cd api

# Install hooks
./scripts/setup-pre-push.sh
./scripts/setup-pre-commit.sh

# Verify
ls -la .git/hooks/
```

### Existing Repository

If hooks are missing or broken:

```bash
# Remove old hooks
rm -f .git/hooks/pre-push .git/hooks/pre-commit

# Reinstall
./scripts/setup-pre-push.sh
./scripts/setup-pre-commit.sh
```

## Manual Execution

Test hooks without pushing/committing:

```bash
# Test pre-push checks
./scripts/preflight.sh

# Test pre-commit checks
pre-commit run --all-files
```

## Bypass (Emergency Only)

**⚠️ Not Recommended:** Bypass hooks only in emergencies:

```bash
git push --no-verify      # Skip pre-push hook
git commit --no-verify    # Skip pre-commit hook
```

**When to use:**

- Hook script is broken (fix in separate branch)
- Emergency hotfix (create follow-up PR for quality fixes)
- Manual verification completed separately

**Never use for:**

- "Saving time"
- Avoiding test failures
- Skipping REUSE compliance

## Verification

### Check Hook Status

```bash
# List all hooks
ls -la .git/hooks/

# Check specific hook
file .git/hooks/pre-push  # Should say "symbolic link"
readlink .git/hooks/pre-push  # Shows target: ../../scripts/preflight.sh
```

### Test Hook Execution

```bash
# Dry-run push (triggers hook without pushing)
git push --dry-run

# Manual execution
./scripts/preflight.sh
```

## Related Scripts

- **`scripts/setup-pre-push.sh`** - Installs pre-push hook as symlink
- **`scripts/setup-pre-commit.sh`** - Installs pre-commit hooks via Python framework
- **`scripts/preflight.sh`** - Pre-push quality checks (target of pre-push hook)
- **`scripts/check-conflict-markers.sh`** - Detects merge conflict markers in files (provided in PR #181)

## Debugging

### Enable Verbose Output

```bash
# See what pre-push hook executes
bash -x .git/hooks/pre-push

# See what preflight checks
bash -x scripts/preflight.sh
```

### Common Errors

| Error                     | Cause                          | Fix                                                                     |
| ------------------------- | ------------------------------ | ----------------------------------------------------------------------- |
| `syntax error near '<<<'` | Merge conflict markers in hook | Reinstall hook: `rm .git/hooks/pre-push && ./scripts/setup-pre-push.sh` |
| `pre-push: not found`     | Hook missing                   | Run `./scripts/setup-pre-push.sh`                                       |
| `Permission denied`       | Script not executable          | `chmod +x scripts/preflight.sh`                                         |
| Hook doesn't run          | Not installed                  | Run setup scripts                                                       |

## Best Practices

1. ✅ **Always use setup scripts** - Don't manually create/copy hooks
2. ✅ **Verify symlinks after restore** - Hooks aren't backed up with Git
3. ✅ **Test hooks manually** - Run `./scripts/preflight.sh` before pushing
4. ✅ **Keep hooks in sync** - Symlinks update automatically
5. ❌ **Never edit `.git/hooks/` directly** - Edit source scripts instead
6. ❌ **Don't commit `.git/hooks/`** - It's local-only (in `.git/`)

## CI Integration

Hooks enforce quality locally. CI enforces same checks remotely:

```yaml
# .github/workflows/quality.yml
- name: Run Quality Checks
  run: ./scripts/preflight.sh
```

**Philosophy:** Same checks everywhere - local, PR, CI.

## Further Reading

- [Git Hooks Documentation](https://git-scm.com/book/en/v2/Customizing-Git-Git-Hooks)
- [Pre-commit Framework](https://pre-commit.com/)
- [Preflight Script Documentation](../scripts/README.md)
- [Conflict Marker Detection](https://github.com/SecPal/.github/blob/main/docs/scripts/CHECK_CONFLICT_MARKERS.md) (see PR #181)

---

**Last Updated:** 2025-11-09
**Applies To:** All SecPal repositories (api, frontend, contracts, .github)
