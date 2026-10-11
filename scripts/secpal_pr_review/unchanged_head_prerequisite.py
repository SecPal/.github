# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""The two exact unchanged-head #1048 external-prerequisite findings.

This is not a repository-wide recovery rule.  A caller selects one of two
accepted-main records; GitHub and committed canonical history supply every
authoritative source fact again before a detached late disposition is issued
or consumed.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable


class PrerequisiteError(RuntimeError):
    """The exact historical prerequisite case cannot be authenticated."""


CANONICAL_MERGE = "70cf7ee7bb45ed8d91d6b6e6c2fb5ef8c14ff946"
CANONICAL_PARENT = "9ed2d54addb03cfb52ba38d7e4844eef2aa7f7cd"
CANONICAL_PR_ENDPOINT = "repos/SecPal/.github/pulls/1050"
CANONICAL_MAIN_ENDPOINT = "repos/SecPal/.github/commits/main"
CANONICAL_PATH = "docs/work-graph-contract.md"
CANONICAL_HEADING = "### 5.3.2 Signing Authority"
CANONICAL_ASSERTION = "`SECPAL_SIGNING_FORMAT: SSH`"
CANONICAL_LINK = (
    "https://github.com/SecPal/.github/blob/main/"
    "docs/work-graph-contract.md#532-signing-authority"
)
# This key is already the accepted SecPal deployment lifecycle signer.  The
# exact-case path does not enroll another signer or register operations for
# generic review-helper authority.
SIGNER_FINGERPRINT = "SHA256:GCaB6jwhFkzWkmHek5dVQNgxEb1JiLMOyhmIAcd0Vsc"


@dataclass(frozen=True)
class Case:
    case_id: str
    repository: str
    delivery_issue: int
    pull_request: int
    head: str
    tree: str
    parent: str
    commit_count: int
    thread_id: str
    comment_id: int
    comment_node: str
    comment_body: str

    @property
    def pr_endpoint(self) -> str:
        return f"repos/{self.repository}/pulls/{self.pull_request}"

    @property
    def commits_endpoint(self) -> str:
        return f"{self.pr_endpoint}/commits?per_page=100"

    @property
    def commit_endpoint(self) -> str:
        return f"repos/{self.repository}/commits/{self.head}"

    @property
    def comment_endpoint(self) -> str:
        return f"repos/{self.repository}/pulls/comments/{self.comment_id}"

    @property
    def agents_endpoint(self) -> str:
        return f"repos/{self.repository}/contents/AGENTS.md?ref={self.head}"

    @property
    def pr_url(self) -> str:
        return f"https://api.github.com/{self.pr_endpoint}"


CASES = {
    "deployment-281": Case(
        "deployment-281", "SecPal/deployment", 280, 281,
        "d930375c6614b6912a6f94644a014434b5e7a7ff",
        "df774b9722851c94f87e09a763feadbe1c832d38",
        "cbedf317bf134e5ea746c4df053e1aa3930c1f0b", 1,
        "PRRT_kwDOTqT8Oc6oMNJ3", 4161882788,
        "PRRC_kwDOTqT8Oc74EUqk",
        "The linked `#532-signing-authority` section does not exist on "
        "`SecPal/.github` main; it is introduced only by currently open, "
        "blocked PR SecPal/.github#1050. If this consumer lands first, "
        "the new normative signing instruction has no published authority. "
        "Make that upstream authority a merge prerequisite, or link to an "
        "already-published canonical section.\n\n"
        "This issue also appears on line 114 of the same file.",
    ),
    "operations-51": Case(
        "operations-51", "SecPal/operations", 50, 51,
        "a4bf2a7acf0c51b02613c8069acb45202dbd5d65",
        "c7105d6f5a31898c3913232e7a71570ae230f027",
        "783a41e0a9ec4b18684d326cdb67e95b58a712e3", 2,
        "PRRT_kwDOUA9VeM6oMLJH", 4161869929,
        "PRRC_kwDOUA9VeM74ERhp",
        "This canonical anchor does not yet exist on `SecPal/.github` "
        "main; it is introduced only by the still-open SecPal/.github#1050. "
        "If this PR merges first, the signing-authority link has no published "
        "target, so the claimed canonical authority is unavailable. Make "
        "#1050 an explicit merge dependency and merge it first, or reference "
        "an already-published canonical section.\n\n"
        "This issue also appears on line 53 of the same file.",
    ),
}


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise PrerequisiteError(reason)


