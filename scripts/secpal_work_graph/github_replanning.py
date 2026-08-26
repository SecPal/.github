# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Exact GitHub mutation boundary for canonical replanning plans."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from . import replanning
from .github import GitHubError, GitHubGraphQLAdapter, VIEWER_QUERY
from .model import Snapshot

REPOSITORY_QUERY = """query ReplanRepository($owner:String!,$name:String!) {
  repository(owner:$owner,name:$name) { id nameWithOwner }
}"""

CREATE_ISSUE = """mutation ReplanCreateIssue($input:CreateIssueInput!) {
  createIssue(input:$input) {
    issue { id number url repository { id nameWithOwner } parent { id } }
  }
}"""
ADD_BLOCKED_BY = """mutation ReplanAddBlockedBy($input:AddBlockedByInput!) {
  addBlockedBy(input:$input) { issue { id } blockingIssue { id } }
}"""
REMOVE_BLOCKED_BY = """mutation ReplanRemoveBlockedBy($input:RemoveBlockedByInput!) {
  removeBlockedBy(input:$input) { issue { id } blockingIssue { id } }
}"""
REPRIORITIZE_SUB_ISSUE = """mutation ReplanPrioritizeSubIssue($input:ReprioritizeSubIssueInput!) {
  reprioritizeSubIssue(input:$input) { issue { id } }
}"""
ADD_SUB_ISSUE = """mutation ReplanAddSubIssue($input:AddSubIssueInput!) {
  addSubIssue(input:$input) { issue { id } subIssue { id } }
}"""


class MutationError(RuntimeError):
    """One bounded mutation failed; callers must stop without retrying."""


