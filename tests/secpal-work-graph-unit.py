#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Pure resolver and acceptance-criteria evidence for the work-graph resolver.

Semantics under test: docs/work-graph-contract.md. These cases prove the
machine-derivable rules of sections 1, 3, and 4 from synthetic snapshots, so no
GitHub access happens here.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase, main

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from secpal_work_graph import acceptance_criteria, model, resolver  # noqa: E402
from secpal_work_graph.model import Claim, Node, build_snapshot  # noqa: E402

REPO = "SecPal/.github"
OTHER_REPO = "SecPal/api"


def leaf(number: int, *, repository: str = REPO, **overrides) -> Node:
    """Build a node that is `READY` unless an override says otherwise."""
    fields = {
        "repository": repository,
        "number": number,
        "has_acceptance_criteria": True,
    }
    fields.update(overrides)
    return Node(**fields)


def epic(number: int, children: tuple[str, ...], *, repository: str = REPO, **overrides) -> Node:
    return leaf(number, repository=repository, children=children, **overrides)


def key(number: int, repository: str = REPO) -> str:
    return model.node_key(repository, number)


def closed(reason: str = model.COMPLETED) -> dict[str, object]:
    return {"state": model.CLOSED, "state_reason": reason}


class ReadyPredicateTests(TestCase):
    """Section 4.1 `READY` and its blocking reasons."""

    def resolve_leaf(self, *nodes: Node, root: str | None = None) -> resolver.Resolution:
        snapshot = build_snapshot(nodes)
        return resolver.resolve(snapshot, root or nodes[0].key)

    def test_standalone_root_leaf_is_ready(self):
        resolution = self.resolve_leaf(leaf(1))
        state = resolution.states[key(1)]
        self.assertTrue(state.ready)
        self.assertFalse(state.blocked)
        self.assertFalse(state.malformed)
        self.assertEqual(state.reasons, ())
        self.assertEqual(resolution.ready_leaves(), (key(1),))

    def test_nested_leaf_is_ready_and_its_epic_is_not(self):
        resolution = self.resolve_leaf(
            epic(1, (key(2),)),
            leaf(2, parent=key(1)),
        )
        self.assertFalse(resolution.states[key(1)].ready)
        self.assertIn(resolver.REASON_NOT_LEAF, resolution.states[key(1)].reasons)
        self.assertTrue(resolution.states[key(2)].ready)
        self.assertEqual(resolution.ready_leaves(), (key(2),))

    def test_ready_conditions_each_remove_the_leaf(self):
        cases = {
            resolver.REASON_CLOSED: leaf(2, parent=key(1), **closed()),
            resolver.REASON_MISSING_ACCEPTANCE_CRITERIA: leaf(2, parent=key(1), has_acceptance_criteria=False),
            resolver.REASON_NOT_LEAF: leaf(2, parent=key(1), children=(key(9),)),
        }
        for reason, node in cases.items():
            with self.subTest(reason=reason):
                resolution = self.resolve_leaf(epic(1, (key(2),)), node, leaf(9, parent=key(2)), root=key(1))
                state = resolution.states[key(2)]
                self.assertFalse(state.ready)
                self.assertIn(reason, state.reasons)

    def test_closed_ancestor_makes_open_leaf_unexecutable(self):
        resolution = self.resolve_leaf(
            epic(1, (key(2),), **closed()),
            leaf(2, parent=key(1)),
            root=key(1),
        )
        state = resolution.states[key(2)]
        self.assertFalse(state.ready)
        self.assertEqual(state.reasons, (resolver.REASON_CLOSED_ANCESTOR,))
        self.assertIn(
            model.Finding(resolver.FINDING_CLOSED_ANCESTOR, key(2), key(1)),
            resolution.findings,
        )

    def test_closed_ancestor_above_the_scope_root_still_applies(self):
        resolution = self.resolve_leaf(
            epic(1, (key(2),), **closed()),
            epic(2, (key(3),), parent=key(1)),
            leaf(3, parent=key(2)),
            root=key(2),
        )
        self.assertEqual(resolution.ancestors, (key(1),))
        self.assertFalse(resolution.states[key(3)].ready)
        self.assertIn(resolver.REASON_CLOSED_ANCESTOR, resolution.states[key(3)].reasons)

    def test_unresolved_ancestor_fails_closed_and_is_not_a_root_leaf(self):
        resolution = self.resolve_leaf(leaf(2, parent=key(1)))
        state = resolution.states[key(2)]
        self.assertFalse(state.ready)
        self.assertTrue(state.malformed)
        self.assertEqual(state.reasons, (resolver.REASON_UNRESOLVED_ANCESTOR,))
        self.assertFalse(resolution.complete)

    def test_containment_cycle_fails_closed_without_becoming_blocked(self):
        resolution = self.resolve_leaf(
            epic(1, (key(2),), parent=key(2)),
            leaf(2, parent=key(1), children=(key(1),)),
            root=key(1),
        )
        state = resolution.states[key(1)]
        self.assertFalse(state.ready)
        self.assertTrue(state.malformed)
        self.assertFalse(state.blocked)
        self.assertIn(resolver.REASON_CONTAINMENT_CYCLE, state.reasons)
        self.assertIn(
            resolver.FINDING_CONTAINMENT_CYCLE,
            {finding.code for finding in resolution.findings},
        )


