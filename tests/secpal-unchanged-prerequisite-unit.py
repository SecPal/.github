# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Closed #1048 unchanged-head prerequisite admission regressions."""

from __future__ import annotations

import base64
import hashlib
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from secpal_pr_review import unchanged_head_prerequisite as prerequisite


@dataclass(frozen=True)
class Comment:
    comment_id: str
    database_id: int
    body_digest: str
    reply_to_id: str | None = None


@dataclass(frozen=True)
class Thread:
    thread_id: str
    is_resolved: bool
    is_outdated: bool
    comments: tuple[Comment, ...]


@dataclass(frozen=True)
class Target:
    repository: str
    pull_request_number: int
    state: str
    head_sha: str
    thread: Thread


class ExactPrerequisiteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.case = prerequisite.CASES["deployment-281"]
        body = self.case.comment_body
        self.target = Target(
            self.case.repository,
            self.case.pull_request,
            "OPEN",
            self.case.head,
            Thread(
                self.case.thread_id,
                False,
                False,
                (Comment(self.case.comment_node, self.case.comment_id,
                         hashlib.sha256(body.encode()).hexdigest()),),
            ),
        )
        agents = (
            "[canonical signing authority](https://github.com/SecPal/.github/"
            "blob/main/docs/work-graph-contract.md#532-signing-authority)"
        ).encode()
        self.responses = {
            self.case.pr_endpoint: {
                "state": "open", "draft": False, "commits": 1,
                "head": {"sha": self.case.head},
                "base": {"ref": "main", "repo": {"full_name": self.case.repository}},
            },
            self.case.commits_endpoint: [{
                "sha": self.case.head,
                "commit": {"verification": {"verified": True, "reason": "valid"}},
            }],
            self.case.commit_endpoint: {
                "sha": self.case.head,
                "commit": {"tree": {"sha": self.case.tree},
                           "verification": {"verified": True, "reason": "valid"}},
                "parents": [{"sha": self.case.parent}],
            },
            self.case.comment_endpoint: {
                "id": self.case.comment_id,
                "node_id": self.case.comment_node,
                "body": body,
                "path": "AGENTS.md",
                "created_at": "2026-10-02T00:46:05Z",
                "commit_id": self.case.head,
                "original_commit_id": self.case.head,
                "pull_request_url": self.case.pr_url,
            },
            self.case.agents_endpoint: {
                "encoding": "base64", "size": len(agents),
                "content": base64.b64encode(agents).decode(),
                "sha": hashlib.sha1(
                    b"blob " + str(len(agents)).encode() + b"\0" + agents
                ).hexdigest(),
            },
            prerequisite.CANONICAL_PR_ENDPOINT: {
                "state": "closed", "merged": True,
                "merge_commit_sha": prerequisite.CANONICAL_MERGE,
                "merged_at": "2026-10-02T07:58:45Z",
            },
            prerequisite.CANONICAL_MAIN_ENDPOINT: {"sha": "a" * 40},
        }
        self.git_outputs = {
            ("remote", "get-url", "origin"): "https://github.com/SecPal/.github.git\n",
            ("rev-parse", "HEAD"): "a" * 40 + "\n",
            ("merge-base", "--is-ancestor", prerequisite.CANONICAL_MERGE, "HEAD"): "",
            ("rev-list", "--parents", "-n", "1", prerequisite.CANONICAL_MERGE):
                prerequisite.CANONICAL_MERGE + " " + prerequisite.CANONICAL_PARENT + "\n",
            ("show", prerequisite.CANONICAL_PARENT + ":docs/work-graph-contract.md"):
                "### 5.3.1 Initial Automated Review\n",
            ("show", prerequisite.CANONICAL_MERGE + ":docs/work-graph-contract.md"):
                "### 5.3.2 Signing Authority\n`SECPAL_SIGNING_FORMAT: SSH`\n",
            ("show", "HEAD:docs/work-graph-contract.md"):
                "### 5.3.2 Signing Authority\n`SECPAL_SIGNING_FORMAT: SSH`\n",
        }

    def authenticate(self):
        return prerequisite.authenticate(
            self.case, self.target,
            get_json=lambda endpoint: self.responses[endpoint],
            git_text=lambda *args: self.git_outputs[args],
            verify_signature=lambda _verification: prerequisite.SIGNER_FINGERPRINT,
        )

    def test_exact_case_passes_and_binds_source(self) -> None:
        result = self.authenticate()
        self.assertEqual(result["repository"], self.case.repository)
        self.assertEqual(result["head"], self.case.head)
        self.assertEqual(result["tree"], self.case.tree)
        self.assertEqual(result["thread_id"], self.case.thread_id)
        self.assertEqual(result["canonical_merge"], prerequisite.CANONICAL_MERGE)

    def test_changed_head_rejects(self) -> None:
        self.responses[self.case.pr_endpoint]["head"]["sha"] = "b" * 40
        with self.assertRaises(prerequisite.PrerequisiteError):
            self.authenticate()

    def test_changed_tree_rejects(self) -> None:
        self.responses[self.case.commit_endpoint]["commit"]["tree"]["sha"] = "b" * 40
        with self.assertRaises(prerequisite.PrerequisiteError):
            self.authenticate()

    def test_changed_thread_rejects(self) -> None:
        self.responses[self.case.comment_endpoint]["body"] = "different finding"
        with self.assertRaises(prerequisite.PrerequisiteError):
            self.authenticate()

    def test_original_finding_must_predate_merge(self) -> None:
        self.responses[self.case.comment_endpoint]["created_at"] = "2026-10-02T08:00:00Z"
        with self.assertRaises(prerequisite.PrerequisiteError):
            self.authenticate()

    def test_canonical_anchor_must_be_absent_then_present(self) -> None:
        self.git_outputs[("show", prerequisite.CANONICAL_PARENT + ":docs/work-graph-contract.md")] = (
            "### 5.3.2 Signing Authority\n"
        )
        with self.assertRaises(prerequisite.PrerequisiteError):
            self.authenticate()

    def test_ssh_assertion_outside_linked_section_rejects(self) -> None:
        self.git_outputs[("show", "HEAD:docs/work-graph-contract.md")] = (
            "### 5.3.2 Signing Authority\nNo SSH assertion here.\n"
            "### 5.4 Other Authority\n`SECPAL_SIGNING_FORMAT: SSH`\n"
        )
        with self.assertRaises(prerequisite.PrerequisiteError):
            self.authenticate()

    def test_merged_section_must_itself_contain_assertion(self) -> None:
        self.git_outputs[("show", prerequisite.CANONICAL_MERGE + ":docs/work-graph-contract.md")] = (
            "### 5.3.2 Signing Authority\nNo SSH assertion here.\n"
            "### 5.4 Other Authority\n`SECPAL_SIGNING_FORMAT: SSH`\n"
        )
        with self.assertRaises(prerequisite.PrerequisiteError):
            self.authenticate()

    def test_unverified_commit_rejects(self) -> None:
        self.responses[self.case.commits_endpoint][0]["commit"]["verification"]["verified"] = False
        with self.assertRaises(prerequisite.PrerequisiteError):
            self.authenticate()

    def test_unknown_case_has_no_generic_fallback(self) -> None:
        self.assertNotIn("SecPal/api", prerequisite.CASES)

    def test_wrong_signer_rejects(self) -> None:
        with self.assertRaises(prerequisite.PrerequisiteError):
            prerequisite.authenticate(
                self.case, self.target,
                get_json=lambda endpoint: self.responses[endpoint],
                git_text=lambda *args: self.git_outputs[args],
                verify_signature=lambda _verification: "SHA256:another-key",
            )

    def test_malformed_commit_list_rejects_without_trusting_last_item(self) -> None:
        self.responses[self.case.commits_endpoint] = [None]
        with self.assertRaises(prerequisite.PrerequisiteError):
            self.authenticate()

    def test_unaccepted_canonical_main_rejects(self) -> None:
        self.git_outputs[("rev-parse", "HEAD")] = "b" * 40
        with self.assertRaises(prerequisite.PrerequisiteError):
            self.authenticate()

    def test_candidate_link_missing_rejects(self) -> None:
        source = b"No canonical signing anchor"
        self.responses[self.case.agents_endpoint] = {
            "encoding": "base64", "size": len(source),
            "content": base64.b64encode(source).decode(),
            "sha": hashlib.sha1(
                b"blob " + str(len(source)).encode() + b"\0" + source
            ).hexdigest(),
        }
        with self.assertRaises(prerequisite.PrerequisiteError):
            self.authenticate()

    def test_pr_must_still_be_ready(self) -> None:
        self.responses[self.case.pr_endpoint]["draft"] = True
        with self.assertRaises(prerequisite.PrerequisiteError):
            self.authenticate()

    def test_exact_scope_has_only_the_two_authenticated_cases(self) -> None:
        self.assertEqual(set(prerequisite.CASES), {
            "deployment-281", "operations-51",
        })
        self.assertEqual(
            prerequisite.CASES["operations-51"].thread_id,
            "PRRT_kwDOUA9VeM6oMLJH",
        )


if __name__ == "__main__":
    unittest.main()
