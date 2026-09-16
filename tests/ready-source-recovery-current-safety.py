# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
"""Closed source-safety assertions for an immutable historical Ready source."""

from __future__ import annotations

import ast
import copy
import hashlib
import inspect
import io
import json
import os
from pathlib import Path
import re
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_ROOT = Path(
    os.environ["SECPAL_CURRENT_SAFETY_CANDIDATE_ROOT"]
).resolve(strict=True)
CANDIDATE_REPOSITORY = os.environ[
    "SECPAL_CURRENT_SAFETY_CANDIDATE_REPOSITORY"
]
if (
    Path(os.environ["SECPAL_CURRENT_SAFETY_TOOLING_ROOT"]).resolve(strict=True)
    != ROOT
    or ROOT == CANDIDATE_ROOT
    or ROOT in CANDIDATE_ROOT.parents
    or CANDIDATE_ROOT in ROOT.parents
    or re.fullmatch(
        r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", CANDIDATE_REPOSITORY
    )
    is None
):
    raise RuntimeError("current-safety provenance roots are invalid")
from secpal_pr_review import fast_path, lifecycle_authority as authority

REPOSITORY = "example/project"
HEAD = "a" * 40
TREE = "b" * 40
SIGNER = "fixture@example.invalid"


class ReadySourceRecoveryCurrentSafety(unittest.TestCase):
    """Assertions owned by candidate source rather than the current issuer."""

    def setUp(self):
        actor = {"login": "reviewer", "node_id": "actor", "database_id": 7}

        def comment(identity):
            return {
                "node_id": identity,
                "body_digest": hashlib.sha256(identity.encode()).hexdigest(),
                "actor": actor,
                "reply_to_id": None,
                "reactions": [],
            }

        review = {**comment("review"), "state": "COMMENTED", "commit_oid": HEAD}
        self.reviewed = fast_path.StableFeedbackState(
            repository=REPOSITORY,
            pull_request_number=17,
            head_sha=HEAD,
            base_ref="main",
            base_sha="c" * 40,
            pr_state="OPEN",
            feedback={
                "pull_request_reactions": [],
                "reviews": [review],
                "conversation_comments": [
                    {**comment("conversation"), "updated_at": None}
                ],
                "threads": [
                    {
                        "node_id": "resolved-thread",
                        "is_resolved": True,
                        "is_outdated": False,
                        "comments": [comment("resolved-comment")],
                    },
                    {
                        "node_id": "open-thread",
                        "is_resolved": False,
                        "is_outdated": False,
                        "comments": [comment("open-comment")],
                    },
                ],
            },
        )

    def prior_authority(self):
        return {
            "schema_version": "1.1",
            "kind": "READY_INTEGRATION_PRIOR_AUTHORITY",
            "repository": REPOSITORY,
            "delivery_issue_number": 16,
            "pull_request_number": 17,
            "prior_delivery_head_sha": HEAD,
            "prior_delivery_tree_sha": TREE,
            "prior_validation_receipt_digest": "d" * 64,
            "prior_final_attestation_digest": "e" * 64,
            "expected_signer": {"kind": "SSH_PRINCIPAL", "identity": SIGNER},
            "lifecycle": {
                "identity": "fixture-lifecycle",
                "current_authority_digest": "f" * 64,
                "historical_proof_mode": authority.NATIVE_PROOF_MODE,
                "draft": False,
                "ready": True,
                "ready_transition": False,
                "unrestricted_reviews": 1,
                "remediation_cycles": 2,
                "exceptional_recoveries": 0,
                "exceptional_continuations": 0,
                "cycle_3": False,
            },
            "publication": {
                "object_oid": "1" * 40,
                "publication_digest": "2" * 64,
            },
        }

    def validate_state(self, state):
        parameters = inspect.signature(authority._validate_state).parameters
        if "allow_adopted_observations" in parameters:
            return authority._validate_state(
                state, allow_adopted_observations=False,
            )
        return authority._validate_state(state)

    def test_ordinary_prior_ready(self):
        prior = self.prior_authority()
        self.assertEqual(
            fast_path.normalize_ready_integration_prior_authority(prior), prior,
        )

    def test_prior_authority_scope(self):
        for path, value in (
            (("delivery_issue_number",), 0),
            (("prior_delivery_head_sha",), "invalid"),
            (("prior_delivery_tree_sha",), "invalid"),
            (("publication", "object_oid"), "invalid"),
            (("lifecycle", "draft"), True),
            (("lifecycle", "ready"), False),
            (("lifecycle", "unrestricted_reviews"), 0),
        ):
            changed = copy.deepcopy(self.prior_authority())
            target = changed
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            with self.subTest(path=path), self.assertRaises(
                fast_path.SecurityBlocker
            ):
                fast_path.normalize_ready_integration_prior_authority(changed)
        changed = self.prior_authority()
        changed["caller_selected_safety"] = True
        with self.assertRaises(fast_path.SecurityBlocker):
            fast_path.normalize_ready_integration_prior_authority(changed)

    def test_prior_authority_signer(self):
        for signer in (
            {"kind": "CALLER", "identity": SIGNER},
            {"kind": "OPENPGP_FINGERPRINT", "identity": "invalid"},
            {"kind": "SSH_PRINCIPAL", "identity": ""},
        ):
            changed = self.prior_authority()
            changed["expected_signer"] = signer
            with self.subTest(signer=signer), self.assertRaises(
                fast_path.SecurityBlocker
            ):
                fast_path.normalize_ready_integration_prior_authority(changed)

    def test_lifecycle_history(self):
        state = authority.initial_state()
        event = {
            "sequence": 1,
            "transition_kind": "DRAFT_TO_READY",
            "event_authorization_digest": "3" * 64,
        }
        state.update(
            unrestricted_review_count=1,
            remediation_cycle_count=2,
            draft=False,
            ready=True,
            ready_transition_count=1,
            ready_history=[event],
        )
        self.assertEqual(self.validate_state(state), state)
        for key, value in (
            ("cycle_3_absent", False),
            ("unrestricted_review_count", 2),
            ("remediation_cycle_count", 3),
            ("ready_transition_count", 0),
            ("exceptional_recovery_count", 2),
            ("exceptional_continuation_count", 2),
        ):
            with self.subTest(key=key), self.assertRaises(
                authority.LifecycleAuthorityError
            ):
                self.validate_state({**state, key: value})

    def test_stable_feedback_integrity(self):
        restored = fast_path.StableFeedbackState.from_payload(
            self.reviewed.to_dict()
        )
        self.assertEqual(restored.state_digest, self.reviewed.state_digest)
        self.assertTrue(any(
            thread["is_resolved"] for thread in restored.feedback["threads"]
        ))
        duplicate = self.reviewed.to_dict()
        duplicate["reviews"].append(copy.deepcopy(duplicate["reviews"][0]))
        with self.assertRaises(fast_path.SecurityBlocker):
            fast_path.StableFeedbackState.from_payload(duplicate)
        for field, value in (("head_sha", "invalid"), ("base_sha", "invalid")):
            changed = self.reviewed.to_dict()
            changed[field] = value
            with self.subTest(field=field), self.assertRaises(
                fast_path.SecurityBlocker
            ):
                fast_path.StableFeedbackState.from_payload(changed)

    def test_candidate_issuer_separation(self):
        tooling_scripts = (ROOT / "scripts").resolve(strict=True)
        for module in (fast_path, authority):
            source = Path(module.__file__).resolve(strict=True)
            self.assertIn(tooling_scripts, source.parents)
            self.assertNotIn(CANDIDATE_ROOT, source.parents)
        self.assertNotIn(str(CANDIDATE_ROOT), sys.path)
        for module in tuple(sys.modules.values()):
            source = getattr(module, "__file__", None)
            if not isinstance(source, str):
                continue
            try:
                resolved = Path(source).resolve(strict=True)
            except OSError:
                continue
            self.assertNotIn(CANDIDATE_ROOT, resolved.parents)

        forbidden = {
            "registry", "command_set", "safety_facts", "current_lifecycle",
            "_validation_runner", "_issuer_source_verifier",
        }

        class ModuleBindingVisitor(ast.NodeVisitor):
            """Collect conservative bindings made while a module is loaded."""

            def __init__(self):
                self.bindings = []

            def bind(self, name, node):
                if name == "issue_ready_source_recovery_authorization":
                    self.bindings.append(node)

            def visit_Name(self, node):
                if isinstance(node.ctx, (ast.Store, ast.Del)):
                    self.bind(node.id, node)

            def visit_FunctionDef(self, node):
                self.bind(node.name, node)
                for expression in [
                    *node.decorator_list,
                    *node.args.defaults,
                    *(
                        default for default in node.args.kw_defaults
                        if default is not None
                    ),
                    *(argument.annotation for argument in [
                        *node.args.posonlyargs,
                        *node.args.args,
                        *node.args.kwonlyargs,
                    ] if argument.annotation is not None),
                ]:
                    self.visit(expression)
                if node.args.vararg and node.args.vararg.annotation:
                    self.visit(node.args.vararg.annotation)
                if node.args.kwarg and node.args.kwarg.annotation:
                    self.visit(node.args.kwarg.annotation)
                if node.returns:
                    self.visit(node.returns)

            visit_AsyncFunctionDef = visit_FunctionDef

            def visit_ClassDef(self, node):
                self.bind(node.name, node)
                for expression in [
                    *node.decorator_list, *node.bases,
                    *(keyword.value for keyword in node.keywords),
                ]:
                    self.visit(expression)

            def visit_Lambda(self, _node):
                return

            def visit_Import(self, node):
                for alias in node.names:
                    self.bind(alias.asname or alias.name.split(".", 1)[0], node)

            def visit_ImportFrom(self, node):
                for alias in node.names:
                    self.bind(
                        "issue_ready_source_recovery_authorization"
                        if alias.name == "*"
                        else alias.asname or alias.name,
                        node,
                    )

            def visit_ExceptHandler(self, node):
                if node.name:
                    self.bind(node.name, node)
                if node.type:
                    self.visit(node.type)
                for statement in node.body:
                    self.visit(statement)

            def visit_MatchAs(self, node):
                if node.pattern:
                    self.visit(node.pattern)
                if node.name:
                    self.bind(node.name, node)

            def visit_MatchStar(self, node):
                if node.name:
                    self.bind(node.name, node)

            def visit_MatchMapping(self, node):
                for key in node.keys:
                    self.visit(key)
                for pattern in node.patterns:
                    self.visit(pattern)
                if node.rest:
                    self.bind(node.rest, node)

        def issuer_parameters(path):
            tree = ast.parse(path.read_bytes(), filename=str(path))
            visitor = ModuleBindingVisitor()
            visitor.visit(tree)
            self.assertEqual(len(visitor.bindings), 1)
            definition = visitor.bindings[0]
            self.assertIsInstance(
                definition, (ast.FunctionDef, ast.AsyncFunctionDef),
            )
            self.assertFalse(definition.decorator_list)
            arguments = definition.args
            parameters = [
                *arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs,
            ]
            if arguments.vararg is not None:
                parameters.append(arguments.vararg)
            if arguments.kwarg is not None:
                parameters.append(arguments.kwarg)
            return {item.arg for item in parameters}

        accepted_actions = ROOT / "scripts/secpal-pr-review-actions.py"
        self.assertTrue(accepted_actions.is_file())
        self.assertFalse(forbidden.intersection(issuer_parameters(accepted_actions)))

        candidate_actions = CANDIDATE_ROOT / "scripts/secpal-pr-review-actions.py"
        if CANDIDATE_REPOSITORY == "SecPal/.github":
            self.assertTrue(candidate_actions.is_file())
            self.assertFalse(
                forbidden.intersection(issuer_parameters(candidate_actions))
            )
        else:
            self.assertFalse(candidate_actions.exists())


def main(arguments):
    if arguments:
        raise RuntimeError("Ready-source current safety accepts no caller selection")
    names = unittest.defaultTestLoader.getTestCaseNames(
        ReadySourceRecoveryCurrentSafety
    )
    suite = unittest.TestSuite(
        ReadySourceRecoveryCurrentSafety(name) for name in names
    )
    output = io.StringIO()
    result = unittest.TextTestRunner(stream=output).run(suite)
    if not result.wasSuccessful() or result.skipped or result.testsRun != len(names):
        sys.stderr.write(output.getvalue())
        failed = sorted({
            getattr(test, "test_case", test)._testMethodName.removeprefix("test_")
            for test, _ in [
                *result.failures, *result.errors, *result.skipped,
            ]
        })
        print(json.dumps(failed))
        return 1
    print(json.dumps([name.removeprefix("test_") for name in names]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