class MalformedContainmentTests(TestCase):
    """Section 3.1 and 3.5 containment defects the resolver can observe."""

    def test_unresolvable_sub_issue_leaves_the_executable_set_incomplete(self):
        snapshot = build_snapshot([epic(1, (key(2), key(404))), leaf(2, parent=key(1))])
        resolution = resolver.resolve(snapshot, key(1))
        self.assertEqual(resolution.ready_leaves(), (key(2),))
        self.assertFalse(resolution.complete)
        self.assertIn(
            resolver.FINDING_UNRESOLVED_SUB_ISSUE,
            {finding.code for finding in resolution.findings},
        )

    def test_an_unobservable_parent_is_not_a_standalone_root(self):
        # Section 3.5: an inaccessible parent is not the same as no parent, and
        # that holds wherever it sits in the chain.
        blind = {"parent": None, "parent_observable": False}
        cases = {
            "the leaf itself": ([leaf(1, **blind)], key(1)),
            "an ancestor": ([epic(1, (key(2),), **blind), leaf(2, parent=key(1))], key(2)),
        }
        for label, (nodes, subject) in cases.items():
            with self.subTest(unobservable_on=label):
                state = resolver.resolve(build_snapshot(nodes), key(1)).states[subject]
                self.assertFalse(state.ready)
                self.assertTrue(state.malformed)
                self.assertIn(resolver.REASON_UNRESOLVED_ANCESTOR, state.reasons)

    def test_a_containment_edge_the_child_does_not_confirm_is_not_selectable(self):
        # One invocation reads several issues, so a parent's sub-issue list and
        # the child's own parent can disagree. Neither is preferred.
        for label, child_parent in (("another parent", key(8)), ("no parent", None)):
            with self.subTest(child_says=label):
                snapshot = build_snapshot(
                    [epic(1, (key(2), key(3))), leaf(2, parent=child_parent), leaf(3, parent=key(1))]
                )
                resolution = resolver.resolve(snapshot, key(1))
                state = resolution.states[key(2)]
                self.assertFalse(state.ready)
                self.assertTrue(state.malformed)
                self.assertIn(resolver.REASON_CONTAINMENT_INCONSISTENT, state.reasons)
                self.assertIn(
                    model.Finding(resolver.FINDING_CONTAINMENT_INCONSISTENT, key(2), key(1)),
                    resolution.findings,
                )
                self.assertNotIn(key(2), resolution.ready_leaves())
                self.assertIsNone(resolution.select_next("alice").selected)


