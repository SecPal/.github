# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read-only target-shaped acceptance against locally fetched immutable objects.

Run with an isolated deployment Git object directory. This test creates only
mechanical merge-tree objects; it cannot push, publish, transition or dispatch.
The fixed SHAs belong to this regression, never production operation policy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.secpal_pr_review import fast_path
from scripts.secpal_pr_review.enrolled_draft_integration import KIND

CURRENT_HEAD = "23f04d218ec299fd933353fd438e921da6ff2694"
ACCEPTED_MAIN = "4571a9b2653cb73c743a7812f0c4bfcad599d45d"
IMPORT_CLOSURE = (
    "scripts/render-native-postgresql.py",
    "scripts/ci-cloud/postgresql_qualification_contract.py",
    "scripts/ci-cloud/rocky_preparation_contract.py",
)


def run(root: Path) -> dict:
    parents = [CURRENT_HEAD, ACCEPTED_MAIN]
    tree, conflicts = fast_path._mechanical_integration_result(root, parents, run_git=fast_path._run_integration_tree_git)
    if conflicts:
        raise AssertionError("the frozen #81-shaped clean integration unexpectedly conflicts")
    evidence = fast_path.derive_ready_integration_tree_evidence(
        root, parents, tree, schema_version="1.0", kind=KIND,
    )
    if evidence["manual_conflict_resolution_delta"] or evidence["path_classifications"]:
        raise AssertionError("clean target integration must have no manual delta")
    closure = []
    for path in IMPORT_CLOSURE:
        raw = fast_path._run_integration_tree_git(root, ["show", f"{tree}:{path}"], raw_output=True).stdout
        accepted = fast_path._run_integration_tree_git(root, ["show", f"{ACCEPTED_MAIN}:{path}"], raw_output=True).stdout
        if raw != accepted:
            raise AssertionError(f"integrated qualification trusted import closure is stale: {path}")
        closure.append({"path": path, "sha256": hashlib.sha256(raw).hexdigest()})
    contract = IMPORT_CLOSURE[1]
    old = fast_path._run_integration_tree_git(root, ["show", f"{CURRENT_HEAD}:{contract}"]).stdout
    corrected = fast_path._run_integration_tree_git(root, ["show", f"{tree}:{contract}"]).stdout
    if old == corrected or "def normalize_lifecycle_timeline(" not in corrected:
        raise AssertionError("the #287 correction was not integrated from accepted main")
    # The delivery declaration remains present; reconciling trusted tooling is
    # integration of both parents, never a selective file-copy workaround.
    fast_path._run_integration_tree_git(root, ["show", f"{tree}:config/production/postgresql-contract.json"])
    return {"kind": KIND, "repository": "SecPal/deployment", "delivery_issue": 81,
            "pull_request": 286, "ordered_parent_shas": parents,
            "integrated_tree_sha": tree, "tree_evidence": evidence,
            "trusted_import_closure": closure, "downstream_mutation": False,
            "provider_dispatch": False, "successful_result": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", required=True, type=Path)
    arguments = parser.parse_args()
    print(json.dumps(run(arguments.repo_root.resolve(strict=True)), indent=2))
