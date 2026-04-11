#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

org="SecPal"
repos=()

while [ $# -gt 0 ]; do
  case "$1" in
    --org)
      org="$2"
      shift 2
      ;;
    --repo)
      repos+=("$2")
      shift 2
      ;;
    -h|--help)
      cat <<'EOF'
Usage: bash scripts/audit-closed-epics.sh [--org ORG] [--repo REPO]...

Audit closed Epic issues by checking checklist-linked child issues.

Options:
  --org ORG    GitHub organization or owner to inspect (default: SecPal)
  --repo REPO  Repository name to inspect. Repeat to scope the audit.

If no repositories are provided, the script audits the active SecPal workspace
repositories: api, changelog, frontend, contracts, android, secpal.app, .github.
EOF
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [ ${#repos[@]} -eq 0 ]; then
  repos=(api changelog frontend contracts android secpal.app .github)
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "gh is required to audit closed epics." >&2
  exit 2
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required to audit closed epics." >&2
  exit 2
fi

export EPIC_AUDIT_ORG="$org"
epic_audit_repos="$(printf '%s\n' "${repos[@]}")"
export EPIC_AUDIT_REPOS="$epic_audit_repos"

python3 - <<'PY'
import json
import os
import re
import subprocess
import sys

org = os.environ["EPIC_AUDIT_ORG"]
repos = [repo for repo in os.environ["EPIC_AUDIT_REPOS"].splitlines() if repo]

explicit_ref = re.compile(rf"{re.escape(org)}/([A-Za-z0-9_.-]+)#(\d+)")
issue_url_ref = re.compile(rf"https://github\.com/{re.escape(org)}/([A-Za-z0-9_.-]+)/issues/(\d+)")
relative_ref = re.compile(r"(?<![\w/])#(\d+)")
markdown_link = re.compile(r"\[[^\]]*\]\([^)]*\)")
pr_ref = re.compile(r"\bPR\s+#\d+", re.IGNORECASE)
checklist_line = re.compile(r"^- \[[ xX]\]")


def gh_json(*args):
    output = subprocess.check_output(
        ["gh", "api", *args],
        text=True,
        stderr=subprocess.DEVNULL,
    )
    return json.loads(output)


def search_epics(owner: str, repo: str):
    queries = [
        f"repo:{owner}/{repo} is:issue label:epic is:closed",
        f"repo:{owner}/{repo} is:issue in:title epic is:closed",
    ]
    results = []
    for query in queries:
        payload = gh_json(
            "/search/issues",
            "-X",
            "GET",
            "-f",
            f"q={query}",
            "-f",
            "per_page=100",
        )
        results.extend(payload.get("items", []))
    unique = {}
    for item in results:
        key = (item["repository_url"], item["number"])
        unique[key] = item
    return list(unique.values())


issue_state_cache = {}


def fetch_issue_state(owner_repo: str, number: int):
    cache_key = (owner_repo, number)
    if cache_key in issue_state_cache:
        return issue_state_cache[cache_key]

    try:
        payload = gh_json(f"/repos/{owner_repo}/issues/{number}")
        state = {
            "state": payload.get("state", "unknown"),
            "title": payload.get("title", ""),
        }
    except subprocess.CalledProcessError:
        state = {"state": "missing", "title": ""}

    issue_state_cache[cache_key] = state
    return state


def parse_issue_refs(line: str, epic_repo: str):
    refs = []
    for repo_name, number in explicit_ref.findall(line):
        refs.append((f"{org}/{repo_name}", int(number)))

    for repo_name, number in issue_url_ref.findall(line):
        refs.append((f"{org}/{repo_name}", int(number)))

    scrubbed = issue_url_ref.sub("", line)
    scrubbed = markdown_link.sub("", scrubbed)
    scrubbed = pr_ref.sub("", scrubbed)
    scrubbed = explicit_ref.sub("", scrubbed)
    for number in relative_ref.findall(scrubbed):
        refs.append((epic_repo, int(number)))

    deduped = []
    seen = set()
    for ref in refs:
        if ref in seen:
            continue
        seen.add(ref)
        deduped.append(ref)
    return deduped


epics = []
for repo in repos:
    epics.extend(search_epics(org, repo))

unique_epics = {}
for item in epics:
    key = (item["repository_url"], item["number"])
    unique_epics[key] = item

findings = []
for item in sorted(unique_epics.values(), key=lambda epic: (epic["repository_url"], epic["number"])):
    epic_repo = item["repository_url"].split("/repos/", 1)[1]
    epic_number = item["number"]
    epic_title = item["title"]
    body = item.get("body") or ""

    for line in body.splitlines():
        stripped = line.strip()
        if not checklist_line.match(stripped):
            continue

        marked_checked = stripped.startswith("- [x]") or stripped.startswith("- [X]")
        refs = parse_issue_refs(stripped, epic_repo)
        for ref_repo, ref_number in refs:
            if (ref_repo, ref_number) == (epic_repo, epic_number):
                continue

            state = fetch_issue_state(ref_repo, ref_number)["state"]
            if state == "missing":
                findings.append(
                    {
                        "kind": "missing-child",
                        "epic_repo": epic_repo,
                        "epic_number": epic_number,
                        "epic_title": epic_title,
                        "child_repo": ref_repo,
                        "child_number": ref_number,
                        "line": stripped,
                    }
                )
            elif marked_checked and state != "closed":
                findings.append(
                    {
                        "kind": "checked-open-child",
                        "epic_repo": epic_repo,
                        "epic_number": epic_number,
                        "epic_title": epic_title,
                        "child_repo": ref_repo,
                        "child_number": ref_number,
                        "line": stripped,
                    }
                )
            elif not marked_checked and state == "closed":
                findings.append(
                    {
                        "kind": "stale-unchecked-child",
                        "epic_repo": epic_repo,
                        "epic_number": epic_number,
                        "epic_title": epic_title,
                        "child_repo": ref_repo,
                        "child_number": ref_number,
                        "line": stripped,
                    }
                )
            elif not marked_checked and state != "closed":
                findings.append(
                    {
                        "kind": "open-child",
                        "epic_repo": epic_repo,
                        "epic_number": epic_number,
                        "epic_title": epic_title,
                        "child_repo": ref_repo,
                        "child_number": ref_number,
                        "line": stripped,
                    }
                )

if not findings:
    print(f"No closed epic checklist issues found across {len(unique_epics)} epic(s).")
    sys.exit(0)

deduped_findings = []
seen_findings = set()
for finding in findings:
    key = (
        finding["kind"],
        finding["epic_repo"],
        finding["epic_number"],
        finding["child_repo"],
        finding["child_number"],
    )
    if key in seen_findings:
        continue
    seen_findings.add(key)
    deduped_findings.append(finding)

print(f"Closed epic checklist issues found: {len(deduped_findings)} across {len(unique_epics)} epic(s).")
for finding in deduped_findings:
    epic_prefix = f"{finding['epic_repo']}#{finding['epic_number']}"
    child_prefix = f"{finding['child_repo']}#{finding['child_number']}"
    if finding["kind"] == "stale-unchecked-child":
        message = f"{child_prefix} is closed but still unchecked"
    elif finding["kind"] == "open-child":
        message = f"{child_prefix} is still open"
    elif finding["kind"] == "checked-open-child":
        message = f"{child_prefix} is not closed but is marked done"
    else:
        message = f"{child_prefix} could not be resolved from the checklist reference"
    print(f"- {epic_prefix} \"{finding['epic_title']}\": {message}")

sys.exit(1)
PY