class SelectionInputTests(TestCase):
    """Sections 1.1 and 1.2: selection metadata is an input to `NEXT` only."""

    def test_unobservable_priority_labels_do_not_change_ready(self):
        snapshot = build_snapshot([leaf(1, priority_labels_observable=False)])
        state = resolver.resolve(snapshot, key(1)).states[key(1)]
        self.assertTrue(state.ready)
        self.assertFalse(state.blocked)

    def test_unobservable_priority_labels_are_never_silently_ranked_as_unlabeled(self):
        snapshot = build_snapshot([leaf(1, priority_labels_observable=False)])
        result = resolver.resolve(snapshot, key(1)).select_next("alice")
        self.assertIsNone(result.selected)
        self.assertIsNone(result.no_selection_reason)
        self.assertEqual(result.incomplete_reason, resolver.INCOMPLETE_SELECTION_METADATA)


class NextCandidateUniverseTests(TestCase):
    """Section 4.2 and 4.3: `NEXT` needs the whole candidate set, not a subset."""

    def test_an_unreadable_sibling_suspends_next_but_not_the_known_ready_leaf(self):
        snapshot = build_snapshot([epic(1, (key(404), key(2))), leaf(2, parent=key(1))])
        resolution = resolver.resolve(snapshot, key(1))
        # Section 3.1: containment never blocks a sibling, so the known leaf is
        # still truthfully READY and `ready`/`show` may report it.
        self.assertTrue(resolution.states[key(2)].ready)
        self.assertEqual(resolution.ready_leaves(), (key(2),))
        self.assertFalse(resolution.complete)
        # The unreadable sibling could outrank it, so `NEXT` is not derivable.
        result = resolution.select_next("alice")
        self.assertIsNone(result.selected)
        self.assertIsNone(result.no_selection_reason)
        self.assertEqual(result.incomplete_reason, resolver.INCOMPLETE_CANDIDATE_SCOPE)

    def test_a_locally_failed_closed_leaf_still_leaves_next_derivable(self):
        # An unresolved dependency makes that leaf canonically non-READY, which
        # is a complete answer, so a fully known sibling stays selectable.
        snapshot = build_snapshot(
            [
                epic(1, (key(2), key(3))),
                leaf(2, parent=key(1), blocked_by=(key(404),)),
                leaf(3, parent=key(1)),
            ]
        )
        resolution = resolver.resolve(snapshot, key(1))
        self.assertFalse(resolution.complete)
        result = resolution.select_next("alice")
        self.assertEqual(result.selected, key(3))
        self.assertIsNone(result.incomplete_reason)

    def test_a_second_parent_is_reported_without_inventing_a_state_rule(self):
        snapshot = build_snapshot(
            [
                epic(1, (key(2), key(3))),
                epic(2, (key(9),), parent=key(1)),
                epic(3, (key(9),), parent=key(1)),
                leaf(9, parent=key(2)),
            ]
        )
        resolution = resolver.resolve(snapshot, key(1))
        self.assertIn(
            model.Finding(resolver.FINDING_MULTIPLE_PARENTS, key(9), f"{key(2)}, {key(3)}"),
            resolution.findings,
        )


