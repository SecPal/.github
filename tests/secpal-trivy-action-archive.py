# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Qualify the immutable action download with Git's real export semantics."""

from __future__ import annotations

import io
import os
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACTION_DIRECTORY = ".github/actions/trivy-repository-scan/"
# Runtime closure owned by configuration_identity() in the scanner.
REQUIRED_FILES = (
    ACTION_DIRECTORY + "action.yml",
    "scripts/secpal-trivy-repository-scan.py",
    "policies/trivy-repository-scan-v1.json",
    "policies/trivy-repository-scan-ignore-v1.yaml",
    "policies/trivy-repository-secret-v1.yaml",
)


def git(*arguments: str, environment: dict[str, str] | None = None,
        data: bytes | None = None) -> bytes:
    return subprocess.run(
        ["git", "--literal-pathspecs", "-C", str(ROOT), *arguments], input=data, env=environment,
        check=True, capture_output=True,
    ).stdout


def archive_files(tree: str) -> dict[str, bytes | None]:
    # No --worktree-attributes: immutable downloads use attributes in this tree.
    with tarfile.open(fileobj=io.BytesIO(git("archive", "--format=tar", tree))) as archive:
        return {
            member.name.rstrip("/") + ("/" if member.isdir() else ""):
                archive.extractfile(member).read() if member.isfile() else None
            for member in archive.getmembers()
        }


class TrivyActionArchiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="secpal-action-archive-")
        self.addCleanup(self.temporary.cleanup)
        self.environment = dict(os.environ, GIT_INDEX_FILE=str(Path(self.temporary.name) / "index"))
        git("read-tree", git("write-tree").decode().strip(), environment=self.environment)
        # Capture tracked working-tree bytes, including staged additions, without
        # modifying the real index or including untracked qualification artifacts.
        git("add", "--all", "--force", "--pathspec-from-file=-", "--pathspec-file-nul",
            environment=self.environment, data=git("ls-files", "-z"))
        self.tree = git("write-tree", environment=self.environment).decode().strip()

    def assert_archive_contract(self, tree: str) -> None:
        files = archive_files(tree)
        for path in REQUIRED_FILES:
            self.assertTrue(path in files, f"required action runtime file excluded: {path}")
            self.assertEqual(files[path], git("show", f"{tree}:{path}"), path)
        unexpected = [
            path for path in files
            if path.startswith(".github/")
            and path not in {".github/", ".github/actions/"}
            and not path.startswith(ACTION_DIRECTORY)
        ]
        self.assertEqual(unexpected, [], "unrelated .github content exported")

    def test_candidate_archive_contains_only_required_action_surface(self) -> None:
        self.assert_archive_contract(self.tree)
        # Execute the existing identity owner with only the exported runtime
        # closure available. Its semantics and bundle digest must stay unchanged.
        exported = Path(self.temporary.name) / "exported"
        files = archive_files(self.tree)
        for path in REQUIRED_FILES:
            target = exported / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(files[path])
        identity_command = [
            "python3", "-I", "-c",
            "import runpy,sys; print(runpy.run_path(sys.argv[1])['configuration_identity']())",
        ]
        self.assertEqual(
            subprocess.check_output(identity_command + [str(exported / REQUIRED_FILES[1])]),
            subprocess.check_output(identity_command + [str(ROOT / REQUIRED_FILES[1])]),
        )

    def test_archive_contract_rejects_runtime_exclusion_and_unrelated_exports(self) -> None:
        attributes = git("show", f"{self.tree}:.gitattributes")
        mutations = (
            ".github export-ignore\n",  # Parent pruning defeats child overrides.
            ".github/actions export-ignore\n",
            *(f"{path} export-ignore\n" for path in REQUIRED_FILES),
            ".github/workflows -export-ignore\n",
            ".github/ISSUE_TEMPLATE -export-ignore\n",
            ".github/instructions -export-ignore\n",
            ".github/actions/setup-node-with-deps -export-ignore\n",
        )
        for mutation in mutations:
            with self.subTest(attribute=mutation.strip()):
                blob = git("hash-object", "-w", "--stdin", data=attributes + mutation.encode()).decode().strip()
                git("update-index", "--cacheinfo", f"100644,{blob},.gitattributes", environment=self.environment)
                tree = git("write-tree", environment=self.environment).decode().strip()
                with self.assertRaises(AssertionError):
                    self.assert_archive_contract(tree)


if __name__ == "__main__":
    unittest.main()