@dataclass
class GitHubMutationWriter:
    """Apply only the five mutations emitted by ``replanning.build_plan``."""

    adapter: GitHubGraphQLAdapter
    node_ids: dict[str, str] = field(default_factory=dict)
    repository_ids: dict[str, str] = field(default_factory=dict)
    alias_node_ids: dict[str, str] = field(default_factory=dict)
    created_identities: dict[str, replanning.CreatedIssueIdentity] = field(default_factory=dict)
    mutation_index: int = 0
    plan_digest: str = ""
    expected_actor: str = ""

    def _query(self, document: str, variables: Mapping[str, Any]) -> Mapping[str, Any]:
        try:
            response = self.adapter.query(document, variables)
        except GitHubError as exc:
            raise MutationError("GitHub rejected the bounded replanning mutation") from exc
        if response.errors or response.data is None:
            raise MutationError("GitHub returned an incomplete replanning mutation response")
        return response.data

    def prepare(self, plan: replanning.Plan, snapshot: Snapshot) -> None:
        """Resolve every stable ID before the first irreversible write."""

        self.plan_digest = plan.snapshot_digest
        self.expected_actor = plan.actor
        for node in snapshot.nodes.values():
            if node.node_id:
                self.node_ids[node.key] = node.node_id
            if node.repository_id:
                self.repository_ids[node.repository] = node.repository_id
        repositories = {
            str(step.arguments["repository"])
            for step in plan.steps
            if step.kind == "CREATE_ISSUE"
        }
        for repository in sorted(repositories - self.repository_ids.keys()):
            owner, name = repository.split("/", 1)
            data = self._query(REPOSITORY_QUERY, {"owner": owner, "name": name})
            live = data.get("repository") or {}
            if live.get("nameWithOwner") != repository or not live.get("id"):
                raise MutationError("target repository is missing or changed")
            self.repository_ids[repository] = str(live["id"])

        for step in plan.steps:
            for field_name in ("parent", "blocked", "blocker", "child", "before", "after"):
                reference = step.arguments.get(field_name)
                if isinstance(reference, str) and not reference.startswith("@"):
                    if reference not in self.node_ids:
                        raise MutationError(f"verified snapshot omitted native ID for {reference}")

    def _id(self, reference: str) -> str:
        if reference.startswith("@"):
            alias = reference[1:]
            value = self.alias_node_ids.get(alias)
        else:
            value = self.node_ids.get(reference)
        if not value:
            raise MutationError(f"mutation target {reference} has no verified native ID")
        return value

    def _client_id(self) -> str:
        self.mutation_index += 1
        return f"secpal-replan-{self.plan_digest[:16]}-{self.mutation_index}"

    def _assert_actor(self) -> None:
        data = self._query(VIEWER_QUERY, {})
        login = (data.get("viewer") or {}).get("login")
        if login != self.expected_actor:
            raise MutationError("authenticated actor changed before mutation")

    def restore_created(
        self, aliases: Mapping[str, replanning.CreatedIssueIdentity]
    ) -> None:
        for alias, identity in aliases.items():
            self.alias_node_ids[alias] = identity.node_id
            self.node_ids[identity.key] = identity.node_id
            repository, _ = identity.key.rsplit("#", 1)
            expected_repository_id = self.repository_ids.get(repository)
            if expected_repository_id != identity.repository_id:
                raise MutationError("recovery repository identity differs from verified state")

    def apply(
        self,
        step: replanning.Step,
        aliases: Mapping[str, replanning.CreatedIssueIdentity],
        *,
        plan: replanning.Plan,
        step_index: int,
    ) -> replanning.CreatedIssueIdentity | None:
        arguments = step.arguments
        self._assert_actor()
        client_id = self._client_id()
        if step.kind == "CREATE_ISSUE":
            repository = str(arguments["repository"])
            payload: dict[str, Any] = {
                "repositoryId": self.repository_ids[repository],
                "title": str(arguments["title"]),
                "body": replanning.created_issue_body(plan, step_index),
                "clientMutationId": client_id,
            }
            if arguments["parent"] is not None:
                payload["parentIssueId"] = self._id(str(arguments["parent"]))
            data = self._query(CREATE_ISSUE, {"input": payload})
            issue = ((data.get("createIssue") or {}).get("issue") or {})
            live_repository = (issue.get("repository") or {}).get("nameWithOwner")
            live_repository_id = (issue.get("repository") or {}).get("id")
            number = issue.get("number")
            node_id = issue.get("id")
            parent_id = (issue.get("parent") or {}).get("id")
            expected_parent_id = payload.get("parentIssueId")
            if (
                live_repository != repository
                or live_repository_id != self.repository_ids[repository]
                or not isinstance(number, int)
                or not node_id
                or parent_id != expected_parent_id
            ):
                raise MutationError("created issue identity or parent differs from the plan")
            canonical = f"{repository}#{number}"
            alias = str(arguments["alias"])
            self.alias_node_ids[alias] = str(node_id)
            self.node_ids[canonical] = str(node_id)
            identity = replanning.CreatedIssueIdentity(
                key=canonical,
                node_id=str(node_id),
                repository_id=str(live_repository_id),
            )
            self.created_identities[alias] = identity
            return identity

        if step.kind == "ADD_SUB_ISSUE":
            parent_id = self._id(str(arguments["parent"]))
            child_id = self._id(str(arguments["child"]))
            payload = {
                "issueId": parent_id,
                "subIssueId": child_id,
                "replaceParent": False,
                "clientMutationId": client_id,
            }
            data = self._query(ADD_SUB_ISSUE, {"input": payload})
            result = data.get("addSubIssue") or {}
            if (result.get("issue") or {}).get("id") != parent_id or (
                result.get("subIssue") or {}
            ).get("id") != child_id:
                raise MutationError("containment mutation returned different issue identities")
            return None

        if step.kind in {"ADD_BLOCKED_BY", "REMOVE_BLOCKED_BY"}:
            blocked_id = self._id(str(arguments["blocked"]))
            blocker_id = self._id(str(arguments["blocker"]))
            payload = {
                "issueId": blocked_id,
                "blockingIssueId": blocker_id,
                "clientMutationId": client_id,
            }
            document = ADD_BLOCKED_BY if step.kind == "ADD_BLOCKED_BY" else REMOVE_BLOCKED_BY
            field_name = "addBlockedBy" if step.kind == "ADD_BLOCKED_BY" else "removeBlockedBy"
            data = self._query(document, {"input": payload})
            result = data.get(field_name) or {}
            if (result.get("issue") or {}).get("id") != blocked_id or (
                result.get("blockingIssue") or {}
            ).get("id") != blocker_id:
                raise MutationError("dependency mutation returned different issue identities")
            return None

        if step.kind == "REPRIORITIZE_SUB_ISSUE":
            parent_id = self._id(str(arguments["parent"]))
            payload = {
                "issueId": parent_id,
                "subIssueId": self._id(str(arguments["child"])),
                "clientMutationId": client_id,
            }
            if "before" in arguments:
                payload["beforeId"] = self._id(str(arguments["before"]))
            else:
                payload["afterId"] = self._id(str(arguments["after"]))
            data = self._query(REPRIORITIZE_SUB_ISSUE, {"input": payload})
            if ((data.get("reprioritizeSubIssue") or {}).get("issue") or {}).get("id") != parent_id:
                raise MutationError("ordering mutation returned a different parent identity")
            return None

        raise MutationError(f"unsupported replanning step {step.kind}")
