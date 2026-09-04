# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Contract tests for the exact #810 bootstrap implementation source."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
import io
import inspect
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
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

    def _recover(self, *, policy=None, command_set_digest=None):
        policy = policy or self.policy
        recovery = policy.evidence_loss_recovery
        expected = (
            None
            if recovery is None
            else recovery.recovery_validation.command_set_digest
        )
        command_set_digest = expected if command_set_digest is None else command_set_digest
        actions = SimpleNamespace(
            _prior_delivery_registry_binding=mock.Mock(return_value={"validation": []})
        )
        with (
            mock.patch.object(
                source,
                "_authenticate_exact_materialized_source",
                return_value=(policy.source_head_sha, policy.source_tree_sha, BLOB),
            ),
            mock.patch.object(source, "_load_actions_helper", return_value=actions),
            mock.patch.object(
                fast_path, "digest_json", return_value=command_set_digest
            ),
        ):
            return source._authenticate_recovered_materialized_source(
                Path("/fixture"), self.trust, policy
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
        self.assertEqual(
            verified.historical_evidence_status,
            source.HISTORICAL_EVIDENCE_PRESENT,
        )
        self.assertIsNone(verified.recovery_authority_digest)
        self.assertIsNone(verified.recovery_validation_digest)
        self.assertIsNone(verified.recovery_technical_security_gate_digest)

    def test_exact_recovery_has_distinct_accepted_authority_identities(self) -> None:
        recovery = self.policy.evidence_loss_recovery
        self.assertIsNotNone(recovery)
        verified = self._recover()
        self.assertTrue(source.is_verified_bootstrap_source(verified))
        self.assertEqual(
            verified.historical_evidence_status,
            source.HISTORICAL_EVIDENCE_RECOVERY,
        )
        self.assertEqual(verified.validation_receipt_digest, RECEIPT)
        self.assertEqual(verified.final_attestation_digest, ATTESTATION)
        self.assertEqual(verified.recovery_authority_digest, recovery.recovery_digest)
        self.assertEqual(
            verified.recovery_validation_digest,
            recovery.recovery_validation.validation_digest,
        )
        self.assertEqual(
            verified.recovery_technical_security_gate_digest,
            recovery.technical_security_gate.gate_digest,
        )

    def test_absent_recovery_policy_fails_closed(self) -> None:
        policy = replace(self.policy, evidence_loss_recovery=None)
        with self.assertRaisesRegex(
            source.BootstrapSourceAdmissionError, "recovery is absent"
        ):
            self._recover(policy=policy)

    def test_recovery_for_another_source_fails_closed(self) -> None:
        recovery = self.policy.evidence_loss_recovery
        self.assertIsNotNone(recovery)
        for changed in (
            replace(
                recovery,
                source_admission_digest="0" * 64,
            ),
            replace(
                recovery,
                recovery_validation=replace(
                    recovery.recovery_validation, source_head_sha="1" * 40
                ),
            ),
            replace(
                recovery,
                technical_security_gate=replace(
                    recovery.technical_security_gate, source_tree_sha="2" * 40
                ),
            ),
        ):
            with self.subTest(changed=changed):
                policy = replace(self.policy, evidence_loss_recovery=changed)
                with self.assertRaisesRegex(
                    source.BootstrapSourceAdmissionError, "recovery is invalid"
                ):
                    self._recover(policy=policy)

    def test_failed_recovery_validation_or_security_gate_fails_closed(self) -> None:
        recovery = self.policy.evidence_loss_recovery
        self.assertIsNotNone(recovery)
        cases = (
            replace(
                recovery,
                recovery_validation=replace(
                    recovery.recovery_validation, result="FAILED"
                ),
            ),
            replace(
                recovery,
                technical_security_gate=replace(
                    recovery.technical_security_gate, result="OPEN_FINDING"
                ),
            ),
        )
        for changed in cases:
            with self.subTest(changed=changed):
                policy = replace(self.policy, evidence_loss_recovery=changed)
                with self.assertRaisesRegex(
                    source.BootstrapSourceAdmissionError, "recovery is invalid"
                ):
                    self._recover(policy=policy)

    def test_recovery_validation_rejects_historical_command_set_drift(self) -> None:
        with self.assertRaisesRegex(
            source.BootstrapSourceAdmissionError, "recovery is invalid"
        ):
            self._recover(command_set_digest="3" * 64)

    def test_malformed_or_cross_source_recovery_registry_fails_closed(self) -> None:
        registry_path = source.authority._TRUST_REGISTRY
        registry = json.loads(registry_path.read_text(encoding="utf-8"))

        def recovery(document):
            repository = next(
                item
                for item in document["repositories"]
                if item["repository"] == REPOSITORY
            )
            return repository["lifecycle_authority_policy"][
                "bootstrap_source_admissions"
            ][0]["evidence_loss_recovery"]

        mutations = (
            lambda item: item.update(untrusted_extra=True),
            lambda item: item.update(kind="GENERIC_RECOVERY"),
            lambda item: item.update(source_admission_digest="4" * 64),
            lambda item: item["recovery_validation"].update(
                source_head_sha="5" * 40
            ),
        )
        for mutate in mutations:
            changed = json.loads(json.dumps(registry))
            mutate(recovery(changed))
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "repositories.json"
                path.write_text(json.dumps(changed), encoding="utf-8")
                with (
                    self.subTest(mutate=mutate),
                    mock.patch.object(source.authority, "_TRUST_REGISTRY", path),
                    self.assertRaises(source.authority.LifecycleAuthorityError),
                ):
                    source.authority._load_lifecycle_trust_policy(REPOSITORY)

    def test_changed_receipt_trailer_fails_before_evidence_mode_selection(self) -> None:
        def git_text(_root, arguments):
            if arguments == ["rev-parse", "HEAD"]:
                return HEAD + "\n"
            if arguments == ["rev-parse", f"{HEAD}^{{tree}}"]:
                return TREE + "\n"
            if arguments[:3] == ["rev-list", "--parents", "-n"]:
                return f"{HEAD} {PARENT}\n"
            raise AssertionError(arguments)

        with (
            mock.patch.object(source, "_git_text", side_effect=git_text),
            mock.patch.object(source, "_verify_commit_signature"),
            mock.patch.object(source, "_exact_trailer", return_value="6" * 64),
            mock.patch.object(source, "_implementation_blob") as implementation,
            self.assertRaisesRegex(
                source.BootstrapSourceAdmissionError, "trailer changed"
            ),
        ):
            source._authenticate_exact_materialized_source(
                Path("/fixture"), self.trust, self.policy
            )
        implementation.assert_not_called()

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
            "recovery",
            "recovery_document",
            "validation_result",
            "technical_security_gate",
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
            mock.patch.object(source, "_verify_diagnostic_raise_site_agreement"),
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
            mock.patch.object(source, "_verify_diagnostic_raise_site_agreement"),
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
            "base": {"ref": "main", "repo": {"full_name": REPOSITORY}},
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
            source._authenticate_live_github_source(self.policy)
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
                source._authenticate_live_github_source(self.policy)

    def test_github_observation_normalization_and_admission_are_separate(self) -> None:
        pull = {
            "number": PR,
            "state": "open",
            "draft": True,
            "base": {
                "ref": "release",
                "repo": {"full_name": REPOSITORY},
            },
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
        results = [
            subprocess.CompletedProcess([], 0, json.dumps(value).encode(), b"")
            for value in (pull, commit)
        ]
        with mock.patch.object(source.publication, "_run_gh", side_effect=results):
            observation = source._observe_github(self.policy)

        self.assertIsInstance(observation, source.GitHubSourceObservation)
        self.assertNotIn("_run_gh", inspect.getsource(source._normalize_github_observation))
        self.assertNotIn("_run_gh", inspect.getsource(source._admit_github_source))
        facts = source._normalize_github_observation(observation)
        self.assertEqual(facts.base_ref, "release")
        with self.assertRaisesRegex(
            source.BootstrapSourceAdmissionError, "binding changed"
        ):
            source._admit_github_source(facts, self.policy)

    def test_retargeted_source_pr_is_rejected_with_unchanged_source_identity(self) -> None:
        pull = {
            "number": PR,
            "state": "open",
            "draft": True,
            "base": {
                "ref": "release",
                "repo": {"full_name": REPOSITORY},
            },
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
        results = [
            subprocess.CompletedProcess([], 0, json.dumps(value).encode(), b"")
            for value in (pull, commit)
        ]
        with (
            mock.patch.object(source.publication, "_run_gh", side_effect=results),
            self.assertRaisesRegex(
                source.BootstrapSourceAdmissionError, "binding changed"
            ),
        ):
            source._authenticate_live_github_source(self.policy)

    def test_distinct_child_failures_retain_closed_diagnostic_identity(self) -> None:
        identities = source._EXECUTION_DIAGNOSTIC_IDENTITIES
        for identity in identities:
            completed = subprocess.CompletedProcess(
                [],
                70,
                json.dumps(
                    {"status": "REJECTED", "diagnostic_identity": identity}
                ).encode(),
                b"secret child detail must not escape",
            )
            with (
                self.subTest(identity=identity),
                mock.patch.object(source, "_trusted_python", return_value="/usr/bin/python3"),
                mock.patch.object(
                    source.authority,
                    "_load_trusted_command_helper",
                    return_value=SimpleNamespace(
                        command_environment=lambda _name: {},
                        TRUSTED_COMMAND_PATH="/usr/bin",
                    ),
                ),
                mock.patch.object(subprocess, "run", return_value=completed),
                self.assertRaises(source.BootstrapSourceAdmissionError) as raised,
            ):
                source._execute_entrypoint(Path("/exact/source"), b"authorization")
            self.assertEqual(raised.exception.diagnostic_identity, identity)
            self.assertNotIn("secret child detail", str(raised.exception))
        self.assertEqual(
            source.BootstrapSourceAdmissionError("admission failed").diagnostic_identity,
            source.SOURCE_ADMISSION_FAILURE,
        )
        for identity in identities:
            self.assertIn(identity, source._LAUNCHER)
        with self.assertRaises(source.BootstrapSourceAdmissionError) as raised:
            source._execute_entrypoint(Path("/exact/source"), b"")
        self.assertEqual(
            raised.exception.diagnostic_identity,
            "AUTHORIZATION_ORCHESTRATION_FAILURE",
        )

    def test_malformed_child_failure_uses_closed_unexpected_identity(self) -> None:
        completed = subprocess.CompletedProcess(
            [], 70, b"attacker-controlled output", b"secret stderr"
        )
        with (
            mock.patch.object(source, "_trusted_python", return_value="/usr/bin/python3"),
            mock.patch.object(
                source.authority,
                "_load_trusted_command_helper",
                return_value=SimpleNamespace(
                    command_environment=lambda _name: {},
                    TRUSTED_COMMAND_PATH="/usr/bin",
                ),
            ),
            mock.patch.object(subprocess, "run", return_value=completed),
            self.assertRaises(source.BootstrapSourceAdmissionError) as raised,
        ):
            source._execute_entrypoint(Path("/exact/source"), b"authorization")
        self.assertEqual(
            raised.exception.diagnostic_identity,
            "UNEXPECTED_CLOSED_CHILD_FAILURE",
        )
        self.assertNotIn("attacker-controlled", str(raised.exception))
        self.assertNotIn("secret stderr", str(raised.exception))

    def test_exact_executor_raise_sites_have_exhaustive_diagnostic_agreement(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        raw = subprocess.run(
            ["git", "cat-file", "blob", BLOB],
            cwd=repository_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        ).stdout
        sites = source._verify_diagnostic_raise_site_agreement(raw, BLOB)
        mapping = dict(source._DIAGNOSTIC_RAISE_SITES)

        self.assertEqual(len(sites), 40)
        self.assertEqual(sites, frozenset(mapping))
        exact_examples = {
            ("_execute_lifecycle_transition", 592):
                "AUTHORIZATION_ORCHESTRATION_FAILURE",
            ("_execute_lifecycle_transition", 697):
                "CURRENT_OBSERVATION_VERIFICATION_FAILURE",
            ("_read_live_github", 505): "GITHUB_OBSERVATION_FAILURE",
            ("_execute_lifecycle_transition", 692):
                "GITHUB_MUTATION_READBACK_FAILURE",
            ("_append_successor_evidence", 388):
                "SIGNING_SUCCESSOR_DERIVATION_FAILURE",
            ("_execute_lifecycle_transition", 744):
                "LIFECYCLE_PUBLICATION_FAILURE",
            ("_execute_lifecycle_transition", 758): "FINAL_CONVERGENCE_FAILURE",
            ("_validate_live_pull_request", 125): "GITHUB_OBSERVATION_FAILURE",
            ("_single_role_identity", 410):
                "SIGNING_SUCCESSOR_DERIVATION_FAILURE",
        }
        for site, expected_identity in exact_examples.items():
            self.assertEqual(mapping[site], expected_identity)
        for expected_identity in source._EXECUTION_DIAGNOSTIC_IDENTITIES - {
            "UNEXPECTED_CLOSED_CHILD_FAILURE"
        }:
            self.assertIn(expected_identity, mapping.values())
        self.assertNotIn("str(error)", source._LAUNCHER)
        with self.assertRaisesRegex(
            source.BootstrapSourceAdmissionError, "agreement is not exact"
        ):
            source._verify_diagnostic_raise_site_agreement(raw, "0" * 40)

    def test_real_isolated_launcher_uses_exact_traceback_site_and_hides_text(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        archived = subprocess.run(
            ["git", "archive", HEAD],
            cwd=repository_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        ).stdout
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with tarfile.open(fileobj=io.BytesIO(archived), mode="r:") as archive:
                archive.extractall(root, filter="data")
            with self.assertRaises(source.BootstrapSourceAdmissionError) as raised:
                source._execute_entrypoint(root, b"not signed authorization")
        self.assertEqual(
            raised.exception.diagnostic_identity,
            "AUTHORIZATION_ORCHESTRATION_FAILURE",
        )
        self.assertNotIn("authorization is invalid", str(raised.exception))

    def test_substituted_executor_cannot_select_identity_by_message(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "scripts" / "secpal_pr_review"
            package.mkdir(parents=True)
            (root / "scripts" / "__init__.py").write_text("", encoding="utf-8")
            (package / "__init__.py").write_text("", encoding="utf-8")
            (package / "lifecycle_execution.py").write_text(
                "def execute_lifecycle_transition(repository, issue, authorization):\n"
                "    raise ValueError('publication response differs from verified CURRENT')\n",
                encoding="utf-8",
            )
            with self.assertRaises(source.BootstrapSourceAdmissionError) as raised:
                source._execute_entrypoint(root, b"authorization")
        self.assertEqual(
            raised.exception.diagnostic_identity,
            "UNEXPECTED_CLOSED_CHILD_FAILURE",
        )
        self.assertNotIn("publication response", str(raised.exception))

    def test_oversized_evidence_is_rejected_by_bounded_regular_file_read(self) -> None:
        filenames = (
            "reviewed-state.json",
            "validation-receipt.json",
            "final-attestation.json",
        )
        for oversized_filename in filenames:
            with self.subTest(filename=oversized_filename), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for filename in filenames:
                    (root / filename).write_bytes(b"{}")
                oversized = root / oversized_filename
                with oversized.open("wb") as handle:
                    handle.truncate(source.MAXIMUM_EVIDENCE_BYTES + 1)
                with self.assertRaisesRegex(
                    source.BootstrapSourceAdmissionError, "size is invalid"
                ):
                    source._read_evidence(root)
        self.assertNotIn("read_bytes", inspect.getsource(source._read_evidence))

    def test_empty_and_symlinked_evidence_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for filename in (
                "reviewed-state.json",
                "validation-receipt.json",
                "final-attestation.json",
            ):
                (root / filename).write_bytes(b"{}")
            (root / "reviewed-state.json").write_bytes(b"")
            with self.assertRaises(source.BootstrapSourceAdmissionError):
                source._read_evidence(root)
            (root / "reviewed-state.json").unlink()
            (root / "reviewed-state.json").symlink_to(root / "validation-receipt.json")
            with self.assertRaises(source.BootstrapSourceAdmissionError):
                source._read_evidence(root)

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
            mock.patch.object(source, "_authenticate_live_github_source"),
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

    def test_absent_historical_evidence_uses_only_accepted_recovery(self) -> None:
        @contextmanager
        def isolated(_trust, _policy):
            yield Path("/fixture")

        verified = self._authenticate()
        with (
            mock.patch.object(source, "_authenticate_live_github_source"),
            mock.patch.object(source, "_authenticate_live_recovery_review_state"),
            mock.patch.object(source, "_isolated_source_repository", isolated),
            mock.patch.object(
                source,
                "_authenticate_recovered_materialized_source",
                create=True,
                return_value=verified,
            ) as recover,
            mock.patch.object(source, "_verify_materialized_tree"),
            mock.patch.object(source, "_read_evidence") as read_evidence,
        ):
            result = source.verify_first_ready_executor_source(REPOSITORY, ISSUE)
        self.assertIs(result, verified)
        recover.assert_called_once_with(Path("/fixture"), self.trust, self.policy)
        read_evidence.assert_not_called()

    def test_recovery_live_review_state_is_exact_and_has_no_open_thread(self) -> None:
        gate = self.policy.evidence_loss_recovery.technical_security_gate
        document = {
            "data": {
                "repository": {
                    "nameWithOwner": REPOSITORY,
                    "pullRequest": {
                        "number": PR,
                        "reviewDecision": None,
                        "comments": {
                            "totalCount": gate.conversation_comment_count,
                            "pageInfo": {"hasNextPage": False},
                        },
                        "reviewThreads": {
                            "totalCount": gate.resolved_review_thread_count,
                            "pageInfo": {"hasNextPage": False},
                            "nodes": [
                                {"isResolved": True}
                                for _ in range(gate.resolved_review_thread_count)
                            ],
                        },
                    },
                }
            }
        }
        raw = json.dumps(document).encode("utf-8")
        with mock.patch.object(
            source, "_observe_recovery_review_state", return_value=raw
        ):
            source._authenticate_live_recovery_review_state(self.policy)

        changed_cases = (
            lambda value: value["data"]["repository"]["pullRequest"].update(
                reviewDecision="CHANGES_REQUESTED"
            ),
            lambda value: value["data"]["repository"]["pullRequest"][
                "comments"
            ].update(totalCount=1),
            lambda value: value["data"]["repository"]["pullRequest"][
                "reviewThreads"
            ]["nodes"][0].update(isResolved=False),
            lambda value: value["data"]["repository"]["pullRequest"][
                "reviewThreads"
            ]["pageInfo"].update(hasNextPage=True),
        )
        for mutate in changed_cases:
            changed = json.loads(json.dumps(document))
            mutate(changed)
            with (
                self.subTest(mutate=mutate),
                mock.patch.object(
                    source,
                    "_observe_recovery_review_state",
                    return_value=json.dumps(changed).encode("utf-8"),
                ),
                self.assertRaises(source.BootstrapSourceAdmissionError),
            ):
                source._authenticate_live_recovery_review_state(self.policy)

    def test_invalid_ordinary_evidence_never_falls_back_to_recovery(self) -> None:
        with (
            mock.patch.object(
                source,
                "_read_evidence",
                side_effect=source.BootstrapSourceAdmissionError(
                    "source validation evidence is invalid"
                ),
            ),
            mock.patch.object(
                source, "_authenticate_recovered_materialized_source"
            ) as recover,
            self.assertRaisesRegex(
                source.BootstrapSourceAdmissionError,
                "source validation evidence is invalid",
            ),
        ):
            source.verify_first_ready_executor_source(
                REPOSITORY,
                ISSUE,
                source_evidence_directory="/supplied-invalid-evidence",
            )
        recover.assert_not_called()

    def test_only_verified_source_can_reach_exact_entrypoint(self) -> None:
        @contextmanager
        def isolated(_trust, _policy):
            yield Path("/fixture")

        verified = self._authenticate()
        with (
            mock.patch.object(source, "_read_evidence", return_value=({}, {}, {})),
            mock.patch.object(source, "_authenticate_live_github_source"),
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
        self.assertEqual(admission.source_base_ref, "main")
        self.assertEqual(
            admission.admission_digest,
            "dde958066ab287feefdc88e9bf2e92aa3b6df390d7c713be3486f719da9956b4",
        )
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