def _timestamp(value: Any) -> datetime:
    _require(isinstance(value, str) and value.endswith("Z"),
             "GitHub timestamp is malformed")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PrerequisiteError("GitHub timestamp is malformed") from exc


def _signing_section_has_ssh_authority(contract: str) -> bool:
    """Bind the assertion to the linked heading, not an unrelated section."""

    lines = contract.splitlines()
    if lines.count(CANONICAL_HEADING) != 1:
        return False
    start = lines.index(CANONICAL_HEADING) + 1
    section: list[str] = []
    for line in lines[start:]:
        if line.startswith(("# ", "## ", "### ")):
            break
        section.append(line)
    return "\n".join(section).count(CANONICAL_ASSERTION) == 1


def authenticate(
    case: Case,
    target: Any,
    *,
    get_json: Callable[[str], Any],
    git_text: Callable[..., str],
    verify_signature: Callable[[dict[str, Any]], str],
) -> dict[str, Any]:
    """Re-derive one exact case; no caller-selected source or thread authority."""

    _require(CASES.get(case.case_id) is case,
             "unchanged-head prerequisite case is not registered")
    body_digest = hashlib.sha256(case.comment_body.encode("utf-8")).hexdigest()
    _require(
        getattr(target, "repository", None) == case.repository
        and getattr(target, "pull_request_number", None) == case.pull_request
        and getattr(target, "state", None) == "OPEN"
        and getattr(target, "head_sha", None) == case.head,
        "review thread pull request or head changed",
    )
    thread = getattr(target, "thread", None)
    comments = getattr(thread, "comments", None)
    _require(
        getattr(thread, "thread_id", None) == case.thread_id
        and getattr(thread, "is_resolved", None) is False
        and type(getattr(thread, "is_outdated", None)) is bool
        and type(comments) is tuple
        and len(comments) == 1
        and comments[0].comment_id == case.comment_node
        and comments[0].database_id == case.comment_id
        and comments[0].body_digest == body_digest
        and comments[0].reply_to_id is None,
        "review thread or original finding changed",
    )

    pr = get_json(case.pr_endpoint)
    _require(
        isinstance(pr, dict)
        and pr.get("state") == "open"
        and pr.get("draft") is False
        and type(pr.get("commits")) is int
        and pr.get("commits") == case.commit_count
        and isinstance(pr.get("head"), dict)
        and pr["head"].get("sha") == case.head
        and isinstance(pr.get("base"), dict)
        and pr["base"].get("ref") == "main"
        and isinstance(pr["base"].get("repo"), dict)
        and pr["base"]["repo"].get("full_name") == case.repository,
        "pull request no longer matches the exact Ready candidate",
    )
    commits = get_json(case.commits_endpoint)
    _require(
        isinstance(commits, list)
        and len(commits) == case.commit_count
        and all(
            isinstance(item, dict)
            and isinstance(item.get("commit"), dict)
            and isinstance(item["commit"].get("verification"), dict)
            and item["commit"]["verification"].get("verified") is True
            and item["commit"]["verification"].get("reason") == "valid"
            for item in commits
        )
        and commits[-1].get("sha") == case.head,
        "complete candidate commit set is not GitHub Verified",
    )
    commit = get_json(case.commit_endpoint)
    _require(
        isinstance(commit, dict)
        and commit.get("sha") == case.head
        and isinstance(commit.get("commit"), dict)
        and isinstance(commit["commit"].get("tree"), dict)
        and commit["commit"]["tree"].get("sha") == case.tree
        and isinstance(commit["commit"].get("verification"), dict)
        and commit["commit"]["verification"].get("verified") is True
        and commit["commit"]["verification"].get("reason") == "valid"
        and verify_signature(commit["commit"]["verification"])
        == SIGNER_FINGERPRINT
        and isinstance(commit.get("parents"), list)
        and len(commit["parents"]) == 1
        and isinstance(commit["parents"][0], dict)
        and commit["parents"][0].get("sha") == case.parent,
        "candidate HEAD, TREE, parent or verification changed",
    )

    comment = get_json(case.comment_endpoint)
    _require(
        isinstance(comment, dict)
        and comment.get("id") == case.comment_id
        and comment.get("node_id") == case.comment_node
        and comment.get("body") == case.comment_body
        and comment.get("path") == "AGENTS.md"
        and comment.get("commit_id") == case.head
        and comment.get("original_commit_id") == case.head
        and comment.get("pull_request_url") == case.pr_url,
        "original finding identity or exact reviewed commit changed",
    )
    original_time = _timestamp(comment.get("created_at"))
    canonical_pr = get_json(CANONICAL_PR_ENDPOINT)
    _require(
        isinstance(canonical_pr, dict)
        and canonical_pr.get("state") == "closed"
        and canonical_pr.get("merged") is True
        and canonical_pr.get("merge_commit_sha") == CANONICAL_MERGE,
        "canonical prerequisite merge identity is not accepted",
    )
    merged_time = _timestamp(canonical_pr.get("merged_at"))
    _require(original_time < merged_time,
             "finding was not created before the prerequisite merge")

    agents = get_json(case.agents_endpoint)
    _require(
        isinstance(agents, dict)
        and agents.get("encoding") == "base64"
        and isinstance(agents.get("size"), int)
        and not isinstance(agents["size"], bool)
        and 0 < agents["size"] <= 32768
        and isinstance(agents.get("content"), str)
        and isinstance(agents.get("sha"), str),
        "candidate AGENTS source is malformed",
    )
    try:
        source = base64.b64decode(agents["content"].replace("\n", ""), validate=True)
        source_text = source.decode("utf-8")
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise PrerequisiteError("candidate AGENTS source is malformed") from exc
    blob_sha = hashlib.sha1(
        b"blob " + str(len(source)).encode() + b"\0" + source
    ).hexdigest()
    _require(
        len(source) == agents["size"]
        and agents["sha"] == blob_sha
        and source_text.count(CANONICAL_LINK) == 1,
        "candidate source does not bind the exact canonical anchor",
    )

    main = get_json(CANONICAL_MAIN_ENDPOINT)
    _require(isinstance(main, dict) and isinstance(main.get("sha"), str),
             "accepted canonical main is unavailable")
    _require(
        git_text("remote", "get-url", "origin").strip()
        in {"https://github.com/SecPal/.github.git", "git@github.com:SecPal/.github.git"}
        and git_text("rev-parse", "HEAD").strip() == main["sha"],
        "local canonical source is not exact accepted main",
    )
    git_text("merge-base", "--is-ancestor", CANONICAL_MERGE, "HEAD")
    _require(
        git_text("rev-list", "--parents", "-n", "1", CANONICAL_MERGE).split()
        == [CANONICAL_MERGE, CANONICAL_PARENT],
        "canonical prerequisite ancestry changed",
    )
    old_contract = git_text("show", f"{CANONICAL_PARENT}:{CANONICAL_PATH}")
    merged_contract = git_text("show", f"{CANONICAL_MERGE}:{CANONICAL_PATH}")
    current_contract = git_text("show", f"HEAD:{CANONICAL_PATH}")
    _require(
        CANONICAL_HEADING not in old_contract
        and _signing_section_has_ssh_authority(merged_contract)
        and _signing_section_has_ssh_authority(current_contract),
        "canonical signing prerequisite is not proven absent-then-present",
    )
    return {
        "case_id": case.case_id,
        "repository": case.repository,
        "delivery_issue": case.delivery_issue,
        "pull_request": case.pull_request,
        "head": case.head,
        "tree": case.tree,
        "parent": case.parent,
        "thread_id": case.thread_id,
        "comment_node": case.comment_node,
        "comment_id": case.comment_id,
        "finding_body_digest": body_digest,
        "comment_created_at": comment["created_at"],
        "candidate_agents_blob": blob_sha,
        "canonical_merge": CANONICAL_MERGE,
        "canonical_merged_at": canonical_pr["merged_at"],
        "canonical_anchor": CANONICAL_LINK,
        "finding_status": "VALID_WHEN_CREATED_PREREQUISITE_NOW_SATISFIED",
    }