class DependencyTests(TestCase):
    """Sections 3.2 and 3.5 dependency semantics."""

    def test_satisfaction_follows_the_closure_reason_rule(self):
        cases = {
            "open": ({}, False),
            "completed": (closed(), True),
            "not_planned": (closed("not_planned"), False),
            "duplicate": (closed("duplicate"), False),
        }
        for label, (target_state, satisfied) in cases.items():
            with self.subTest(target=label):
                snapshot = build_snapshot(
                    [
                        leaf(1, blocked_by=(key(2),)),
                        leaf(2, **target_state),
                    ]
                )
                state = resolver.resolve(snapshot, key(1)).states[key(1)]
                self.assertEqual(state.ready, satisfied)
                self.assertEqual(state.blocked, not satisfied)
                if not satisfied:
                    self.assertIn(resolver.REASON_UNSATISFIED_DEPENDENCY, state.reasons)

    def test_cross_repository_dependency_is_honoured(self):
        snapshot = build_snapshot(
            [
                leaf(1, blocked_by=(key(7, OTHER_REPO),)),
                leaf(7, repository=OTHER_REPO),
            ]
        )
        state = resolver.resolve(snapshot, key(1)).states[key(1)]
        self.assertTrue(state.blocked)
        self.assertIn(resolver.REASON_UNSATISFIED_DEPENDENCY, state.reasons)

    def test_missing_dependency_target_blocks_and_is_reported(self):
        snapshot = build_snapshot([leaf(1, blocked_by=(key(404),))])
        resolution = resolver.resolve(snapshot, key(1))
        state = resolution.states[key(1)]
        self.assertFalse(state.ready)
        self.assertTrue(state.blocked)
        self.assertIn(resolver.REASON_UNRESOLVED_DEPENDENCY, state.reasons)
        self.assertIn(
            resolver.FINDING_UNRESOLVED_DEPENDENCY,
            {finding.code for finding in resolution.findings},
        )
        self.assertFalse(resolution.complete)

    def test_dependency_cycle_blocks_members_and_their_dependents(self):
        snapshot = build_snapshot(
            [
                epic(1, (key(2), key(3), key(4))),
                leaf(2, parent=key(1), blocked_by=(key(3),)),
                leaf(3, parent=key(1), blocked_by=(key(2),)),
                leaf(4, parent=key(1), blocked_by=(key(2),)),
            ]
        )
        resolution = resolver.resolve(snapshot, key(1))
        for number in (2, 3, 4):
            with self.subTest(node=number):
                state = resolution.states[key(number)]
                self.assertFalse(state.ready)
                self.assertIn(resolver.REASON_DEPENDENCY_CYCLE, state.reasons)
        self.assertTrue(resolution.states[key(2)].blocked)
        self.assertIn(
            resolver.FINDING_DEPENDENCY_CYCLE,
            {finding.code for finding in resolution.findings},
        )

    def test_depending_on_a_cycle_fails_closed_without_participating_in_it(self):
        # Section 4.1 makes only a participant `BLOCKED`; section 3.5 still keeps
        # every node that depends on a cycle out of `READY`.
        snapshot = build_snapshot(
            [
                leaf(1, blocked_by=(key(2),)),
                leaf(2, blocked_by=(key(3),), **closed()),
                leaf(3, blocked_by=(key(2),), **closed()),
            ]
        )
        state = resolver.resolve(snapshot, key(1)).states[key(1)]
        self.assertFalse(state.ready)
        self.assertFalse(state.blocked)
        self.assertEqual(state.reasons, (resolver.REASON_DEPENDENCY_CYCLE,))

    def test_dependencies_are_never_inherited_through_containment(self):
        snapshot = build_snapshot(
            [
                epic(1, (key(2),), blocked_by=(key(3),)),
                leaf(2, parent=key(1)),
                leaf(3),
            ]
        )
        resolution = resolver.resolve(snapshot, key(1))
        self.assertTrue(resolution.states[key(1)].blocked)
        self.assertTrue(resolution.states[key(2)].ready)


