<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# Git Conflict Marker Detection

The `check-conflict-markers.sh` script detects unresolved Git merge conflict markers in tracked files to prevent accidental commits of broken code.

## Problem

When resolving merge conflicts, developers sometimes forget to remove conflict markers:

```bash
<<<<<<< HEAD
code from current branch
=======
code from incoming branch
>>>>>>> feature-branch
```

These markers cause:

- **Syntax errors** in source code
- **Runtime failures** in scripts and configuration files
- **Broken builds** in CI/CD pipelines
- **Production incidents** if deployed

## Solution

This script automatically detects conflict markers in all tracked text files before they reach the repository.

## Usage

### Manual Check

```bash
# Check all tracked files
./scripts/check-conflict-markers.sh
```

### CI/CD Integration

The script runs automatically in CI via GitHub Actions on every PR and push to `main`.

### Pre-commit Hook

Add to `.git/hooks/pre-commit`:

```bash
#!/bin/bash
# Run conflict marker check
if [ -f scripts/check-conflict-markers.sh ]; then
  ./scripts/check-conflict-markers.sh || exit 1
fi
```

## Detected Patterns

The script detects these conflict markers:

| Marker           | Meaning                         |
| ---------------- | ------------------------------- |
| `<<<<<<<`        | Start of conflict (from HEAD)   |
| `=======`        | Separator between changes       |
| `>>>>>>>`        | End of conflict (from incoming) |
| `\|\|\|\|\|\|\|` | Optional: diff3 style marker    |

## Exit Codes

- `0` - No conflict markers found ✅
- `1` - Conflict markers detected ❌

## Example Output

### Success (No Conflicts)

```bash
═══════════════════════════════════════════════════════════════
Git Conflict Marker Detection
═══════════════════════════════════════════════════════════════

─────────────────────────────────────────────────────
Checked files: 111
✓ No conflict markers found
═══════════════════════════════════════════════════════════════
```

### Failure (Conflicts Found)

```bash
═══════════════════════════════════════════════════════════════
Git Conflict Marker Detection
═══════════════════════════════════════════════════════════════

✗ Conflict markers detected:

File: .git/hooks/pre-push
  Line 73: <<<<<<< Updated upstream...

File: src/main.py
  Line 42: =======...

─────────────────────────────────────────────────────
Checked files: 111
✗ Found conflict markers in files

Action required:
1. Open the affected files
2. Search for conflict markers: <<<<<<<, =======, >>>>>>>
3. Manually resolve the conflicts
4. Remove all conflict markers
5. Test your changes
6. Commit again

═══════════════════════════════════════════════════════════════
```

## How to Resolve Conflicts

1. **Locate the markers** - The script shows file names and line numbers
2. **Review both changes** - Understand code from both branches
3. **Choose or merge** - Keep one version, the other, or combine both
4. **Remove markers** - Delete all `<<<<<<<`, `=======`, `>>>>>>>` lines
5. **Test** - Verify the code works correctly
6. **Commit** - Try committing again

## Common Scenarios

### False Positives

The script only checks lines **starting with** conflict markers, reducing false positives. If you legitimately need these patterns in your code (e.g., documentation), indent them:

```markdown
<!-- This is documentation, not a conflict -->

    <<<<<<< This won't trigger (indented)
```

### Binary Files

Binary files are automatically skipped - only text files are checked.

### .git Directory

The `.git` directory itself is excluded from checks (uses `git ls-files`).

## Integration with Other Tools

### Pre-commit Framework

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: check-conflict-markers
        name: Check for conflict markers
        entry: ./scripts/check-conflict-markers.sh
        language: script
        pass_filenames: false
```

### CI/CD Pipelines

```yaml
# GitHub Actions (already included)
- name: Check conflict markers
  run: ./scripts/check-conflict-markers.sh
```

## Troubleshooting

### "Permission denied"

```bash
chmod +x scripts/check-conflict-markers.sh
```

### "file: command not found"

Install the `file` utility:

```bash
# Ubuntu/Debian
sudo apt install file

# macOS
brew install file
```

## See Also

- [Preflight Scripts](../scripts/preflight.sh) - Quality Gate Checks
- [System Requirements Check](CHECK_SYSTEM_REQUIREMENTS.md) - Development Prerequisites
- [Git Merge Conflicts](https://git-scm.com/docs/git-merge#_how_conflicts_are_presented) - Official Git Documentation
