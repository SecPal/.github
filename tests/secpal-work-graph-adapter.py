#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""GitHub read-adapter evidence for the work-graph resolver.

These cases drive the real subprocess boundary against a controlled fake `gh`
executable, so they prove argument construction, pagination, failure handling,
and read-only operation. Graph semantics are proven separately from synthetic
snapshots in tests/secpal-work-graph-unit.py.
"""

from __future__ import annotations

import io
import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import TestCase, main

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from secpal_work_graph import cli, github, model, replan_cli, replanning, resolver  # noqa: E402

REPO = "SecPal/.github"
OTHER_REPO = "SecPal/api"

FAKE_GH = '''#!/usr/bin/env python3
import json
import os
import re
import sys

argv = sys.argv[1:]
body = sys.stdin.read()
with open(os.environ["FAKE_GH_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps({"argv": argv, "body": body}) + "\\n")

script = json.loads(open(os.environ["FAKE_GH_SCRIPT"], encoding="utf-8").read())
request = json.loads(body)
operation = re.search(r"query\\s+(\\w+)", request["query"]).group(1)
variables = request.get("variables", {})
key = "{}:{}/{}#{}:{}".format(
    operation,
    variables.get("owner", ""),
    variables.get("name", ""),
    variables.get("number", ""),
    variables.get("cursor") or "",
)
if key not in script:
    sys.stderr.write("fake gh: unexpected request " + key + "\\n")
    sys.exit(9)
response = script[key]
if response.get("__raw") is not None:
    sys.stdout.write(response["__raw"])
    sys.exit(response.get("__exit", 0))
sys.stdout.write(json.dumps(response))
sys.exit(1 if response.get("errors") else 0)
'''


def issue_payload(
    number,
    *,
    repository=REPO,
    state="OPEN",
    state_reason=None,
    body="## Acceptance Criteria\n\n- proven\n",
    parent=None,
    sub_issues=(),
    blocked_by=(),
    labels=(),
    blocking=0,
    claims=(),
    sub_cursor=None,
    dependency_cursor=None,
    blocking_cursor=None,
):
    owner, name = repository.split("/")

    def reference(value):
        target_repository, _, target_number = value.rpartition("#")
        target_owner, target_name = target_repository.split("/")
        return {
            "number": int(target_number),
            "repository": {"nameWithOwner": f"{target_owner}/{target_name}"},
        }

    return {
        "data": {
            "repository": {
                "issue": {
                    "number": number,
                    "id": f"ISSUE_{number}",
                    "title": f"Issue {number}",
                    "url": f"https://github.com/{owner}/{name}/issues/{number}",
                    "state": state,
                    "stateReason": state_reason,
                    "body": body,
                    "repository": {"id": f"REPO_{owner}_{name}", "nameWithOwner": repository},
                    "parent": reference(parent) if parent else None,
                    "labels": {
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "nodes": [{"name": label} for label in labels],
                    },
                    "subIssues": {
                        "pageInfo": {
                            "hasNextPage": sub_cursor is not None,
                            "endCursor": sub_cursor,
                        },
                        "nodes": [reference(value) for value in sub_issues],
                    },
                    "blockedBy": {
                        "pageInfo": {
                            "hasNextPage": dependency_cursor is not None,
                            "endCursor": dependency_cursor,
                        },
                        "nodes": [reference(value) for value in blocked_by],
                    },
                    "blocking": {
                        "totalCount": len(blocking) if isinstance(blocking, (list, tuple)) else blocking,
                        "pageInfo": {
                            "hasNextPage": blocking_cursor is not None,
                            "endCursor": blocking_cursor,
                        },
                        "nodes": (
                            [reference(value) for value in blocking]
                            if isinstance(blocking, (list, tuple))
                            else []
                        ),
                    },
                    "closedByPullRequestsReferences": {
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "nodes": [
                            {
                                "number": pull_number,
                                "url": f"https://github.com/{repository}/pull/{pull_number}",
                                "state": pull_state,
                                "author": ({"login": login} if login else None),
                                "repository": {"nameWithOwner": repository},
                            }
                            for pull_number, pull_state, login in claims
                        ],
                    },
                }
            }
        }
    }


def page_payload(connection, payload):
    return {"data": {"repository": {"issue": {connection: payload}}}}


def page(connection, nodes, *, cursor=None):
    def reference(value):
        repository, _, number = value.rpartition("#")
        return {"number": int(number), "repository": {"nameWithOwner": repository}}

    return page_payload(
        connection,
        {
            "pageInfo": {"hasNextPage": cursor is not None, "endCursor": cursor},
            "nodes": [reference(value) for value in nodes],
        },
    )


class AdapterTestCase(TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        base = Path(self.directory.name)
        self.script_path = base / "script.json"
        self.log_path = base / "calls.jsonl"
        binary_directory = base / "bin"
        binary_directory.mkdir()
        self.gh_path = binary_directory / "gh"
        self.gh_path.write_text(FAKE_GH, encoding="utf-8")
        self.gh_path.chmod(self.gh_path.stat().st_mode | stat.S_IXUSR)
        self.log_path.write_text("", encoding="utf-8")

    def adapter(self, script, **options):
        self.script_path.write_text(json.dumps(script), encoding="utf-8")
        environment = dict(os.environ)
        environment["FAKE_GH_SCRIPT"] = str(self.script_path)
        environment["FAKE_GH_LOG"] = str(self.log_path)
        return github.GitHubReadAdapter(
            gh_executable=str(self.gh_path), environment=environment, **options
        )

    def calls(self):
        return [
            json.loads(line)
            for line in self.log_path.read_text(encoding="utf-8").splitlines()
            if line
        ]

    def run_command(self, script, *arguments):
        """Drive the real CLI against the fake gh, which it inherits from the environment."""
        self.script_path.write_text(json.dumps(script), encoding="utf-8")
        os.environ["FAKE_GH_SCRIPT"] = str(self.script_path)
        os.environ["FAKE_GH_LOG"] = str(self.log_path)
        self.addCleanup(os.environ.pop, "FAKE_GH_SCRIPT", None)
        self.addCleanup(os.environ.pop, "FAKE_GH_LOG", None)
        stdout, stderr = io.StringIO(), io.StringIO()
        code = cli.main(["--gh", str(self.gh_path), *arguments], stdout=stdout, stderr=stderr)
        return code, stdout.getvalue(), stderr.getvalue()


class SnapshotLoadingTests(AdapterTestCase):
    @staticmethod
    def prerequisite_request(current, external):
        return {
            "current_issue": current,
            "finding": {
                "classification": "MISSING_PREREQUISITE",
                "technically_blocking": True,
                "mechanically_blocking": True,
                "timing": "BEFORE_FREEZE",
                "risk": ["P2"],
            },
            "operation": {
                "kind": "INSERT_PREREQUISITE",
                "issue": {
                    "alias": "prerequisite",
                    "repository": REPO,
                    "title": "Prerequisite",
                    "body": "## Acceptance Criteria\n\n- Complete.\n",
                },
                "move_current_blockers": [external],
            },
        }

    def test_replanning_upgrades_an_external_blocker_before_rewiring_it(self):
        current = f"{REPO}#2"
        external = f"{OTHER_REPO}#44"
        script = {
            f"WorkGraphIssue:{REPO}#1:": issue_payload(1, sub_issues=(current,)),
            f"WorkGraphIssue:{REPO}#2:": issue_payload(
                2, parent=f"{REPO}#1", blocked_by=(external,)
            ),
            f"WorkGraphIssue:{OTHER_REPO}#44:": issue_payload(
                44, repository=OTHER_REPO, blocking=(current,)
            ),
        }
        request = self.prerequisite_request(current, external)

        snapshot, _ = replan_cli._load_plan_snapshot(self.adapter(script), request)
        self.assertTrue(snapshot.require(external).blocking_observable)
        plan = replanning.build_plan(snapshot, request, actor="alice")
        self.assertEqual(
            [step.kind for step in plan.steps if "BLOCKED_BY" in step.kind],
            ["ADD_BLOCKED_BY", "ADD_BLOCKED_BY", "REMOVE_BLOCKED_BY"],
        )

    def test_replanning_upgrades_the_exact_obsolete_dependency_endpoint(self):
        current = f"{REPO}#2"
        external = f"{OTHER_REPO}#44"
        script = {
            f"WorkGraphIssue:{REPO}#1:": issue_payload(1, sub_issues=(current,)),
            f"WorkGraphIssue:{REPO}#2:": issue_payload(
                2, parent=f"{REPO}#1", blocked_by=(external,)
            ),
            f"WorkGraphIssue:{OTHER_REPO}#44:": issue_payload(
                44, repository=OTHER_REPO, blocking=(current,)
            ),
        }
        request = {
            "current_issue": current,
            "finding": {
                "classification": "IN_CONTRACT_DEFECT",
                "technically_blocking": True,
                "mechanically_blocking": True,
                "timing": "BEFORE_FREEZE",
                "risk": ["P2"],
            },
            "operation": {
                "kind": "REMOVE_OBSOLETE_DEPENDENCY",
                "blocker": external,
                "contract_no_longer_requires_blocker": True,
            },
        }

        snapshot, _ = replan_cli._load_plan_snapshot(self.adapter(script), request)
        plan = replanning.build_plan(snapshot, request, actor="alice")

        self.assertTrue(snapshot.require(external).blocking_observable)
        self.assertEqual(plan.steps[0].kind, "REMOVE_BLOCKED_BY")

    def test_replanning_retains_endpoint_observability_after_rewiring(self):
        current = f"{REPO}#2"
        prerequisite = f"{REPO}#3"
        external = f"{OTHER_REPO}#44"
        script = {
            f"WorkGraphIssue:{REPO}#1:": issue_payload(
                1, sub_issues=(prerequisite, current)
            ),
            f"WorkGraphIssue:{REPO}#2:": issue_payload(
                2, parent=f"{REPO}#1", blocked_by=(prerequisite,)
            ),
            f"WorkGraphIssue:{REPO}#3:": issue_payload(
                3, parent=f"{REPO}#1", blocked_by=(external,), blocking=(current,)
            ),
            f"WorkGraphIssue:{OTHER_REPO}#44:": issue_payload(
                44, repository=OTHER_REPO, blocking=(prerequisite,)
            ),
        }

        snapshot, _ = replan_cli._load_plan_snapshot(
            self.adapter(script), self.prerequisite_request(current, external)
        )

        self.assertTrue(snapshot.require(external).blocking_observable)

    def test_replanning_upgrades_an_external_prerequisite_before_promotion(self):
        current = f"{REPO}#2"
        external = f"{OTHER_REPO}#44"
        script = {
            f"WorkGraphIssue:{REPO}#1:": issue_payload(1, sub_issues=(current,)),
            f"WorkGraphIssue:{REPO}#2:": issue_payload(
                2, parent=f"{REPO}#1", blocked_by=(external,)
            ),
            f"WorkGraphIssue:{OTHER_REPO}#44:": issue_payload(
                44, repository=OTHER_REPO, blocking=(current,)
            ),
        }
        request = {
            "current_issue": current,
            "finding": {
                "classification": "PROMOTE_TO_SUB_EPIC",
                "technically_blocking": True,
                "mechanically_blocking": True,
                "timing": "BEFORE_FREEZE",
                "risk": ["P2"],
            },
            "operation": {
                "kind": "PROMOTE_TO_SUB_EPIC",
                "children": [
                    {
                        "alias": "contract-a",
                        "repository": REPO,
                        "title": "Contract A",
                        "body": "## Acceptance Criteria\n\n- A.\n",
                    },
                    {
                        "alias": "contract-b",
                        "repository": REPO,
                        "title": "Contract B",
                        "body": "## Acceptance Criteria\n\n- B.\n",
                    },
                ],
                "blocked_by_placement": {external: ["contract-a"]},
                "blocking_placement": {},
            },
        }

        snapshot, _ = replan_cli._load_plan_snapshot(self.adapter(script), request)
        self.assertTrue(snapshot.require(external).blocking_observable)
        plan = replanning.build_plan(snapshot, request, actor="alice")
        self.assertEqual(plan.steps[2].kind, "ADD_BLOCKED_BY")

    def test_replanning_upgrades_an_external_dependent_before_promotion(self):
        current = f"{REPO}#2"
        dependent = f"{OTHER_REPO}#45"
        script = {
            f"WorkGraphIssue:{REPO}#1:": issue_payload(1, sub_issues=(current,)),
            f"WorkGraphIssue:{REPO}#2:": issue_payload(
                2, parent=f"{REPO}#1", blocking=(dependent,)
            ),
            f"WorkGraphIssue:{OTHER_REPO}#45:": issue_payload(
                45, repository=OTHER_REPO, blocked_by=(current,)
            ),
        }
        request = {
            "current_issue": current,
            "finding": {
                "classification": "PROMOTE_TO_SUB_EPIC",
                "technically_blocking": True,
                "mechanically_blocking": True,
                "timing": "BEFORE_FREEZE",
                "risk": ["P2"],
            },
            "operation": {
                "kind": "PROMOTE_TO_SUB_EPIC",
                "children": [
                    {
                        "alias": "contract-a",
                        "repository": REPO,
                        "title": "Contract A",
                        "body": "## Acceptance Criteria\n\n- A.\n",
                    },
                    {
                        "alias": "contract-b",
                        "repository": REPO,
                        "title": "Contract B",
                        "body": "## Acceptance Criteria\n\n- B.\n",
                    },
                ],
                "blocked_by_placement": {},
                "blocking_placement": {dependent: ["contract-b"]},
            },
        }

        snapshot, _ = replan_cli._load_plan_snapshot(self.adapter(script), request)
        self.assertTrue(snapshot.require(dependent).blocking_observable)
        replanning.build_plan(snapshot, request, actor="alice")

    def test_replanning_rejects_incomplete_reverse_edge_pagination(self):
        current = f"{REPO}#2"
        external = f"{OTHER_REPO}#44"
        partial = issue_payload(
            44,
            repository=OTHER_REPO,
            blocking=(current,),
            blocking_cursor="BLOCK1",
        )
        script = {
            f"WorkGraphIssue:{REPO}#1:": issue_payload(1, sub_issues=(current,)),
            f"WorkGraphIssue:{REPO}#2:": issue_payload(
                2, parent=f"{REPO}#1", blocked_by=(external,)
            ),
            f"WorkGraphIssue:{OTHER_REPO}#44:": partial,
            f"WorkGraphBlocking:{OTHER_REPO}#44:BLOCK1": with_error(
                page("blocking", ()), "FORBIDDEN", "blocking", "nodes", "0"
            ),
        }

        with self.assertRaisesRegex(replanning.PlanError, "incomplete"):
            replan_cli._load_plan_snapshot(
                self.adapter(script), self.prerequisite_request(current, external)
            )

    def test_replanning_rejects_inconsistent_endpoint_directions(self):
        current = f"{REPO}#2"
        external = f"{OTHER_REPO}#44"
        script = {
            f"WorkGraphIssue:{REPO}#1:": issue_payload(1, sub_issues=(current,)),
            f"WorkGraphIssue:{REPO}#2:": issue_payload(
                2, parent=f"{REPO}#1", blocked_by=(external,)
            ),
            f"WorkGraphIssue:{OTHER_REPO}#44:": issue_payload(
                44, repository=OTHER_REPO, blocking=()
            ),
        }

        with self.assertRaisesRegex(replanning.PlanError, "disagree"):
            replan_cli._load_plan_snapshot(
                self.adapter(script), self.prerequisite_request(current, external)
            )

    def test_completed_endpoint_read_still_rejects_the_intermediate_native_limit(self):
        current = f"{REPO}#2"
        external = f"{OTHER_REPO}#44"
        dependents = tuple(f"{OTHER_REPO}#{number}" for number in range(100, 149))
        script = {
            f"WorkGraphIssue:{REPO}#1:": issue_payload(1, sub_issues=(current,)),
            f"WorkGraphIssue:{REPO}#2:": issue_payload(
                2, parent=f"{REPO}#1", blocked_by=(external,)
            ),
            f"WorkGraphIssue:{OTHER_REPO}#44:": issue_payload(
                44, repository=OTHER_REPO, blocking=(current, *dependents)
            ),
        }
        request = self.prerequisite_request(current, external)
        snapshot, _ = replan_cli._load_plan_snapshot(self.adapter(script), request)

        with self.assertRaisesRegex(replanning.PlanError, "canonical structural"):
            replanning.build_plan(snapshot, request, actor="alice")

    def test_snapshot_upgrades_a_dependency_read_when_it_becomes_scope(self):
        dependency_first = {
            "WorkGraphIssue:SecPal/.github#1:": issue_payload(
                1, sub_issues=(f"{REPO}#3",), blocked_by=(f"{REPO}#2",)
            ),
            "WorkGraphIssue:SecPal/.github#3:": issue_payload(
                3, parent=f"{REPO}#1", sub_issues=(f"{REPO}#2",)
            ),
            "WorkGraphIssue:SecPal/.github#2:": issue_payload(
                2, parent=f"{REPO}#3", sub_issues=(f"{REPO}#4",)
            ),
            "WorkGraphIssue:SecPal/.github#4:": issue_payload(4, parent=f"{REPO}#2"),
        }
        snapshot, root = github.load_snapshot(self.adapter(dependency_first), f"{REPO}#1")
        resolution = resolver.resolve(snapshot, root)
        self.assertEqual(snapshot.nodes[f"{REPO}#2"].children, (f"{REPO}#4",))
        self.assertFalse(resolution.states[f"{REPO}#2"].leaf)
        self.assertTrue(resolution.states[f"{REPO}#4"].ready)
        numbers = [json.loads(call["body"])["variables"]["number"] for call in self.calls()]
        self.assertEqual(numbers.count(2), 2)

        scope_first = {
            "WorkGraphIssue:SecPal/.github#1:": issue_payload(
                1, sub_issues=(f"{REPO}#2",), blocked_by=(f"{REPO}#2",)
            ),
            "WorkGraphIssue:SecPal/.github#2:": issue_payload(
                2, parent=f"{REPO}#1", sub_issues=(f"{REPO}#3",)
            ),
            "WorkGraphIssue:SecPal/.github#3:": issue_payload(3, parent=f"{REPO}#2"),
        }
        self.log_path.write_text("", encoding="utf-8")
        github.load_snapshot(self.adapter(scope_first), f"{REPO}#1")
        numbers = [json.loads(call["body"])["variables"]["number"] for call in self.calls()]
        self.assertEqual(numbers.count(2), 1)

    def test_native_relationships_become_a_normalized_snapshot(self):
        script = {
            "WorkGraphIssue:SecPal/.github#1:": issue_payload(
                1, sub_issues=(f"{OTHER_REPO}#7", f"{REPO}#2"), blocking=3
            ),
            "WorkGraphIssue:SecPal/api#7:": issue_payload(
                7,
                repository=OTHER_REPO,
                parent=f"{REPO}#1",
                labels=("priority: high", "area: api"),
                claims=((11, "OPEN", "bob"),),
            ),
            "WorkGraphIssue:SecPal/.github#2:": issue_payload(
                2,
                parent=f"{REPO}#1",
                blocked_by=(f"{REPO}#3",),
                body="Parent: #1\n\nNo criteria here.\n",
            ),
            "WorkGraphIssue:SecPal/.github#3:": issue_payload(
                3, state="CLOSED", state_reason="COMPLETED"
            ),
        }
        snapshot, _ = github.load_snapshot(self.adapter(script), f"{REPO}#1")

        root = snapshot.nodes[f"{REPO}#1"]
        self.assertEqual(root.children, (f"{OTHER_REPO}#7", f"{REPO}#2"))
        self.assertEqual(root.blocking_count, 3)
        self.assertTrue(root.has_acceptance_criteria)

        cross_repository = snapshot.nodes[f"{OTHER_REPO}#7"]
        self.assertEqual(cross_repository.parent, f"{REPO}#1")
        self.assertEqual(cross_repository.priority_labels, ("priority: high",))
        self.assertEqual(
            cross_repository.claims,
            (model.Claim("bob", f"{OTHER_REPO}#11", f"https://github.com/{OTHER_REPO}/pull/11"),),
        )

        leaf = snapshot.nodes[f"{REPO}#2"]
        self.assertEqual(leaf.blocked_by, (f"{REPO}#3",))
        self.assertFalse(leaf.has_acceptance_criteria)
        self.assertEqual(leaf.mirror_relationships, ("parent",))

        dependency = snapshot.nodes[f"{REPO}#3"]
        self.assertTrue(dependency.is_done)

    def test_every_call_is_a_read_only_graphql_query(self):
        script = {"WorkGraphIssue:SecPal/.github#1:": issue_payload(1)}
        github.load_snapshot(self.adapter(script), f"{REPO}#1")
        calls = self.calls()
        self.assertTrue(calls)
        for call in calls:
            self.assertEqual(call["argv"], ["api", "graphql", "--input", "-"])
            document = json.loads(call["body"])["query"]
            self.assertTrue(document.lstrip().startswith("query "))
            self.assertNotIn("mutation", document)

    def test_pagination_is_consumed_completely(self):
        script = {
            "WorkGraphIssue:SecPal/.github#1:": issue_payload(
                1,
                sub_issues=(f"{REPO}#2",),
                blocked_by=(f"{REPO}#4",),
                sub_cursor="SUB1",
                dependency_cursor="DEP1",
            ),
            "WorkGraphSubIssues:SecPal/.github#1:SUB1": page("subIssues", (f"{REPO}#3",)),
            "WorkGraphBlockedBy:SecPal/.github#1:DEP1": page("blockedBy", (f"{REPO}#5",)),
            "WorkGraphIssue:SecPal/.github#2:": issue_payload(2, parent=f"{REPO}#1"),
            "WorkGraphIssue:SecPal/.github#3:": issue_payload(3, parent=f"{REPO}#1"),
            "WorkGraphIssue:SecPal/.github#4:": issue_payload(4),
            "WorkGraphIssue:SecPal/.github#5:": issue_payload(5),
        }
        snapshot, _ = github.load_snapshot(self.adapter(script), f"{REPO}#1")
        root = snapshot.nodes[f"{REPO}#1"]
        self.assertEqual(root.children, (f"{REPO}#2", f"{REPO}#3"))
        self.assertEqual(root.blocked_by, (f"{REPO}#4", f"{REPO}#5"))

    def test_pagination_rejects_a_repeated_cursor(self):
        class RepeatingCursorAdapter:
            calls = 0

            def query(self, document, variables):
                self.calls += 1
                if self.calls > 1:
                    raise AssertionError("pagination requested the repeated cursor again")
                payload = page("subIssues", (), cursor="SAME")
                return github.GraphQLResponse(payload["data"], ())

        adapter = RepeatingCursorAdapter()
        issue = issue_payload(1, sub_cursor="SAME")["data"]["repository"]["issue"]
        with self.assertRaisesRegex(github.GitHubError, "cursor"):
            github._paginate(adapter, "subIssues", issue, {"owner": "SecPal", "name": ".github", "number": 1})
        self.assertEqual(adapter.calls, 1)

    def test_ancestors_are_read_without_pulling_in_sibling_scopes(self):
        # The fake gh fails on any unscripted request, so the absence of a
        # request for #9 is asserted by the run completing at all.
        script = {
            "WorkGraphIssue:SecPal/.github#1:": issue_payload(
                1,
                state="CLOSED",
                state_reason="COMPLETED",
                sub_issues=(f"{REPO}#2", f"{REPO}#9"),
            ),
            "WorkGraphIssue:SecPal/.github#2:": issue_payload(2, parent=f"{REPO}#1"),
        }
        snapshot, _ = github.load_snapshot(self.adapter(script), f"{REPO}#2")
        self.assertIn(f"{REPO}#1", snapshot.nodes)
        self.assertNotIn(f"{REPO}#9", snapshot.nodes)
        state = resolver.resolve(snapshot, f"{REPO}#2").states[f"{REPO}#2"]
        self.assertFalse(state.ready)
        self.assertEqual(state.reasons, (resolver.REASON_CLOSED_ANCESTOR,))

    def test_each_issue_is_fetched_once_per_invocation(self):
        script = {
            "WorkGraphIssue:SecPal/.github#1:": issue_payload(
                1, sub_issues=(f"{REPO}#2", f"{REPO}#3")
            ),
            "WorkGraphIssue:SecPal/.github#2:": issue_payload(
                2, parent=f"{REPO}#1", blocked_by=(f"{REPO}#3",)
            ),
            "WorkGraphIssue:SecPal/.github#3:": issue_payload(3, parent=f"{REPO}#1"),
        }
        github.load_snapshot(self.adapter(script), f"{REPO}#1")
        documents = [json.loads(call["body"])["variables"]["number"] for call in self.calls()]
        self.assertEqual(sorted(documents), [1, 2, 3])


def with_error(payload, kind, *path_tail):
    """Attach a field-level GraphQL access error to an otherwise readable issue."""
    document = json.loads(json.dumps(payload))
    document.setdefault("errors", []).append(
        {"type": kind, "path": ["repository", "issue", *path_tail], "message": "not accessible"}
    )
    return document


class RequiredInputObservabilityTests(AdapterTestCase):
    """Section 3.5: an inaccessible native input never becomes absent data."""

    def test_an_unobservable_parent_is_not_reported_as_a_root(self):
        cases = {
            "forbidden": with_error(issue_payload(1), "FORBIDDEN", "parent"),
            "not found": with_error(issue_payload(1), "NOT_FOUND", "parent"),
            "nested path": with_error(issue_payload(1), "FORBIDDEN", "parent", "repository"),
        }
        for label, payload in cases.items():
            with self.subTest(case=label):
                snapshot, _ = github.load_snapshot(
                    self.adapter({"WorkGraphIssue:SecPal/.github#1:": payload}), f"{REPO}#1"
                )
                node = snapshot.nodes[f"{REPO}#1"]
                self.assertIsNone(node.parent)
                self.assertFalse(node.parent_observable)
                state = resolver.resolve(snapshot, f"{REPO}#1").states[f"{REPO}#1"]
                self.assertFalse(state.ready)
                self.assertTrue(state.malformed)

    def test_a_null_parent_without_an_access_error_is_a_legitimate_root(self):
        snapshot, _ = github.load_snapshot(
            self.adapter({"WorkGraphIssue:SecPal/.github#1:": issue_payload(1)}), f"{REPO}#1"
        )
        node = snapshot.nodes[f"{REPO}#1"]
        self.assertIsNone(node.parent)
        self.assertTrue(node.parent_observable)
        self.assertTrue(resolver.resolve(snapshot, f"{REPO}#1").states[f"{REPO}#1"].ready)

    def test_partially_readable_relationship_data_is_not_a_complete_list(self):
        # A payload carrying usable nodes plus an access error underneath the
        # connection must never be normalized into a shorter complete list.
        for connection, kind in (("subIssues", "FORBIDDEN"), ("blockedBy", "NOT_FOUND")):
            with self.subTest(connection=connection, error=kind):
                base = issue_payload(
                    2, parent=f"{REPO}#1", sub_issues=(f"{REPO}#5",), blocked_by=(f"{REPO}#6",)
                )
                script = {
                    "WorkGraphIssue:SecPal/.github#1:": issue_payload(
                        1, sub_issues=(f"{REPO}#2", f"{REPO}#3")
                    ),
                    "WorkGraphIssue:SecPal/.github#2:": with_error(base, kind, connection, "nodes", "1"),
                    "WorkGraphIssue:SecPal/.github#3:": issue_payload(3, parent=f"{REPO}#1"),
                    "WorkGraphIssue:SecPal/.github#5:": issue_payload(5, parent=f"{REPO}#2"),
                    "WorkGraphIssue:SecPal/.github#6:": issue_payload(6),
                }
                snapshot, _ = github.load_snapshot(self.adapter(script), f"{REPO}#1")
                unreadable = snapshot.nodes[f"{REPO}#2"]
                self.assertFalse(unreadable.resolved)
                self.assertEqual(unreadable.unresolved_reason, kind)
                resolution = resolver.resolve(snapshot, f"{REPO}#1")
                self.assertFalse(resolution.complete)
                self.assertIsNone(resolution.select_next("alice").selected)

    def test_dependency_reads_do_not_require_irrelevant_sub_issues(self):
        dependency = with_error(
            issue_payload(2, state="CLOSED", state_reason="COMPLETED"),
            "FORBIDDEN",
            "subIssues",
        )
        script = {
            "WorkGraphIssue:SecPal/.github#1:": issue_payload(1, blocked_by=(f"{REPO}#2",)),
            "WorkGraphIssue:SecPal/.github#2:": dependency,
        }
        snapshot, root = github.load_snapshot(self.adapter(script), f"{REPO}#1")
        self.assertTrue(snapshot.nodes[f"{REPO}#2"].is_done)
        self.assertTrue(resolver.resolve(snapshot, root).states[f"{REPO}#1"].ready)

    def test_a_partial_follow_up_page_is_not_a_successful_page(self):
        script = {
            "WorkGraphIssue:SecPal/.github#1:": issue_payload(
                1, sub_issues=(f"{REPO}#2",), sub_cursor="SUB1"
            ),
            "WorkGraphSubIssues:SecPal/.github#1:SUB1": with_error(
                page("subIssues", (f"{REPO}#3",)), "FORBIDDEN", "subIssues", "nodes", "0"
            ),
            "WorkGraphIssue:SecPal/.github#2:": issue_payload(2, parent=f"{REPO}#1"),
            "WorkGraphIssue:SecPal/.github#3:": issue_payload(3, parent=f"{REPO}#1"),
        }
        # Every referenced issue is readable, so only the partial page can fail this.
        with self.assertRaises(github.GitHubError):
            github.load_snapshot(self.adapter(script), f"{REPO}#1")

    def test_unreadable_labels_leave_the_node_resolvable(self):
        # Selection metadata is not an input to READY, so it must not make the
        # whole node unresolved.
        snapshot, _ = github.load_snapshot(
            self.adapter(
                {"WorkGraphIssue:SecPal/.github#1:": with_error(issue_payload(1), "FORBIDDEN", "labels")}
            ),
            f"{REPO}#1",
        )
        node = snapshot.nodes[f"{REPO}#1"]
        self.assertTrue(node.resolved)
        self.assertFalse(node.priority_labels_observable)
        self.assertEqual(node.priority_labels, ())
        self.assertTrue(resolver.resolve(snapshot, f"{REPO}#1").states[f"{REPO}#1"].ready)


class ClaimObservationTests(AdapterTestCase):
    def test_only_open_pull_requests_with_a_named_author_are_claims(self):
        script = {
            "WorkGraphIssue:SecPal/.github#1:": issue_payload(
                1,
                claims=((10, "OPEN", "alice"), (11, "CLOSED", "bob"), (12, "OPEN", None)),
            )
        }
        snapshot, _ = github.load_snapshot(self.adapter(script), f"{REPO}#1")
        node = snapshot.nodes[f"{REPO}#1"]
        self.assertEqual(node.claims, (model.Claim("alice", f"{REPO}#10", node.claims[0].url),))
        self.assertTrue(node.claims_observable)

    def test_inaccessible_claim_data_is_reported_rather_than_assumed_absent(self):
        payload = issue_payload(1)
        payload["data"]["repository"]["issue"]["closedByPullRequestsReferences"] = None
        payload["errors"] = [
            {
                "type": "FORBIDDEN",
                "path": ["repository", "issue", "closedByPullRequestsReferences"],
                "message": "Resource not accessible",
            }
        ]
        snapshot, _ = github.load_snapshot(
            self.adapter({"WorkGraphIssue:SecPal/.github#1:": payload}), f"{REPO}#1"
        )
        node = snapshot.nodes[f"{REPO}#1"]
        self.assertFalse(node.claims_observable)
        self.assertEqual(node.claims, ())

    def test_an_unreadable_claim_page_degrades_exactly_like_an_unreadable_first_page(self):
        # Claim observability is all-or-nothing per invocation, so a readable
        # first page plus an unreadable continuation is not a complete claim set.
        first = issue_payload(1, claims=((10, "OPEN", "alice"),))
        connection = first["data"]["repository"]["issue"]["closedByPullRequestsReferences"]
        connection["pageInfo"] = {"hasNextPage": True, "endCursor": "CLAIM1"}
        continuation = with_error(
            page_payload(
                "closedByPullRequestsReferences",
                {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": []},
            ),
            "FORBIDDEN",
            "closedByPullRequestsReferences",
            "nodes",
            "0",
        )
        snapshot, root = github.load_snapshot(
            self.adapter(
                {
                    "WorkGraphIssue:SecPal/.github#1:": first,
                    "WorkGraphClaims:SecPal/.github#1:CLAIM1": continuation,
                }
            ),
            f"{REPO}#1",
        )
        node = snapshot.nodes[f"{REPO}#1"]
        self.assertFalse(node.claims_observable)
        self.assertEqual(node.claims, ())
        state = resolver.resolve(snapshot, root).states[f"{REPO}#1"]
        self.assertTrue(state.ready)
        self.assertFalse(state.active)


class CanonicalIdentityTests(AdapterTestCase):
    """One issue has exactly one identity: the one GitHub returns."""

    CANONICAL = {
        "WorkGraphIssue:SecPal/.github#1:": issue_payload(1, sub_issues=(f"{REPO}#2",)),
        "WorkGraphIssue:SecPal/.github#2:": issue_payload(2, parent=f"{REPO}#1"),
    }

    def test_a_reference_github_canonicalizes_resolves_to_the_canonical_identity(self):
        # GitHub accepts `secpal/.github` and answers with `SecPal/.github`. The
        # requested spelling is an input reference, never a second graph node.
        variant = dict(self.CANONICAL)
        variant["WorkGraphIssue:secpal/.github#1:"] = variant.pop(
            "WorkGraphIssue:SecPal/.github#1:"
        )
        code, output, _ = self.run_command(variant, "ready", "secpal/.github#1")
        document = json.loads(output)
        self.assertEqual(code, 0)
        self.assertEqual(document["scope_root"], f"{REPO}#1")
        self.assertEqual([node["key"] for node in document["ready"]], [f"{REPO}#2"])
        self.assertTrue(document["complete"])
        self.assertEqual(document["findings"], [])

        canonical = self.run_command(self.CANONICAL, "ready", f"{REPO}#1")
        self.assertEqual((code, output), canonical[:2])

    def test_an_incoherent_issue_number_is_a_read_boundary_failure(self):
        script = {"WorkGraphIssue:SecPal/.github#1:": issue_payload(7)}
        with self.assertRaises(github.GitHubError):
            github.load_snapshot(self.adapter(script), f"{REPO}#1")


class FailureTests(AdapterTestCase):
    def test_missing_issue_becomes_an_unresolved_node(self):
        script = {
            "WorkGraphIssue:SecPal/.github#1:": issue_payload(1, blocked_by=(f"{REPO}#404",)),
            "WorkGraphIssue:SecPal/.github#404:": {
                "data": {"repository": {"issue": None}},
                "errors": [
                    {
                        "type": "NOT_FOUND",
                        "path": ["repository", "issue"],
                        "message": "Could not resolve to an Issue",
                    }
                ],
            },
        }
        snapshot, _ = github.load_snapshot(self.adapter(script), f"{REPO}#1")
        missing = snapshot.nodes[f"{REPO}#404"]
        self.assertFalse(missing.resolved)
        self.assertEqual(missing.unresolved_reason, "NOT_FOUND")

    def test_an_unreadable_sub_issue_reports_incompleteness_instead_of_failing(self):
        script = {
            "WorkGraphIssue:SecPal/.github#1:": issue_payload(
                1, sub_issues=(f"{REPO}#2", f"{REPO}#404")
            ),
            "WorkGraphIssue:SecPal/.github#2:": issue_payload(2, parent=f"{REPO}#1"),
            "WorkGraphIssue:SecPal/.github#404:": {
                "data": {"repository": {"issue": None}},
                "errors": [{"type": "NOT_FOUND", "path": ["repository", "issue"]}],
            },
        }
        code, output, _ = self.run_command(script, "ready", f"{REPO}#1")
        document = json.loads(output)
        self.assertEqual(code, 0)
        self.assertEqual([node["key"] for node in document["ready"]], [f"{REPO}#2"])
        self.assertFalse(document["complete"])
        self.assertIn(
            "unresolved_sub_issue", {finding["code"] for finding in document["findings"]}
        )

    def test_operational_failures_are_raised_instead_of_becoming_absence(self):
        cases = {
            "unparseable output": {"__raw": "not json at all", "__exit": 0},
            "transport failure": {"__raw": "", "__exit": 1},
            "server error": {
                "data": None,
                "errors": [{"type": "INTERNAL", "message": "something failed"}],
            },
        }
        for label, response in cases.items():
            with self.subTest(case=label):
                adapter = self.adapter({"WorkGraphIssue:SecPal/.github#1:": response})
                with self.assertRaises(github.GitHubError):
                    github.load_snapshot(adapter, f"{REPO}#1")

    def test_unresolvable_scope_root_is_raised(self):
        script = {
            "WorkGraphIssue:SecPal/.github#1:": {
                "data": {"repository": {"issue": None}},
                "errors": [{"type": "NOT_FOUND", "path": ["repository", "issue"]}],
            }
        }
        with self.assertRaises(github.GitHubError):
            github.load_snapshot(self.adapter(script), f"{REPO}#1")

    def test_the_node_budget_fails_closed(self):
        script = {
            "WorkGraphIssue:SecPal/.github#1:": issue_payload(1, sub_issues=(f"{REPO}#2",)),
            "WorkGraphIssue:SecPal/.github#2:": issue_payload(2, parent=f"{REPO}#1"),
        }
        with self.assertRaises(github.GitHubError):
            github.load_snapshot(self.adapter(script, max_nodes=1), f"{REPO}#1")


class ExecutorIdentityTests(AdapterTestCase):
    def test_authenticated_identity_resolves_the_invocation_context(self):
        script = {"WorkGraphViewer:/#:": {"data": {"viewer": {"login": "carol"}}}}
        self.assertEqual(self.adapter(script).viewer_login(), "carol")


class CommandTests(AdapterTestCase):
    """The five commands #669 requires, rendered from one resolved model."""

    SCRIPT = {
        "WorkGraphIssue:SecPal/.github#1:": issue_payload(
            1, sub_issues=(f"{REPO}#2", f"{REPO}#3")
        ),
        "WorkGraphIssue:SecPal/.github#2:": issue_payload(2, parent=f"{REPO}#1"),
        "WorkGraphIssue:SecPal/.github#3:": issue_payload(
            3, parent=f"{REPO}#1", blocked_by=(f"{REPO}#4",), body="No criteria.\n"
        ),
        "WorkGraphIssue:SecPal/.github#4:": issue_payload(4),
    }

    def command(self, *arguments):
        return self.run_command(self.SCRIPT, *arguments)

    def test_show_renders_the_normalized_subtree(self):
        code, output, _ = self.command("show", f"{REPO}#1")
        document = json.loads(output)
        self.assertEqual(code, 0)
        self.assertEqual([node["key"] for node in document["nodes"]], [f"{REPO}#{n}" for n in (1, 2, 3)])
        self.assertEqual(document["nodes"][1]["path"], [0])
        self.assertTrue(document["complete"])

    def test_ready_returns_only_the_executable_leaf(self):
        code, output, _ = self.command("ready", f"{REPO}#1")
        document = json.loads(output)
        self.assertEqual(code, 0)
        self.assertEqual([node["key"] for node in document["ready"]], [f"{REPO}#2"])
        self.assertEqual(
            document["not_ready_leaves"],
            [
                {
                    "key": f"{REPO}#3",
                    "reasons": ["unsatisfied_dependency", "missing_acceptance_criteria"],
                }
            ],
        )

    def test_next_selects_one_leaf_for_the_given_executor(self):
        code, output, _ = self.command("next", f"{REPO}#1", "--executor", "alice")
        document = json.loads(output)
        self.assertEqual(code, 0)
        self.assertEqual(document["selected"]["key"], f"{REPO}#2")
        self.assertIsNone(document["no_selection_reason"])
        self.assertEqual(document["executor"], "alice")

    def test_next_reports_incomplete_inputs_instead_of_a_canonical_answer(self):
        script = {
            "WorkGraphIssue:SecPal/.github#1:": issue_payload(
                1, sub_issues=(f"{REPO}#404", f"{REPO}#2")
            ),
            "WorkGraphIssue:SecPal/.github#2:": issue_payload(2, parent=f"{REPO}#1"),
            "WorkGraphIssue:SecPal/.github#404:": {
                "data": {"repository": {"issue": None}},
                "errors": [{"type": "NOT_FOUND", "path": ["repository", "issue"]}],
            },
        }
        code, output, _ = self.run_command(script, "next", f"{REPO}#1", "--executor", "alice")
        document = json.loads(output)
        self.assertEqual(code, 1)
        self.assertEqual(document["status"], "incomplete_inputs")
        self.assertIsNone(document["selected"])
        self.assertIsNone(document["no_selection_reason"])
        self.assertEqual(document["incomplete_reason"], "incomplete_candidate_scope")
        # The known sibling is still truthfully READY on the `ready` surface.
        self.assertEqual(document["ready"], [f"{REPO}#2"])
        ready_code, ready_output, _ = self.run_command(script, "ready", f"{REPO}#1")
        self.assertEqual(ready_code, 0)
        self.assertEqual([node["key"] for node in json.loads(ready_output)["ready"]], [f"{REPO}#2"])

    def test_all_closed_leaves_explain_an_empty_executable_set(self):
        script = {
            "WorkGraphIssue:SecPal/.github#1:": issue_payload(1, sub_issues=(f"{REPO}#2",)),
            "WorkGraphIssue:SecPal/.github#2:": issue_payload(
                2, parent=f"{REPO}#1", state="CLOSED", state_reason="COMPLETED"
            ),
        }
        code, output, _ = self.run_command(script, "next", f"{REPO}#1", "--executor", "alice")
        document = json.loads(output)
        self.assertEqual(code, 0)
        self.assertEqual(document["no_selection_reason"], resolver.NO_READY_LEAF)
        self.assertEqual(document["not_ready_leaves"], [{"key": f"{REPO}#2", "reasons": ["closed"]}])
        _, text, _ = self.run_command(
            script, "--format", "text", "next", f"{REPO}#1", "--executor", "alice"
        )
        self.assertIn(f"---  {REPO}#2 closed", text)

    def test_validate_reports_structural_findings_only(self):
        code, output, _ = self.command("validate", f"{REPO}#1")
        document = json.loads(output)
        self.assertEqual(code, 1)
        self.assertEqual(
            {finding["code"] for finding in document["findings"]},
            {"missing_acceptance_criteria"},
        )

    def test_validate_issue_explains_one_issue(self):
        ready_code, ready_output, _ = self.command("validate-issue", f"{REPO}#2")
        blocked_code, blocked_output, _ = self.command("validate-issue", f"{REPO}#3")
        self.assertEqual(ready_code, 0)
        self.assertTrue(json.loads(ready_output)["issue"]["ready"])
        self.assertEqual(blocked_code, 1)
        blocked = json.loads(blocked_output)["issue"]
        self.assertTrue(blocked["blocked"])
        self.assertFalse(blocked["malformed"])
        self.assertEqual(
            blocked["reasons"], ["unsatisfied_dependency", "missing_acceptance_criteria"]
        )

    def test_machine_output_is_deterministic_and_text_uses_the_same_model(self):
        first = self.command("show", f"{REPO}#1")[1]
        second = self.command("show", f"{REPO}#1")[1]
        self.assertEqual(first, second)
        text = self.command("--format", "text", "ready", f"{REPO}#1")[1]
        self.assertIn(f"READY {REPO}#2", text)
        self.assertIn(f"{REPO}#3", text)

    def test_invalid_references_are_rejected_without_contacting_github(self):
        for reference in (
            "not-an-issue",
            "foo#1",
            "12",
            "https://example.com/x",
            "https://gitlab.com/acme/project/issues/5",
            "https://github.com/SecPal/.github/pull/5",
            "SecPal/.github#x",
        ):
            with self.subTest(reference=reference):
                code, _, stderr = self.command("show", reference)
                self.assertEqual(code, 2)
                self.assertEqual(json.loads(stderr)["error"]["code"], "invalid_reference")
        self.assertEqual(self.calls(), [])

    def test_a_bare_number_resolves_against_an_explicit_repository(self):
        code, output, _ = self.command("--repo", REPO, "validate-issue", "2")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)["issue"]["key"], f"{REPO}#2")


class SubprocessSafetyTests(TestCase):
    def test_github_access_is_bounded_and_never_shelled_out(self):
        # Structural evidence for the stated invariant that the read boundary
        # runs gh as an argument vector, never through a shell.
        source = (ROOT / "scripts/secpal_work_graph/github.py").read_text(encoding="utf-8")
        self.assertNotIn("shell=True", source)
        self.assertGreater(github.GitHubReadAdapter().timeout, 0)

    def test_the_entrypoint_runs(self):
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts/secpal-work-graph.py"), "--help"],
            capture_output=True,
            text=True,
            check=True,
        )
        for command in ("show", "validate", "ready", "next", "validate-issue"):
            self.assertIn(command, completed.stdout)


if __name__ == "__main__":
    main()