class NativeLimitTests(TestCase):
    """Sections 2.2 and 3.2 native limits are validation constraints."""

    def test_limits_are_reported_as_structural_findings(self):
        children = tuple(key(number) for number in range(100, 100 + model.MAX_SUB_ISSUES_PER_PARENT + 1))
        dependencies = tuple(key(number) for number in range(500, 500 + model.MAX_DEPENDENCIES_PER_TYPE + 1))
        nodes = [epic(1, children, blocked_by=dependencies, blocking_count=model.MAX_DEPENDENCIES_PER_TYPE + 1)]
        nodes.extend(leaf(number, parent=key(1)) for number in range(100, 100 + model.MAX_SUB_ISSUES_PER_PARENT + 1))
        nodes.extend(leaf(number, **closed()) for number in range(500, 500 + model.MAX_DEPENDENCIES_PER_TYPE + 1))
        resolution = resolver.resolve(build_snapshot(nodes), key(1))
        codes = {finding.code for finding in resolution.findings}
        self.assertIn(resolver.FINDING_SUB_ISSUE_LIMIT, codes)
        self.assertIn(resolver.FINDING_DEPENDENCY_LIMIT, codes)
        self.assertIn(resolver.FINDING_DEPENDENCY_LIMIT_BLOCKING, codes)

    def test_nesting_beyond_the_native_depth_is_reported(self):
        depth = model.MAX_NESTING_DEPTH + 1
        nodes = [epic(0, (key(1),))]
        nodes.extend(epic(number, (key(number + 1),), parent=key(number - 1)) for number in range(1, depth))
        nodes.append(leaf(depth, parent=key(depth - 1)))
        resolution = resolver.resolve(build_snapshot(nodes), key(0))
        self.assertIn(
            model.Finding(resolver.FINDING_NESTING_DEPTH, key(depth), str(depth)),
            resolution.findings,
        )
        self.assertTrue(resolution.states[key(depth)].ready)


class MirrorTests(TestCase):
    """Section 1: a Markdown mirror never becomes graph state."""

    def test_body_relationships_are_reported_but_change_nothing(self):
        snapshot = build_snapshot([leaf(1, mirror_relationships=("blocked by", "parent"))])
        resolution = resolver.resolve(snapshot, key(1))
        self.assertTrue(resolution.states[key(1)].ready)
        self.assertIn(
            model.Finding(resolver.FINDING_MIRROR_RELATIONSHIP, key(1), "blocked by, parent"),
            resolution.findings,
        )

    def test_mirror_detection_recognizes_bootstrap_lines_only(self):
        body = "Parent: #1\n- Blocked by: #2\n**Order:** 3\nParenthetical: no\n"
        self.assertEqual(model.mirror_relationships(body), ("blocked by", "order", "parent"))
        self.assertEqual(model.mirror_relationships("no relationships here"), ())


class DoneTests(TestCase):
    """Section 4.1 `DONE` is native state, not proof of correct delivery."""

    def test_done_reports_native_closure_without_judging_it(self):
        snapshot = build_snapshot(
            [
                epic(1, (key(2), key(3))),
                leaf(2, parent=key(1), has_acceptance_criteria=False, **closed()),
                leaf(3, parent=key(1), **closed("not_planned")),
            ]
        )
        resolution = resolver.resolve(snapshot, key(1))
        self.assertTrue(resolution.states[key(2)].done)
        self.assertFalse(resolution.states[key(3)].done)
        for number in (2, 3):
            self.assertFalse(resolution.states[key(number)].blocked)


class ClaimTests(TestCase):
    """Section 4.2 execution claims."""

    def test_claim_on_a_ready_leaf_makes_it_active(self):
        snapshot = build_snapshot([leaf(1, claims=(Claim("alice", f"{REPO}#10"),))])
        self.assertTrue(resolver.resolve(snapshot, key(1)).states[key(1)].active)

    def test_claim_on_a_non_ready_leaf_does_not_make_it_active(self):
        snapshot = build_snapshot(
            [leaf(1, has_acceptance_criteria=False, claims=(Claim("alice", f"{REPO}#10"),))]
        )
        state = resolver.resolve(snapshot, key(1)).states[key(1)]
        self.assertFalse(state.active)
        self.assertFalse(state.ready)

    def test_unobservable_claims_leave_the_leaf_available_and_are_reported(self):
        snapshot = build_snapshot([leaf(1, claims_observable=False)])
        resolution = resolver.resolve(snapshot, key(1))
        self.assertTrue(resolution.states[key(1)].ready)
        self.assertFalse(resolution.states[key(1)].active)
        self.assertIn(
            model.Finding(resolver.FINDING_CLAIMS_UNOBSERVABLE, key(1)),
            resolution.findings,
        )
        self.assertEqual(
            resolution.select_next("alice").selected,
            key(1),
        )


