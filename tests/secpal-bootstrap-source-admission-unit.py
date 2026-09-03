# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Contract tests for the exact #810 bootstrap implementation source."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
import inspect
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.secpal_pr_review import bootstrap_source_admission as source
from scripts.secpal_pr_review import fast_path


REPOSITORY = "SecPal/.github"
ISSUE = 810
PR = 812
HEAD = "a668f6642ffcc76bcbea7fa6b69c5d6198ef5868"
TREE = "13987395e5bdbeb586effb08e6a6f0ed5082a383"
PARENT = "6487001f57f6223f6502bacf953d9ad90d37a880"
RECEIPT = "83ef66b94d46d862b728a55ebb3affd4d8231ea70f8bf09c0c0aabcbdc7a63cc"
ATTESTATION = "a6ed34cbf05647e1c7cce4a9435e3f0f17e5d918f9e344763f6d8fbc9ac4e102"
STALE_RECEIPT = "a09090603206134470b21f58224d6fd35c4a26f4cc87ca7936c068421d0e867f"
STALE_ATTESTATION = "e585aab46ea8e30a28fd953d98711460d0e45818637cf68ab36e25e550b9e5e6"
BLOB = "4cfd9eb73a522224f9dfca4176d1aad386b81d50"


class BootstrapSourceAdmissionContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.trust, self.policy = source._select_policy(REPOSITORY, ISSUE)
        self.reviewed = fast_path.StableFeedbackState(
            repository=REPOSITORY,
            pull_request_number=PR,
            head_sha=PARENT,
            base_ref="main",
            base_sha="1" * 40,
            pr_state="OPEN",
            feedback={
                "pull_request_reactions": [],
                "reviews": [],
                "conversation_comments": [],
                "threads": [],
            },
        )
        self.receipt = {"receipt_digest": RECEIPT}
        self.attestation = {
            "attestation_digest": ATTESTATION,
            "manual_gate_evidence": [],
            "validation_receipt_digest": RECEIPT,
        }

    def _verified_validation(self, policy=None):
        policy = policy or self.policy
        return fast_path.VerifiedValidationEvidence(
            repository=policy.repository,
            pull_request_number=policy.pull_request,
            head_sha=policy.source_head_sha,
            tree_sha=policy.source_tree_sha,
            validation_receipt_digest=policy.validation_receipt_digest,
            final_attestation_digest=policy.final_attestation_digest,
            source_validation_evidence_digest="2" * 64,
            _verification_seal=fast_path._VERIFIED_VALIDATION_EVIDENCE,
        )

    def _authenticate(
        self,
        *,
        policy=None,
        observed_head=HEAD,
        observed_tree=TREE,
        observed_parent=PARENT,
        receipt=None,
        attestation=None,
        verifier_error=None,
    ):
        policy = policy or self.policy
        receipt = self.receipt if receipt is None else receipt
        attestation = self.attestation if attestation is None else attestation

        def git_text(_root, arguments):
            if arguments == ["rev-parse", "HEAD"]:
                return observed_head + "\n"
            if arguments == ["rev-parse", f"{observed_head}^{{tree}}"]:
                return observed_tree + "\n"
            if arguments[:3] == ["rev-list", "--parents", "-n"]:
                return f"{observed_head} {observed_parent}\n"
            raise AssertionError(arguments)

        verify = (
            mock.Mock(side_effect=verifier_error)
            if verifier_error is not None
            else mock.Mock(return_value=self._verified_validation(policy))
        )
        actions = SimpleNamespace(
            _prior_delivery_registry_binding=mock.Mock(
                return_value={"validation": [], "manual_gates": []}
            )
        )
        with (
            mock.patch.object(source, "_git_text", side_effect=git_text),
            mock.patch.object(source, "_verify_commit_signature"),
            mock.patch.object(source, "_exact_trailer", return_value=policy.validation_receipt_digest),
            mock.patch.object(source, "_load_actions_helper", return_value=actions),
            mock.patch.object(
                fast_path, "verify_reviewed_state_evidence", return_value=self.reviewed
            ),
            mock.patch.object(
                fast_path, "create_validation_receipt", return_value=receipt
            ),
            mock.patch.object(fast_path, "verify_validation_attestation", verify),
            mock.patch.object(source, "_implementation_blob", return_value=BLOB),
        ):
            return source._authenticate_materialized_source(
                Path("/fixture"),
                self.trust,
                policy,
                ({}, receipt, attestation),
            )

    def test_exact_admitted_source_metadata_verifies(self) -> None:
        verified = self._authenticate()
        self.assertTrue(source.is_verified_bootstrap_source(verified))
        self.assertEqual(
            (
                verified.repository,
                verified.delivery_issue,
                verified.pull_request,
                verified.head_sha,
                verified.tree_sha,
                verified.parent_sha,
                verified.validation_receipt_digest,
                verified.final_attestation_digest,
                verified.signer_identity,
                verified.implementation_path,
                verified.entrypoint,
                verified.purpose,
            ),
            (
                REPOSITORY,
                ISSUE,
                PR,
                HEAD,
                TREE,
                PARENT,
                RECEIPT,
                ATTESTATION,
                "aroviqen@secpal.app",
                source.IMPLEMENTATION_PATH,
                source.ENTRYPOINT,
                source.PURPOSE,
            ),
        )

    def test_wrong_repository_issue_and_cross_delivery_replay_fail(self) -> None:
        for repository, issue in (
            ("Other/.github", ISSUE),
            (REPOSITORY, 811),
            ("Other/.github", 811),
        ):
            with self.subTest(repository=repository, issue=issue):
                with self.assertRaises(source.BootstrapSourceAdmissionError):
                    source._select_policy(repository, issue)

    def test_wrong_pr_is_rejected_by_verified_evidence_binding(self) -> None:
        wrong = replace(self.policy, pull_request=811)
        with self.assertRaisesRegex(
            source.BootstrapSourceAdmissionError, "does not match maintained"
        ):
            self._authenticate(policy=wrong)

    def test_wrong_head_tree_parent_and_same_path_different_tree_fail(self) -> None:
        cases = (
            {"observed_head": "3" * 40},
            {"observed_tree": "4" * 40},
            {"observed_parent": "5" * 40},
            {"observed_tree": "6" * 40},
        )
        for arguments in cases:
            with self.subTest(arguments=arguments):
                with self.assertRaisesRegex(
                    source.BootstrapSourceAdmissionError, "head, tree, or parent"
                ):
                    self._authenticate(**arguments)

    def test_wrong_and_predecessor_receipts_fail(self) -> None:
        for digest in ("7" * 64, STALE_RECEIPT):
            with self.subTest(digest=digest):
                with self.assertRaisesRegex(
                    source.BootstrapSourceAdmissionError,
                    "does not match maintained",
                ):
                    self._authenticate(receipt={"receipt_digest": digest})

    def test_wrong_and_predecessor_attestations_fail(self) -> None:
        for digest in ("8" * 64, STALE_ATTESTATION):
            with self.subTest(digest=digest):
                attestation = {**self.attestation, "attestation_digest": digest}
                with self.assertRaisesRegex(
                    source.BootstrapSourceAdmissionError,
                    "does not match maintained",
                ):
                    self._authenticate(attestation=attestation)

    def test_malformed_receipt_or_attestation_fails(self) -> None:
        for error in (
            fast_path.SecurityBlocker("malformed receipt"),
            fast_path.SecurityBlocker("malformed attestation"),
        ):
            with self.subTest(error=str(error)):
                with self.assertRaisesRegex(
                    source.BootstrapSourceAdmissionError,
                    "receipt or final attestation is invalid",
                ):
                    self._authenticate(verifier_error=error)

    def test_unsigned_and_wrong_signer_fail(self) -> None:
        for returncode, output in (
            (1, b"error: commit is unsigned\n"),
            (0, b'Good "git" signature for attacker@example.test with ED25519 key X\n'),
        ):
            with self.subTest(returncode=returncode):
                completed = subprocess.CompletedProcess([], returncode, b"", output)
                with (
                    mock.patch.object(source, "_allowed_signers", return_value=Path("/allowed")),
                    mock.patch.object(source.publication, "_run_git", return_value=completed),
                    self.assertRaisesRegex(
                        source.BootstrapSourceAdmissionError,
                        "signature or maintained signer",
                    ),
                ):
                    source._verify_commit_signature(
                        Path("/fixture"), self.trust, self.policy
                    )

    def test_caller_cannot_select_signer_path_module_entrypoint_or_purpose(self) -> None:
        parameters = inspect.signature(
            source.execute_first_ready_executor_bootstrap
        ).parameters
        for forbidden in (
            "signer",
            "path",
            "module",
            "entrypoint",
            "purpose",
            "pull_request",
            "ref",
            "command",
            "shell",
            "environment",
            "executable",
            "python",
        ):
            self.assertNotIn(forbidden, parameters)

    def test_mutable_ref_substitution_fails(self) -> None:
        completed = subprocess.CompletedProcess([], 0, b"", b"")
        with (
            mock.patch.object(source, "_git", return_value=completed),
            mock.patch.object(source, "_git_text", return_value="9" * 40 + "\n"),
            mock.patch.object(source, "_verify_materialized_tree"),
            self.assertRaisesRegex(
                source.BootstrapSourceAdmissionError, "mutable source ref"
            ),
        ):
            with source._isolated_source_repository(self.trust, self.policy):
                self.fail("mutable source unexpectedly materialized")

    def test_materialized_tree_drift_fails_before_execution(self) -> None:
        with (
            mock.patch.object(
                source,
                "_git_text",
                side_effect=(HEAD + "\n", TREE + "\n", "1 .M N... changed.py\n"),
            ),
            self.assertRaisesRegex(
                source.BootstrapSourceAdmissionError, "materialized source differs"
            ),
        ):
            source._verify_materialized_tree(Path("/fixture"), self.policy)

    def test_duplicate_or_malformed_evidence_json_fails(self) -> None:
        for raw in (
            b'{"schema_version":"1.0","schema_version":"1.0"}\n',
            b'{"schema_version":NaN}\n',
            b"[]\n",
        ):
            with self.subTest(raw=raw), self.assertRaises(
                source.BootstrapSourceAdmissionError
            ):
                source._closed_json(raw, "fixture evidence")

    def test_isolated_materialization_fetches_only_exact_head_and_cleans_up(self) -> None:
        completed = subprocess.CompletedProcess([], 0, b"", b"")
        calls = []

        def record(_root, arguments, **_kwargs):
            calls.append(arguments)
            return completed

        retained = None
        with (
            mock.patch.object(source, "_git", side_effect=record),
            mock.patch.object(source, "_git_text", return_value=HEAD + "\n"),
            mock.patch.object(source, "_verify_materialized_tree"),
        ):
            with source._isolated_source_repository(self.trust, self.policy) as root:
                retained = root
                self.assertTrue(root.is_dir())
        self.assertIsNotNone(retained)
        self.assertFalse(retained.exists())
        fetches = [call for call in calls if call and call[0] == "fetch"]
        self.assertEqual(len(fetches), 1)
        self.assertEqual(fetches[0][-1], HEAD)
        self.assertNotIn("main", fetches[0])

    def test_exact_regular_file_and_entrypoint_are_required(self) -> None:
        record = f"100644 blob {BLOB}\t{source.IMPLEMENTATION_PATH}\x00"
        blob = b"def execute_lifecycle_transition(repository, issue, authorization):\n    return None\n"
        absent = subprocess.CompletedProcess([], 1, b"", b"")
        with (
            mock.patch.object(source, "_git_text", return_value=record),
            mock.patch.object(
                source,
                "_git",
                return_value=subprocess.CompletedProcess([], 0, blob, b""),
            ),
            mock.patch.object(source.publication, "_run_git", return_value=absent),
        ):
            self.assertEqual(
                source._implementation_blob(Path("/fixture"), self.policy), BLOB
            )

        for malformed in (
            b"def another_entrypoint():\n    pass\n",
            b"execute_lifecycle_transition = object()\n",
        ):
            with (
                mock.patch.object(source, "_git_text", return_value=record),
                mock.patch.object(
                    source,
                    "_git",
                    return_value=subprocess.CompletedProcess([], 0, malformed, b""),
                ),
                mock.patch.object(source.publication, "_run_git", return_value=absent),
                self.assertRaisesRegex(
                    source.BootstrapSourceAdmissionError, "entrypoint"
                ),
            ):
                source._implementation_blob(Path("/fixture"), self.policy)

    def test_candidate_local_verifier_cannot_self_admit(self) -> None:
        record = f"100644 blob {BLOB}\t{source.IMPLEMENTATION_PATH}\x00"
        blob = b"def execute_lifecycle_transition(repository, issue, authorization):\n    return None\n"
        present = subprocess.CompletedProcess([], 0, b"", b"")
        with (
            mock.patch.object(source, "_git_text", return_value=record),
            mock.patch.object(
                source,
                "_git",
                return_value=subprocess.CompletedProcess([], 0, blob, b""),
            ),
            mock.patch.object(source.publication, "_run_git", return_value=present),
            self.assertRaisesRegex(
                source.BootstrapSourceAdmissionError, "cannot self-admit"
            ),
        ):
            source._implementation_blob(Path("/fixture"), self.policy)

    def test_live_pr_and_commit_identity_are_closed(self) -> None:
        pull = {
            "number": PR,
            "state": "open",
            "draft": True,
            "base": {"repo": {"full_name": REPOSITORY}},
            "head": {"repo": {"full_name": REPOSITORY}, "sha": HEAD},
        }
        commit = {
            "sha": HEAD,
            "parents": [{"sha": PARENT}],
            "commit": {
                "tree": {"sha": TREE},
                "verification": {"verified": True, "reason": "valid"},
            },
        }

        def results(values):
            return [
                subprocess.CompletedProcess(
                    [], 0, json.dumps(item).encode("utf-8"), b""
                )
                for item in values
            ]

        with mock.patch.object(
            source.publication, "_run_gh", side_effect=results((pull, commit))
        ):
            source._observe_github(self.policy)
        mutations = (
            ("wrong repository", lambda p, _c: p["head"]["repo"].update(full_name="Other/repo")),
            ("wrong PR", lambda p, _c: p.update(number=811)),
            ("wrong head", lambda p, _c: p["head"].update(sha="a" * 40)),
            ("wrong tree", lambda _p, c: c["commit"]["tree"].update(sha="b" * 40)),
            ("wrong parent", lambda _p, c: c.update(parents=[{"sha": "c" * 40}])),
            ("unsigned", lambda _p, c: c["commit"]["verification"].update(verified=False)),
        )
        for label, mutate in mutations:
            changed_pull = json.loads(json.dumps(pull))
            changed_commit = json.loads(json.dumps(commit))
            mutate(changed_pull, changed_commit)
            with (
                self.subTest(label=label),
                mock.patch.object(
                    source.publication,
                    "_run_gh",
                    side_effect=results((changed_pull, changed_commit)),
                ),
                self.assertRaisesRegex(
                    source.BootstrapSourceAdmissionError, "binding changed"
                ),
            ):
                source._observe_github(self.policy)

    def test_execution_uses_fixed_isolated_import_boundary(self) -> None:
        completed = subprocess.CompletedProcess([], 0, b'{"status":"COMPLETE"}\n', b"")
        with (
            mock.patch.object(source, "_trusted_python", return_value="/usr/bin/python3"),
            mock.patch.object(
                source.authority,
                "_load_trusted_command_helper",
                return_value=SimpleNamespace(
                    command_environment=lambda _name: {
                        "PATH": "/usr/bin",
                        "PYTHONPATH": "/attacker",
                    },
                    TRUSTED_COMMAND_PATH="/usr/bin",
                ),
            ),
            mock.patch.object(subprocess, "run", return_value=completed) as runner,
        ):
            result = source._execute_entrypoint(Path("/exact/source"), b"authorization")
        self.assertEqual(result, {"status": "COMPLETE"})
        arguments = runner.call_args.args[0]
        self.assertEqual(arguments[:4], ["/usr/bin/python3", "-I", "-S", "-c"])
        self.assertEqual(arguments[-1], "/exact/source")
        self.assertNotIn("PYTHONPATH", runner.call_args.kwargs["env"])
        for key in ("HOME", "GH_CONFIG_DIR", "GH_TOKEN", "GITHUB_TOKEN"):
            self.assertNotIn(key, runner.call_args.kwargs["env"])
        self.assertNotIn("shell", runner.call_args.kwargs)
        self.assertIn("admitted sibling import escaped", source._LAUNCHER)

    def test_execution_child_environment_excludes_hostile_parent_state(self) -> None:
        completed = subprocess.CompletedProcess([], 0, b'{"status":"COMPLETE"}\n', b"")
        parent_environment = {
            "PATH": "/usr/bin:/bin",
            "HOME": "/operator-home",
            "GH_CONFIG_DIR": "/operator-gh-config",
            "GH_TOKEN": "test-token",
            "GITHUB_TOKEN": "test-github-token",
            "LD_PRELOAD": "/attacker/preload.so",
            "LD_LIBRARY_PATH": "/attacker/lib",
            "DYLD_INSERT_LIBRARIES": "/attacker/inject.dylib",
            "DYLD_LIBRARY_PATH": "/attacker/dylibs",
            "PYTHONPATH": "/attacker/python",
            "PYTHONHOME": "/attacker/home",
            "SECPAL_UNEXPECTED_PARENT_ENV": "attacker-controlled",
        }
        with (
            mock.patch.object(source, "_trusted_python", return_value="/usr/bin/python3"),
            mock.patch.object(
                source.authority,
                "_load_trusted_command_helper",
                return_value=SimpleNamespace(
                    command_environment=lambda _name: dict(parent_environment),
                    TRUSTED_COMMAND_PATH="/usr/bin:/bin",
                ),
            ),
            mock.patch.object(subprocess, "run", return_value=completed) as runner,
        ):
            source._execute_entrypoint(Path("/exact/source"), b"authorization")
        environment = runner.call_args.kwargs["env"]
        for key in (
            "LD_PRELOAD",
            "LD_LIBRARY_PATH",
            "DYLD_INSERT_LIBRARIES",
            "DYLD_LIBRARY_PATH",
            "PYTHONPATH",
            "PYTHONHOME",
            "SECPAL_UNEXPECTED_PARENT_ENV",
        ):
            self.assertNotIn(key, environment)
        self.assertEqual(environment["PATH"], "/usr/bin:/bin")
        self.assertEqual(environment["LANG"], "C.UTF-8")
        self.assertEqual(environment["LC_ALL"], "C.UTF-8")
        self.assertEqual(environment["PAGER"], "cat")
        self.assertEqual(environment["GH_PAGER"], "cat")
        self.assertEqual(environment["GH_HOST"], "github.com")
        self.assertEqual(environment["HOME"], "/operator-home")
        self.assertEqual(environment["GH_CONFIG_DIR"], "/operator-gh-config")
        self.assertEqual(environment["GH_TOKEN"], "test-token")
        self.assertEqual(environment["GITHUB_TOKEN"], "test-github-token")

    def test_source_admission_alone_has_no_mutation_or_lifecycle_authority(self) -> None:
        verified = self._authenticate()
        self.assertTrue(source.is_verified_bootstrap_source(verified))
        fields = set(verified.__dataclass_fields__)
        for forbidden in (
            "draft",
            "ready",
            "current",
            "lifecycle_id",
            "transition",
            "github_mutation",
            "publication",
            "work_graph",
            "genesis",
        ):
            self.assertNotIn(forbidden, fields)

    def test_public_verifier_never_executes_candidate(self) -> None:
        @contextmanager
        def isolated(_trust, _policy):
            yield Path("/fixture")

        verified = self._authenticate()
        with (
            mock.patch.object(source, "_read_evidence", return_value=({}, {}, {})),
            mock.patch.object(source, "_observe_github"),
            mock.patch.object(source, "_isolated_source_repository", isolated),
            mock.patch.object(
                source, "_authenticate_materialized_source", return_value=verified
            ),
            mock.patch.object(source, "_verify_materialized_tree"),
            mock.patch.object(source, "_execute_entrypoint") as execute,
        ):
            result = source.verify_first_ready_executor_source(
                REPOSITORY, ISSUE, source_evidence_directory="/evidence"
            )
        self.assertIs(result, verified)
        execute.assert_not_called()

    def test_only_verified_source_can_reach_exact_entrypoint(self) -> None:
        @contextmanager
        def isolated(_trust, _policy):
            yield Path("/fixture")

        verified = self._authenticate()
        with (
            mock.patch.object(source, "_read_evidence", return_value=({}, {}, {})),
            mock.patch.object(source, "_observe_github"),
            mock.patch.object(source, "_isolated_source_repository", isolated),
            mock.patch.object(
                source, "_authenticate_materialized_source", return_value=verified
            ),
            mock.patch.object(source, "_verify_materialized_tree"),
            mock.patch.object(
                source, "_execute_entrypoint", return_value={"status": "COMPLETE"}
            ) as execute,
        ):
            result = source.execute_first_ready_executor_bootstrap(
                REPOSITORY,
                ISSUE,
                b"separately-signed-one-use-authorization",
                source_evidence_directory="/evidence",
            )
        self.assertEqual(result, {"status": "COMPLETE"})
        execute.assert_called_once_with(
            Path("/fixture"), b"separately-signed-one-use-authorization"
        )

    def test_historical_genesis_repair_and_787_remain_separate(self) -> None:
        self.assertEqual(len(self.trust.bootstrap_genesis_repairs), 1)
        repair = self.trust.bootstrap_genesis_repairs[0]
        self.assertEqual((repair.repair_issue, repair.delivery_issue), (774, 736))
        self.assertEqual(len(self.trust.bootstrap_source_admissions), 1)
        admission = self.trust.bootstrap_source_admissions[0]
        self.assertEqual((admission.delivery_issue, admission.pull_request), (810, 812))
        self.assertNotIn(787, (admission.delivery_issue, admission.pull_request))

    def test_no_generic_branch_execution_trust_exists(self) -> None:
        self.assertEqual(
            set(inspect.signature(source.execute_first_ready_executor_bootstrap).parameters),
            {
                "repository",
                "delivery_issue",
                "serialized_authorization",
                "source_evidence_directory",
            },
        )
        self.assertNotIn("shell=True", inspect.getsource(source))


if __name__ == "__main__":
    unittest.main()