class NextSelectionTests(TestCase):
    """Section 4.3 deterministic `NEXT`."""

    def parallel_epic(self, *leaves: Node) -> resolver.Resolution:
        children = tuple(node.key for node in leaves)
        snapshot = build_snapshot([epic(1, children), *leaves])
        return resolver.resolve(snapshot, key(1))

    def test_parallelism_is_preserved_and_sibling_order_only_biases_selection(self):
        resolution = self.parallel_epic(leaf(5, parent=key(1)), leaf(4, parent=key(1)))
        self.assertEqual(resolution.ready_leaves(), (key(5), key(4)))
        self.assertEqual(resolution.select_next("alice").selected, key(5))

    def test_priority_rank_outranks_sibling_order(self):
        resolution = self.parallel_epic(
            leaf(5, parent=key(1)),
            leaf(4, parent=key(1), priority_labels=("priority: high",)),
        )
        self.assertEqual(resolution.select_next("alice").selected, key(4))

    def test_highest_recognized_label_wins_and_unknown_labels_rank_lowest(self):
        resolution = self.parallel_epic(
            leaf(5, parent=key(1), priority_labels=("priority: urgent",)),
            leaf(4, parent=key(1), priority_labels=("priority: medium", "priority: blocker")),
        )
        self.assertEqual(resolution.select_next("alice").selected, key(4))
        self.assertEqual(resolution.states[key(5)].priority_rank, model.UNRECOGNIZED_PRIORITY_RANK)

    def test_ties_break_by_repository_then_issue_number(self):
        # Distinct leaves under one root always differ in path order, so the last
        # two keys of section 4.3 are proven on the ordering function itself.
        same_path = (0,)
        ordered = [
            resolver.SelectionKey(priority_rank=2, path=same_path, repository=REPO, number=8),
            resolver.SelectionKey(priority_rank=1, path=same_path, repository=REPO, number=3),
            resolver.SelectionKey(priority_rank=1, path=same_path, repository=REPO, number=8),
            resolver.SelectionKey(priority_rank=1, path=same_path, repository=OTHER_REPO, number=3),
            resolver.SelectionKey(priority_rank=1, path=(0, 0), repository=REPO, number=1),
        ]
        self.assertEqual(sorted(ordered), ordered)
        # The ordering is a total order, so every comparison operator answers
        # consistently rather than only the one `sorted` happens to call.
        first, second = ordered[0], ordered[1]
        self.assertTrue(first < second and first <= second and second > first and second >= first)
        self.assertTrue(first <= first and first >= first)
        self.assertFalse(first > second or second < first)

    def test_path_order_compares_vectors_lexicographically(self):
        snapshot = build_snapshot(
            [
                epic(1, (key(2), key(5))),
                epic(2, (key(3),), parent=key(1)),
                leaf(3, parent=key(2)),
                leaf(5, parent=key(1)),
            ]
        )
        resolution = resolver.resolve(snapshot, key(1))
        self.assertEqual(resolution.states[key(3)].path, (0, 0))
        self.assertEqual(resolution.states[key(5)].path, (1,))
        self.assertEqual(resolution.select_next("alice").selected, key(3))

    def test_foreign_claims_are_excluded_and_own_claims_are_not(self):
        resolution = self.parallel_epic(
            leaf(5, parent=key(1), claims=(Claim("bob", f"{REPO}#10"),)),
            leaf(4, parent=key(1), claims=(Claim("alice", f"{REPO}#11"),)),
        )
        result = resolution.select_next("alice")
        self.assertEqual(result.selected, key(4))
        self.assertEqual(result.candidates, (key(4),))

    def test_no_ready_leaf_and_all_candidates_claimed_are_distinct(self):
        # Both are ordinary answers over a complete input set, so neither is an
        # incompleteness result.
        blocked = self.parallel_epic(leaf(5, parent=key(1), has_acceptance_criteria=False))
        empty = blocked.select_next("alice")
        self.assertIsNone(empty.selected)
        self.assertEqual(empty.no_selection_reason, resolver.NO_READY_LEAF)
        self.assertIsNone(empty.incomplete_reason)

        claimed = self.parallel_epic(leaf(5, parent=key(1), claims=(Claim("bob", f"{REPO}#10"),)))
        result = claimed.select_next("alice")
        self.assertIsNone(result.selected)
        self.assertEqual(result.no_selection_reason, resolver.ALL_CANDIDATES_CLAIMED)
        self.assertIsNone(result.incomplete_reason)

    def test_cross_repository_containment_keeps_native_order(self):
        snapshot = build_snapshot(
            [
                epic(1, (key(7, OTHER_REPO), key(2))),
                leaf(7, repository=OTHER_REPO, parent=key(1)),
                leaf(2, parent=key(1)),
            ]
        )
        resolution = resolver.resolve(snapshot, key(1))
        self.assertEqual(resolution.ready_leaves(), (key(7, OTHER_REPO), key(2)))


class AcceptanceCriteriaTests(TestCase):
    """Section 4.1 structural acceptance-criteria detection."""

    ACCEPTED = {
        "canonical heading": "## Acceptance Criteria\n\n- one\n",
        "approved decoration": "### ✅ Acceptance Criteria\n\n- one\n",
        "trailing colon and case": "## acceptance criteria:\n\ntext\n",
        "upper case deep heading": "#### ACCEPTANCE CRITERIA\n\ntext\n",
        "emphasis inside heading": "## **Acceptance Criteria**\n\ntext\n",
        "fenced block as content": "## Acceptance Criteria\n\n```\ncode\n```\n",
        "heading after other sections": "# Goal\n\ntext\n\n## Acceptance Criteria\n\n- one\n",
    }

    REJECTED = {
        "fenced code": "```markdown\n## Acceptance Criteria\n\n- one\n```\n",
        "indented code": "    ## Acceptance Criteria\n\n    - one\n",
        "blockquote": "> ## Acceptance Criteria\n>\n> - one\n",
        "bold text": "**Acceptance Criteria**\n\n- one\n",
        "prose mention": "This issue has acceptance criteria below.\n",
        "unapproved decoration": "## \U0001f3af Acceptance Criteria\n\n- one\n",
        "parenthetical suffix": "## Acceptance Criteria (draft)\n\n- one\n",
        "different words": "## Criteria\n\n- one\n",
        "empty section": "## Acceptance Criteria\n\n## Non-Goals\n\n- one\n",
        "empty body": "",
        "setext heading": "Acceptance Criteria\n===\n\n- one\n",
    }

    def test_structural_detection_matches_the_canonical_procedure(self):
        labels = list(self.ACCEPTED) + list(self.REJECTED)
        bodies = list(self.ACCEPTED.values()) + list(self.REJECTED.values())
        expected = [True] * len(self.ACCEPTED) + [False] * len(self.REJECTED)
        # One batch call also proves detection stays aligned with its input order.
        self.assertEqual(dict(zip(labels, acceptance_criteria.detect(bodies))), dict(zip(labels, expected)))

    def test_detection_failure_is_raised_rather_than_defaulted(self):
        with self.assertRaises(acceptance_criteria.MarkdownParserUnavailable):
            acceptance_criteria.detect(["text"], node_executable="definitely-not-node")


if __name__ == "__main__":
    main()
