# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Contract tests for closed exact bootstrap source-admission subtypes."""

from __future__ import annotations

import base64
from contextlib import contextmanager
from dataclasses import replace
import hashlib
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
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
RECOVERY_FEEDBACK_DIGEST = "d2236120f769caa74d5da0435330c103a036dfe68a5e0f8274d43a3916ca8f2b"
HISTORICAL_SOURCE_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "bootstrap-source-admission-a668f664.pack.b64"
)
# This is the minimal historical object set needed to bind the admitted
# commit to its executable paths and import the exact executor in isolation.
HISTORICAL_SOURCE_FILES = {
    "scripts/secpal_pr_review/fast_path.py": (
        "d924628f7bb18be9575eb761ab429462bd9b69c8"
    ),
    "scripts/secpal_pr_review/follow_up.py": (
        "1380027b1f771dfbd3f318a95b31efaad0ec0835"
    ),
    "scripts/secpal_pr_review/late_disposition.py": (
        "beec15391a6f5a249fe5eb3deaf603b988146b7a"
    ),
    "scripts/secpal_pr_review/lifecycle_authority.py": (
        "45d3b020ffad90a1be55cf8d4ac971dce823f2d8"
    ),
    "scripts/secpal_pr_review/lifecycle_execution.py": BLOB,
    "scripts/secpal_pr_review/lifecycle_orchestration.py": (
        "0cc24301660af6654cd25f3687644bf868f59331"
    ),
    "scripts/secpal_pr_review/lifecycle_publication.py": (
        "3e3e55bff14118b9cac12699d41cc8381758aea1"
    ),
    "scripts/secpal_work_graph/__init__.py": (
        "1cfe7fd9d9479c1f3356574e566dd8bf39391d04"
    ),
    "scripts/secpal_work_graph/model.py": (
        "11b18ad1a82570aa0d17a18efb11120fe2eaae0a"
    ),
    "scripts/secpal_work_graph/replanning.py": (
        "2f1a13e1c2ddd4966683a4dd310a1993c60872a5"
    ),
}
HISTORICAL_SOURCE_OBJECTS = frozenset(
    {
        HEAD,
        TREE,
        PARENT,
        "565cdf820a0745a07ff8bb81817a7fea931be70b",
        "a619c2a7c4d50152e4aa77baab32c74e03474c91",
        "7d0191f68a7461329cbd7653e3f7ed66d5fdcdf8",
        *HISTORICAL_SOURCE_FILES.values(),
    }
)

EVIDENCE_HELPER_ISSUE = 818
EVIDENCE_HELPER_PR = 819
EVIDENCE_HELPER_HEAD = "e14f7668354763af5033f511097ddf990d6e8ef5"
EVIDENCE_HELPER_CURRENT_HEAD = "b297745297b7aa98ba24ef05c011a7906a0a43d8"
EVIDENCE_HELPER_TREE = "5065ce77573e9753249de055f6122f14362cbb30"
EVIDENCE_HELPER_PARENT = "b297745297b7aa98ba24ef05c011a7906a0a43d8"
EVIDENCE_HELPER_RECEIPT = (
    "4a21e7f8b0f3a96bdecf78b97a55cf77c12b9fae7b012c32d3d19d2f1195801e"
)
EVIDENCE_HELPER_ATTESTATION = (
    "6e17c6e1bb3a9a11538605206ef7b6dd6c8738d9f7dedc03ab1c913303cbd0fd"
)
EVIDENCE_HELPER_PATH = "scripts/secpal-pr-review.py"
EVIDENCE_HELPER_BLOB = "130e49df1c6e90c3db1b4286e74639f1d3fc1418"
EVIDENCE_HELPER_OLD_BLOB = "b37b30eeb7b44bed26d517d096f92e31aa0dd0ff"
EVIDENCE_HELPER_SUBTYPE = "PR_REVIEW_EVIDENCE_HELPER_SOURCE"
EVIDENCE_HELPER_PURPOSE = "PR_REVIEW_EVIDENCE_HELPER_SOURCE_ADMISSION"
EVIDENCE_HELPER_ADMISSION_DIGEST = (
    "38aa92b53d5289db44063ce4197687c18bb162c344aa37326ee2703013158418"
)
PROTECTED_MAIN_HEAD = "a5a7b0704645659a5db7df820b2d448de3859560"


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

    @staticmethod
    def _historical_git_environment() -> dict[str, str]:
        return {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PATH": os.environ.get("PATH", os.defpath),
        }

    def _historical_git(
        self,
        git_directory: Path,
        arguments: list[str],
        *,
        input_bytes: bytes | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            ["git", "--git-dir", str(git_directory), *arguments],
            cwd=git_directory.parent,
            env=self._historical_git_environment(),
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=check,
        )

    @contextmanager
    def _isolated_historical_source(self, pack: bytes | None = None):
        if pack is None:
            encoded = b"".join(HISTORICAL_SOURCE_FIXTURE.read_bytes().splitlines())
            pack = base64.b64decode(encoded, validate=True)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            git_directory = root / "fixture.git"
            subprocess.run(
                ["git", "init", "--bare", str(git_directory)],
                cwd=root,
                env=self._historical_git_environment(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            for identity, kind in (
                (HEAD, "commit"),
                (PARENT, "commit"),
                (BLOB, "blob"),
            ):
                absent = self._historical_git(
                    git_directory,
                    ["cat-file", "-e", f"{identity}^{{{kind}}}"],
                    check=False,
                )
                self.assertNotEqual(absent.returncode, 0)

            self._historical_git(
                git_directory,
                ["index-pack", "--stdin", "--fix-thin"],
                input_bytes=pack,
            )
            observed_objects = frozenset(
                self._historical_git(
                    git_directory,
                    [
                        "cat-file",
                        "--batch-all-objects",
                        "--batch-check=%(objectname)",
                    ],
                ).stdout.decode("ascii").splitlines()
            )
            self.assertEqual(observed_objects, HISTORICAL_SOURCE_OBJECTS)
            identities = self._historical_git(
                git_directory,
                [
                    "rev-parse",
                    f"{HEAD}^{{commit}}",
                    f"{HEAD}^{{tree}}",
                    f"{HEAD}^",
                    f"{PARENT}^{{commit}}",
                ],
            ).stdout.decode("ascii").splitlines()
            self.assertEqual(identities, [HEAD, TREE, PARENT, PARENT])

            source_root = root / "source"
            for path, expected_blob in HISTORICAL_SOURCE_FILES.items():
                observed_blob = self._historical_git(
                    git_directory, ["rev-parse", f"{HEAD}:{path}"]
                ).stdout.decode("ascii").strip()
                self.assertEqual(observed_blob, expected_blob)
                raw = self._historical_git(
                    git_directory, ["cat-file", "blob", observed_blob]
                ).stdout
                destination = source_root / path
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(raw)
            yield git_directory, source_root

    def _recovery_review_document(self) -> dict[str, object]:
        actor = {
            "database_id": 223894421,
            "login": "github-code-quality",
            "node_id": "BOT_kgDODVhblQ",
        }
        feedback = {
            "pull_request_reactions": [],
            "reviews": [
                {
                    "actor": actor,
                    "body_digest": hashlib.sha256(b"").hexdigest(),
                    "commit_oid": PARENT,
                    "node_id": "PRR_kwDOQFR1MM8AAAABL7Ibaw",
                    "reactions": [],
                    "state": "COMMENTED",
                }
            ],
            "conversation_comments": [],
            "threads": [
                {
                    "comments": [
                        {
                            "actor": actor,
                            "body_digest": "1671e9ff600d488e7f94d664c51058190e9238b014089e9585e34b6e91755a5b",
                            "node_id": "PRRC_kwDOQFR1MM7pkv_s",
                            "reactions": [],
                            "reply_to_id": None,
                        }
                    ],
                    "is_outdated": True,
                    "is_resolved": True,
                    "node_id": "PRRT_kwDOQFR1MM6erzK6",
                },
                {
                    "comments": [
                        {
                            "actor": actor,
                            "body_digest": "af1358df331afa7893179422cbc889373591d559da432d00586302f8386f8bd9",
                            "node_id": "PRRC_kwDOQFR1MM7pkwAK",
                            "reactions": [],
                            "reply_to_id": None,
                        }
                    ],
                    "is_outdated": True,
                    "is_resolved": True,
                    "node_id": "PRRT_kwDOQFR1MM6erzLQ",
                },
            ],
        }
        reviewed = fast_path.StableFeedbackState(
            repository=REPOSITORY,
            pull_request_number=PR,
            head_sha=HEAD,
            base_ref="main",
            base_sha="7d36b28b8dc596e91ffb91eeb1ae1ffd2f19dc19",
            pr_state="OPEN",
            feedback=feedback,
        )
        self.assertEqual(reviewed.feedback_digest, RECOVERY_FEEDBACK_DIGEST)
        return {
            "repository": reviewed.repository,
            "pull_request_number": reviewed.pull_request_number,
            "head_sha": reviewed.head_sha,
            "base_ref": reviewed.base_ref,
            "base_sha": reviewed.base_sha,
            "pr_state": reviewed.pr_state,
            "review_decision": None,
            "feedback": reviewed.feedback,
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
            lambda item: item["technical_security_gate"].update(
                feedback_inventory_digest="6" * 64
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
                    mock.patch.object(source, "_run_bootstrap_git", return_value=completed),
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
            "feedback_inventory_digest",
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
            mock.patch.object(source, "_run_bootstrap_git", return_value=absent),
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
                mock.patch.object(source, "_run_bootstrap_git", return_value=absent),
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
            mock.patch.object(source, "_run_bootstrap_git", return_value=present),
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
            source, "_run_bootstrap_gh", side_effect=results((pull, commit))
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
                    source,
                    "_run_bootstrap_gh",
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
        with mock.patch.object(source, "_run_bootstrap_gh", side_effect=results):
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
            mock.patch.object(source, "_run_bootstrap_gh", side_effect=results),
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
        with self._isolated_historical_source() as (git_directory, _source_root):
            raw = self._historical_git(
                git_directory, ["cat-file", "blob", BLOB]
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
        with self._isolated_historical_source() as (_git_directory, source_root):
            with self.assertRaises(source.BootstrapSourceAdmissionError) as raised:
                source._execute_entrypoint(
                    source_root, b"not signed authorization"
                )
        self.assertEqual(
            raised.exception.diagnostic_identity,
            "AUTHORIZATION_ORCHESTRATION_FAILURE",
        )
        self.assertNotIn("authorization is invalid", str(raised.exception))

    def test_historical_source_fixture_materializes_from_empty_object_database(self) -> None:
        with self._isolated_historical_source() as (git_directory, source_root):
            observed_blob = self._historical_git(
                git_directory,
                ["hash-object", str(source_root / source.IMPLEMENTATION_PATH)],
            ).stdout.decode("ascii").strip()
        self.assertEqual(observed_blob, BLOB)

    def test_substituted_historical_source_fixture_fails_closed(self) -> None:
        encoded = b"".join(HISTORICAL_SOURCE_FIXTURE.read_bytes().splitlines())
        substituted = bytearray(base64.b64decode(encoded, validate=True))
        substituted[len(substituted) // 2] ^= 1
        with self.assertRaises(subprocess.CalledProcessError):
            with self._isolated_historical_source(bytes(substituted)):
                pass

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
        document = self._recovery_review_document()
        raw = source.authority.canonical_json_bytes(document)
        with mock.patch.object(
            source, "_observe_recovery_review_state", return_value=raw
        ):
            source._authenticate_live_recovery_review_state(self.policy)

        changed_cases = (
            lambda value: value.update(review_decision="CHANGES_REQUESTED"),
            lambda value: value.update(head_sha="1" * 40),
            lambda value: value.update(base_ref="other"),
            lambda value: value.update(pr_state="CLOSED"),
            lambda value: value["feedback"]["threads"][0].update(
                is_resolved=False
            ),
        )
        for mutate in changed_cases:
            changed = json.loads(json.dumps(document))
            mutate(changed)
            with (
                self.subTest(mutate=mutate),
                mock.patch.object(
                    source,
                    "_observe_recovery_review_state",
                    return_value=source.authority.canonical_json_bytes(changed),
                ),
                self.assertRaises(source.BootstrapSourceAdmissionError),
            ):
                source._authenticate_live_recovery_review_state(self.policy)

    def test_recovery_rejects_new_commented_review_body(self) -> None:
        document = self._recovery_review_document()
        document["feedback"]["reviews"].append(
            {
                "node_id": "PRR_new_substantive_review",
                "state": "COMMENTED",
                "body_digest": hashlib.sha256(
                    b"Security finding: do not execute."
                ).hexdigest(),
                "actor": {
                    "login": "security-reviewer",
                    "node_id": "USER_security_reviewer",
                    "database_id": 82,
                },
                "commit_oid": HEAD,
                "reactions": [],
            }
        )
        with (
            mock.patch.object(
                source,
                "_observe_recovery_review_state",
                return_value=source.authority.canonical_json_bytes(document),
            ),
            self.assertRaises(source.BootstrapSourceAdmissionError),
        ):
            source._authenticate_live_recovery_review_state(self.policy)

    def test_recovery_rejects_same_count_thread_identity_substitution(self) -> None:
        document = self._recovery_review_document()
        replacement = document["feedback"]["threads"][0]
        replacement["node_id"] = "PRRT_replacement"
        replacement["comments"][0]["node_id"] = "PRRC_replacement"
        replacement["comments"][0]["body_digest"] = "7" * 64
        with (
            mock.patch.object(
                source,
                "_observe_recovery_review_state",
                return_value=source.authority.canonical_json_bytes(document),
            ),
            self.assertRaises(source.BootstrapSourceAdmissionError),
        ):
            source._authenticate_live_recovery_review_state(self.policy)

    def test_recovery_rejects_same_count_review_identity_content_or_head_drift(self) -> None:
        mutations = (
            lambda review: review.update(node_id="PRR_replacement"),
            lambda review: review.update(body_digest="8" * 64),
            lambda review: review["actor"].update(login="replacement-reviewer"),
            lambda review: review.update(commit_oid=HEAD),
        )
        for mutate in mutations:
            document = self._recovery_review_document()
            mutate(document["feedback"]["reviews"][0])
            with (
                self.subTest(mutate=mutate),
                mock.patch.object(
                    source,
                    "_observe_recovery_review_state",
                    return_value=source.authority.canonical_json_bytes(document),
                ),
                self.assertRaises(source.BootstrapSourceAdmissionError),
            ):
                source._authenticate_live_recovery_review_state(self.policy)

    def test_recovery_rejects_new_conversation_comment(self) -> None:
        document = self._recovery_review_document()
        document["feedback"]["conversation_comments"].append(
            {
                "node_id": "IC_new_finding",
                "body_digest": "9" * 64,
                "actor": {
                    "login": "security-reviewer",
                    "node_id": "USER_security_reviewer",
                    "database_id": 82,
                },
                "updated_at": "2026-09-04T10:00:00Z",
                "reactions": [],
            }
        )
        with (
            mock.patch.object(
                source,
                "_observe_recovery_review_state",
                return_value=source.authority.canonical_json_bytes(document),
            ),
            self.assertRaises(source.BootstrapSourceAdmissionError),
        ):
            source._authenticate_live_recovery_review_state(self.policy)

    def test_recovery_rejects_duplicate_feedback_identities(self) -> None:
        mutations = (
            lambda feedback: feedback["reviews"].append(
                dict(feedback["reviews"][0])
            ),
            lambda feedback: feedback["threads"].append(
                dict(feedback["threads"][0])
            ),
            lambda feedback: feedback["threads"][0]["comments"].append(
                dict(feedback["threads"][0]["comments"][0])
            ),
            lambda feedback: feedback["conversation_comments"].append(
                {
                    "node_id": feedback["threads"][0]["comments"][0]["node_id"],
                    "body_digest": "9" * 64,
                    "actor": feedback["threads"][0]["comments"][0]["actor"],
                    "updated_at": "2026-09-04T10:00:00Z",
                    "reactions": [],
                }
            ),
        )
        for mutate in mutations:
            document = self._recovery_review_document()
            mutate(document["feedback"])
            with (
                self.subTest(mutate=mutate),
                mock.patch.object(
                    source,
                    "_observe_recovery_review_state",
                    return_value=source.authority.canonical_json_bytes(document),
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

    def test_recovery_precedes_and_does_not_expand_lifecycle_authorization(self) -> None:
        @contextmanager
        def isolated(_trust, _policy):
            yield Path("/fixture")

        verified = self._recover()
        authorization = b"separately-signed-one-use-authorization"
        calls: list[str] = []

        def authenticate_review(_policy):
            calls.append("feedback")

        def authenticate_source(_root, _trust, _policy):
            calls.append("source")
            return verified

        def execute(_root, serialized):
            calls.append("executor")
            self.assertIs(serialized, authorization)
            return {"status": "COMPLETE"}

        with (
            mock.patch.object(source, "_authenticate_live_github_source"),
            mock.patch.object(
                source,
                "_authenticate_live_recovery_review_state",
                side_effect=authenticate_review,
            ),
            mock.patch.object(source, "_isolated_source_repository", isolated),
            mock.patch.object(
                source,
                "_authenticate_recovered_materialized_source",
                side_effect=authenticate_source,
            ),
            mock.patch.object(source, "_verify_materialized_tree"),
            mock.patch.object(source, "_execute_entrypoint", side_effect=execute),
        ):
            result = source.execute_first_ready_executor_bootstrap(
                REPOSITORY, ISSUE, authorization
            )
        self.assertEqual(result, {"status": "COMPLETE"})
        self.assertEqual(calls, ["feedback", "source", "executor"])
        self.assertNotIn(
            "recovery",
            set(inspect.signature(source._execute_entrypoint).parameters),
        )

    def test_historical_genesis_repair_and_787_remain_separate(self) -> None:
        self.assertEqual(len(self.trust.bootstrap_genesis_repairs), 1)
        repair = self.trust.bootstrap_genesis_repairs[0]
        self.assertEqual((repair.repair_issue, repair.delivery_issue), (774, 736))
        self.assertEqual(len(self.trust.bootstrap_source_admissions), 2)
        admission = next(
            item
            for item in self.trust.bootstrap_source_admissions
            if item.subtype == source.ADMISSION_SUBTYPE
        )
        self.assertEqual((admission.delivery_issue, admission.pull_request), (810, 812))
        self.assertEqual(admission.source_base_ref, "main")
        self.assertEqual(admission.entrypoint, source.ENTRYPOINT)
        self.assertIsNone(admission.implementation_blob_oid)
        self.assertIsNone(admission.policy_source)
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


class EvidenceHelperSourceAdmissionContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.trust = source.authority._load_lifecycle_trust_policy(REPOSITORY)
        self.policy = next(
            item
            for item in self.trust.bootstrap_source_admissions
            if item.subtype == EVIDENCE_HELPER_SUBTYPE
        )
        self.reviewed = fast_path.StableFeedbackState(
            repository=REPOSITORY,
            pull_request_number=EVIDENCE_HELPER_PR,
            head_sha=EVIDENCE_HELPER_PARENT,
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
        self.receipt = {"receipt_digest": EVIDENCE_HELPER_RECEIPT}
        self.attestation = {
            "attestation_digest": EVIDENCE_HELPER_ATTESTATION,
            "manual_gate_evidence": [],
            "validation_receipt_digest": EVIDENCE_HELPER_RECEIPT,
        }

    def _protected_main_observation(
        self,
        *,
        repository: str = REPOSITORY,
        default_branch: str = "main",
        head_sha: str = PROTECTED_MAIN_HEAD,
    ) -> source.ProtectedMainObservation:
        return source.ProtectedMainObservation(
            repository_json=json.dumps(
                {
                    "data": {
                        "repository": {
                            "nameWithOwner": repository,
                            "defaultBranchRef": {
                                "name": default_branch,
                                "target": {"oid": head_sha},
                            },
                        }
                    }
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )

    def _protected_main_registry(self) -> bytes:
        return subprocess.check_output(
            [
                "git",
                "show",
                f"{PROTECTED_MAIN_HEAD}:{source.PROTECTED_MAIN_REGISTRY_PATH}",
            ]
        )

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
        observed_head=EVIDENCE_HELPER_HEAD,
        observed_tree=EVIDENCE_HELPER_TREE,
        observed_parent=EVIDENCE_HELPER_PARENT,
        receipt=None,
        attestation=None,
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

        actions = SimpleNamespace(
            _prior_delivery_registry_binding=mock.Mock(
                return_value={"validation": [], "manual_gates": []}
            )
        )
        with (
            mock.patch.object(source, "_git_text", side_effect=git_text),
            mock.patch.object(source, "_verify_commit_signature"),
            mock.patch.object(
                source, "_exact_trailer", return_value=policy.validation_receipt_digest
            ),
            mock.patch.object(source, "_load_actions_helper", return_value=actions),
            mock.patch.object(
                fast_path, "verify_reviewed_state_evidence", return_value=self.reviewed
            ),
            mock.patch.object(
                fast_path, "create_validation_receipt", return_value=receipt
            ),
            mock.patch.object(
                fast_path,
                "verify_validation_attestation",
                return_value=self._verified_validation(policy),
            ),
            mock.patch.object(
                source,
                "_implementation_blob",
                return_value=policy.implementation_blob_oid,
            ),
        ):
            return source._authenticate_materialized_source(
                Path("/fixture"), self.trust, policy, ({}, receipt, attestation)
            )

    def test_exact_byte_only_policy_is_independently_maintained(self) -> None:
        with mock.patch.object(
            source,
            "_load_protected_main_trust_policy",
            return_value=self.trust,
        ):
            _trust, policy = source._select_evidence_helper_policy(
                REPOSITORY, EVIDENCE_HELPER_ISSUE
            )
        self.assertEqual(
            (
                policy.subtype,
                policy.repository,
                policy.delivery_issue,
                policy.pull_request,
                policy.source_head_sha,
                policy.source_tree_sha,
                policy.source_parent_sha,
                policy.validation_receipt_digest,
                policy.final_attestation_digest,
                policy.source_signer_identity,
                policy.implementation_path,
                policy.implementation_blob_oid,
                policy.entrypoint,
                policy.purpose,
                policy.policy_source,
                policy.admission_digest,
            ),
            (
                EVIDENCE_HELPER_SUBTYPE,
                REPOSITORY,
                EVIDENCE_HELPER_ISSUE,
                EVIDENCE_HELPER_PR,
                EVIDENCE_HELPER_HEAD,
                EVIDENCE_HELPER_TREE,
                EVIDENCE_HELPER_PARENT,
                EVIDENCE_HELPER_RECEIPT,
                EVIDENCE_HELPER_ATTESTATION,
                "aroviqen@secpal.app",
                EVIDENCE_HELPER_PATH,
                EVIDENCE_HELPER_BLOB,
                None,
                EVIDENCE_HELPER_PURPOSE,
                source.ACCEPTED_MAIN_POLICY_SOURCE,
                EVIDENCE_HELPER_ADMISSION_DIGEST,
            ),
        )

    def test_byte_source_ready_binding_is_exact_boolean(self) -> None:
        registry_path = (
            Path(__file__).resolve().parents[1]
            / ".agents/skills/secpal-pr-review/references/repositories.json"
        )
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        governance = next(
            item
            for item in registry["repositories"]
            if item["repository"] == REPOSITORY
        )
        admission = next(
            item
            for item in governance["lifecycle_authority_policy"][
                "bootstrap_source_admissions"
            ]
            if item["subtype"] == EVIDENCE_HELPER_SUBTYPE
        )
        for expected_draft in (False, True):
            admission["source_pr_draft"] = expected_draft
            admission["admission_digest"] = source.authority.digest_json(
                {
                    key: value
                    for key, value in admission.items()
                    if key != "admission_digest"
                }
            )

            with (
                self.subTest(expected_draft=expected_draft),
                tempfile.TemporaryDirectory() as directory,
            ):
                candidate_registry = Path(directory) / "repositories.json"
                candidate_registry.write_text(json.dumps(registry), encoding="utf-8")
                with mock.patch.object(
                    source.authority, "_TRUST_REGISTRY", candidate_registry
                ):
                    trust = source.authority._load_lifecycle_trust_policy(REPOSITORY)
                exact_policy = next(
                    item
                    for item in trust.bootstrap_source_admissions
                    if item.subtype == EVIDENCE_HELPER_SUBTYPE
                )
                self.assertIs(exact_policy.source_pr_draft, expected_draft)

        admission["source_pr_draft"] = 0
        admission["admission_digest"] = source.authority.digest_json(
            {
                key: value
                for key, value in admission.items()
                if key != "admission_digest"
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            candidate_registry = Path(directory) / "repositories.json"
            candidate_registry.write_text(json.dumps(registry), encoding="utf-8")
            with (
                mock.patch.object(
                    source.authority, "_TRUST_REGISTRY", candidate_registry
                ),
                self.assertRaises(source.authority.LifecycleAuthorityError),
            ):
                source.authority._load_lifecycle_trust_policy(REPOSITORY)

    def test_protected_main_observation_is_exact_and_closed(self) -> None:
        payload = self._protected_main_observation().repository_json
        completed = subprocess.CompletedProcess([], 0, payload, b"")
        with mock.patch.object(
            source, "_run_bootstrap_gh", return_value=completed
        ) as run_gh:
            facts = source._normalize_protected_main(
                source._observe_protected_main()
            )
        self.assertEqual(
            (facts.repository, facts.default_branch, facts.head_sha),
            (REPOSITORY, "main", PROTECTED_MAIN_HEAD),
        )
        arguments = run_gh.call_args.args[0]
        self.assertEqual(arguments[:5], ["api", "--hostname", "github.com", "graphql", "-f"])
        self.assertIn("owner=SecPal", arguments)
        self.assertIn("name=.github", arguments)
        with (
            mock.patch.object(
                source,
                "_run_bootstrap_gh",
                return_value=subprocess.CompletedProcess([], 1, b"", b"unavailable"),
            ),
            self.assertRaisesRegex(
                source.BootstrapSourceAdmissionError, "authority is unavailable"
            ),
        ):
            source._observe_protected_main()
        for observation in (
            self._protected_main_observation(repository="Other/.github"),
            self._protected_main_observation(default_branch="candidate"),
            source.ProtectedMainObservation(repository_json=b"{}"),
            source.ProtectedMainObservation(repository_json=b'{"data":{"repository":null}}'),
        ):
            with self.subTest(observation=observation), self.assertRaises(
                source.BootstrapSourceAdmissionError
            ):
                source._normalize_protected_main(observation)

    def test_bootstrap_capture_rejects_oversized_stdout_and_stderr(self) -> None:
        for stream in ("stdout", "stderr"):
            processes = []
            popen = source.subprocess.Popen

            def record_process(*arguments, **keywords):
                process = popen(*arguments, **keywords)
                processes.append(process)
                return process

            code = (
                "import sys; "
                f"sys.{stream}.buffer.write(b'x' * "
                f"({source.MAXIMUM_EVIDENCE_BYTES} + 1)); "
                f"sys.{stream}.flush()"
            )
            with (
                self.subTest(stream=stream),
                mock.patch.object(
                    source,
                    "_resolve_bootstrap_executable",
                    return_value=sys.executable,
                    create=True,
                ),
                mock.patch.object(
                    source.subprocess, "Popen", side_effect=record_process
                ),
                self.assertRaisesRegex(
                    source.BootstrapSourceAdmissionError,
                    "output limit",
                ),
            ):
                source._run_bootstrap_command("gh", ["-c", code])
            self.assertEqual(len(processes), 1)
            self.assertIsNotNone(processes[0].poll())

    def test_bootstrap_capture_is_small_bounded_concurrent_and_timeout_closed(
        self,
    ) -> None:
        with mock.patch.object(
            source,
            "_resolve_bootstrap_executable",
            return_value=sys.executable,
        ):
            completed = source._run_bootstrap_command(
                "gh",
                [
                    "-c",
                    "import sys; "
                    "sys.stdout.buffer.write(b'o' * 32768); "
                    "sys.stderr.buffer.write(b'e' * 32768)",
                ],
            )
            self.assertEqual(completed.returncode, 0)
            self.assertEqual(completed.stdout, b"o" * 32768)
            self.assertEqual(completed.stderr, b"e" * 32768)
            with (
                mock.patch.object(
                    source, "_BOOTSTRAP_COMMAND_TIMEOUT_SECONDS", 0.05
                ),
                self.assertRaisesRegex(
                    source.BootstrapSourceAdmissionError, "timed out"
                ),
            ):
                source._run_bootstrap_command(
                    "gh", ["-c", "import time; time.sleep(1)"]
                )

    def test_bootstrap_resolution_ignores_ambient_path_and_is_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fake = Path(directory) / "git"
            fake.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
            fake.chmod(0o700)
            with mock.patch.dict(source.os.environ, {"PATH": directory}):
                resolved = source._resolve_bootstrap_executable("git")
            self.assertNotEqual(Path(resolved), fake)
        with self.assertRaisesRegex(
            source.BootstrapSourceAdmissionError, "not allowlisted"
        ):
            source._resolve_bootstrap_executable("python3")

        with tempfile.TemporaryDirectory() as directory:
            unavailable = Path(directory)
            (unavailable / "git").mkdir()
            with (
                mock.patch.object(
                    source, "_BOOTSTRAP_COMMAND_DIRECTORIES", (unavailable,)
                ),
                self.assertRaisesRegex(
                    source.BootstrapSourceAdmissionError, "unavailable"
                ),
            ):
                source._resolve_bootstrap_executable("git")

    def test_bootstrap_environments_are_closed_and_git_never_imports_helper(
        self,
    ) -> None:
        hostile = {
            "PATH": "/candidate/bin",
            "PYTHONPATH": "/candidate/python",
            "LD_PRELOAD": "/candidate/loader",
            "DYLD_INSERT_LIBRARIES": "/candidate/dyld",
            "GIT_DIR": "/candidate/git",
            "GH_TOKEN": "test-token",
        }
        with mock.patch.dict(source.os.environ, hostile, clear=True):
            gh_environment = source._bootstrap_command_environment("gh", None)
            self.assertEqual(gh_environment["PATH"], source._BOOTSTRAP_COMMAND_PATH)
            self.assertEqual(gh_environment["GH_TOKEN"], "test-token")
            for key in (
                "PYTHONPATH", "LD_PRELOAD", "DYLD_INSERT_LIBRARIES", "GIT_DIR"
            ):
                self.assertNotIn(key, gh_environment)

            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                git_environment = source._bootstrap_command_environment("git", root)
                self.assertEqual(git_environment["HOME"], str(root))
                self.assertEqual(
                    git_environment["PATH"], source._BOOTSTRAP_COMMAND_PATH
                )
                for key in hostile:
                    if key not in {"PATH"}:
                        self.assertNotIn(key, git_environment)

        with (
            tempfile.TemporaryDirectory() as directory,
            mock.patch.object(
                source.authority,
                "_load_trusted_command_helper",
                side_effect=AssertionError("candidate helper executed"),
            ) as poisoned_helper,
        ):
            root = Path(directory)
            source._run_bootstrap_git(root, ["init", "--quiet"])
        poisoned_helper.assert_not_called()

    def test_oversized_provider_output_never_reaches_json_normalization(self) -> None:
        normalize = mock.Mock()
        with tempfile.TemporaryDirectory() as directory:
            fake_gh = Path(directory) / "gh"
            fake_gh.write_text(
                "#!/usr/bin/python3\n"
                "import sys\n"
                "sys.stdout.buffer.write(b'{' + b'x' * 65536)\n",
                encoding="utf-8",
            )
            fake_gh.chmod(0o700)
            with (
                mock.patch.object(
                    source,
                    "_resolve_bootstrap_executable",
                    return_value=str(fake_gh),
                ),
                mock.patch.object(source, "_normalize_protected_main", normalize),
                self.assertRaisesRegex(
                    source.BootstrapSourceAdmissionError, "output limit"
                ),
            ):
                source._load_protected_main_trust_policy(REPOSITORY)
        normalize.assert_not_called()

    def test_pre_authentication_command_boundary_never_imports_candidate_helper(
        self,
    ) -> None:
        payload = self._protected_main_observation().repository_json

        @contextmanager
        def isolated(_trust, _policy):
            yield Path("/authenticated-source")

        verified = self._authenticate()
        with tempfile.TemporaryDirectory() as directory:
            fake_gh = Path(directory) / "gh"
            fake_gh.write_text(
                "#!/usr/bin/python3\n"
                "import sys\n"
                f"sys.stdout.buffer.write({payload!r})\n",
                encoding="utf-8",
            )
            fake_gh.chmod(0o700)
            with (
                mock.patch.object(
                    source,
                    "_resolve_bootstrap_executable",
                    return_value=str(fake_gh),
                    create=True,
                ),
                mock.patch.object(
                    source.authority,
                    "_load_trusted_command_helper",
                    side_effect=AssertionError(
                        "unauthenticated checkout helper executed"
                    ),
                ) as poisoned_helper,
                mock.patch.object(
                    source,
                    "_read_protected_main_registry",
                    return_value=Path(
                        ".agents/skills/secpal-pr-review/references/repositories.json"
                    ).read_bytes(),
                ),
                mock.patch.object(
                    source, "_read_evidence", return_value=({}, {}, {})
                ),
                mock.patch.object(source, "_authenticate_live_github_source"),
                mock.patch.object(
                    source, "_isolated_source_repository", isolated
                ),
                mock.patch.object(
                    source,
                    "_authenticate_materialized_source",
                    return_value=verified,
                ),
                mock.patch.object(source, "_verify_materialized_tree"),
            ):
                result = source.verify_pr_review_evidence_helper_source(
                    REPOSITORY,
                    EVIDENCE_HELPER_ISSUE,
                    source_evidence_directory="/candidate/evidence",
                )
        self.assertIs(result, verified)
        poisoned_helper.assert_not_called()

        for function in (
            source._git,
            source._verify_commit_signature,
            source._observe_github,
            source._observe_protected_main,
            source._isolated_source_repository,
            source._implementation_blob,
        ):
            with self.subTest(function=function.__name__):
                implementation = inspect.getsource(function)
                self.assertNotIn("publication._run_git", implementation)
                self.assertNotIn("publication._run_gh", implementation)

    def test_protected_main_policy_uses_only_observed_immutable_registry(self) -> None:
        registry_document = Path(
            ".agents/skills/secpal-pr-review/references/repositories.json"
        ).read_bytes()
        with (
            mock.patch.object(
                source,
                "_observe_protected_main",
                return_value=self._protected_main_observation(),
            ),
            mock.patch.object(
                source,
                "_read_protected_main_registry",
                return_value=registry_document,
            ) as read_registry,
        ):
            trust = source._load_protected_main_trust_policy(REPOSITORY)
        read_registry.assert_called_once_with(PROTECTED_MAIN_HEAD)
        admission = next(
            item
            for item in trust.bootstrap_source_admissions
            if item.subtype == EVIDENCE_HELPER_SUBTYPE
        )
        self.assertEqual(admission.implementation_blob_oid, EVIDENCE_HELPER_BLOB)
        self.assertEqual(
            set(inspect.signature(source._load_protected_main_trust_policy).parameters),
            {"repository"},
        )
        self.assertEqual(
            set(inspect.signature(source._read_protected_main_registry).parameters),
            {"main_oid"},
        )

    def test_protected_main_admission_absence_and_malformed_registry_fail_closed(self) -> None:
        for registry_document, message in (
            (self._protected_main_registry(), "not uniquely maintained"),
            (b"{}", "registry is invalid"),
        ):
            with (
                self.subTest(message=message),
                mock.patch.object(
                    source,
                    "_observe_protected_main",
                    return_value=self._protected_main_observation(),
                ),
                mock.patch.object(
                    source,
                    "_read_protected_main_registry",
                    return_value=registry_document,
                ),
                self.assertRaisesRegex(
                    source.BootstrapSourceAdmissionError, message
                ),
            ):
                source._select_evidence_helper_policy(
                    REPOSITORY, EVIDENCE_HELPER_ISSUE
                )

    def test_protected_main_read_requires_exact_object_and_registry_blob(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            remote = Path(directory) / "remote"
            remote.mkdir()
            subprocess.run(["git", "init", "--quiet", str(remote)], check=True)
            registry = remote / source.PROTECTED_MAIN_REGISTRY_PATH
            registry.parent.mkdir(parents=True)
            registry.write_bytes(
                Path(
                    ".agents/skills/secpal-pr-review/references/repositories.json"
                ).read_bytes()
            )
            subprocess.run(["git", "-C", str(remote), "add", "."], check=True)
            subprocess.run(
                [
                    "git", "-C", str(remote),
                    "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test",
                    "commit", "--quiet", "-m", "fixture",
                ],
                check=True,
            )
            head = subprocess.check_output(
                ["git", "-C", str(remote), "rev-parse", "HEAD"], text=True
            ).strip()
            with mock.patch.object(
                source, "PROTECTED_MAIN_REMOTE_URL", str(remote)
            ):
                self.assertEqual(
                    source._read_protected_main_registry(head),
                    registry.read_bytes(),
                )
                with self.assertRaises(source.BootstrapSourceAdmissionError):
                    source._read_protected_main_registry("f" * 40)
            registry.unlink()
            subprocess.run(["git", "-C", str(remote), "add", "-u"], check=True)
            subprocess.run(
                [
                    "git", "-C", str(remote),
                    "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test",
                    "commit", "--quiet", "-m", "missing registry",
                ],
                check=True,
            )
            missing = subprocess.check_output(
                ["git", "-C", str(remote), "rev-parse", "HEAD"], text=True
            ).strip()
            with (
                mock.patch.object(source, "PROTECTED_MAIN_REMOTE_URL", str(remote)),
                self.assertRaisesRegex(
                    source.BootstrapSourceAdmissionError, "registry is unavailable"
                ),
            ):
                source._read_protected_main_registry(missing)

    def test_exact_byte_source_authenticates_without_execution_authority(self) -> None:
        verified = self._authenticate()
        self.assertTrue(source.is_verified_bootstrap_source(verified))
        self.assertEqual(verified.implementation_blob_oid, EVIDENCE_HELPER_BLOB)
        self.assertEqual(verified.policy_source, source.ACCEPTED_MAIN_POLICY_SOURCE)
        self.assertIsNone(verified.entrypoint)

        parameters = inspect.signature(
            source.verify_pr_review_evidence_helper_source
        ).parameters
        self.assertEqual(
            set(parameters),
            {"repository", "delivery_issue", "source_evidence_directory"},
        )
        for forbidden in (
            "policy", "registry", "subtype", "purpose", "path", "blob",
            "signer", "entrypoint", "command", "authorization",
            "main_oid", "accepted_main_oid", "registry_bytes", "policy_source",
        ):
            self.assertNotIn(forbidden, parameters)
        self.assertFalse(
            hasattr(source, "execute_pr_review_evidence_helper_source")
        )

    def test_exact_github_source_facts_and_verification_are_closed(self) -> None:
        facts = source.GitHubSourceFacts(
            base_repository=REPOSITORY,
            base_ref="main",
            head_repository=REPOSITORY,
            pull_request=EVIDENCE_HELPER_PR,
            state="OPEN",
            draft=False,
            head_sha=EVIDENCE_HELPER_HEAD,
            commit_sha=EVIDENCE_HELPER_HEAD,
            tree_sha=EVIDENCE_HELPER_TREE,
            parent_shas=(EVIDENCE_HELPER_PARENT,),
            github_verified=True,
            github_verification_reason="valid",
        )
        source._admit_github_source(facts, self.policy)
        mutations = (
            {"base_repository": "Other/repo"},
            {"base_ref": "release"},
            {"head_repository": "Other/repo"},
            {"pull_request": 820},
            {"state": "CLOSED"},
            {"draft": True},
            {"commit_sha": "4" * 40},
            {"tree_sha": "5" * 40},
            {"parent_shas": ("6" * 40,)},
            {"github_verified": False},
            {"github_verification_reason": "unsigned"},
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation), self.assertRaises(
                source.BootstrapSourceAdmissionError
            ):
                source._admit_github_source(replace(facts, **mutation), self.policy)

    def test_lawfully_advanced_pr_retains_immutable_byte_source_admission(self) -> None:
        facts = source.GitHubSourceFacts(
            base_repository=REPOSITORY,
            base_ref="main",
            head_repository=REPOSITORY,
            pull_request=EVIDENCE_HELPER_PR,
            state="OPEN",
            draft=False,
            head_sha=EVIDENCE_HELPER_CURRENT_HEAD,
            commit_sha=EVIDENCE_HELPER_HEAD,
            tree_sha=EVIDENCE_HELPER_TREE,
            parent_shas=(EVIDENCE_HELPER_PARENT,),
            github_verified=True,
            github_verification_reason="valid",
        )

        source._admit_github_source(facts, self.policy)

    def test_current_candidate_blob_is_authenticated_at_later_pr_head(self) -> None:
        pull = {
            "number": EVIDENCE_HELPER_PR,
            "state": "open",
            "draft": False,
            "base": {"ref": "main", "repo": {"full_name": REPOSITORY}},
            "head": {
                "repo": {"full_name": REPOSITORY},
                "sha": EVIDENCE_HELPER_CURRENT_HEAD,
            },
        }
        commit = {
            "sha": EVIDENCE_HELPER_HEAD,
            "parents": [{"sha": EVIDENCE_HELPER_PARENT}],
            "commit": {
                "tree": {"sha": EVIDENCE_HELPER_TREE},
                "verification": {"verified": True, "reason": "valid"},
            },
        }
        candidate_blob = {
            "data": {
                "repository": {
                    "nameWithOwner": REPOSITORY,
                    "pullRequest": {
                        "number": EVIDENCE_HELPER_PR,
                        "headRefOid": EVIDENCE_HELPER_CURRENT_HEAD,
                    },
                    "object": {"oid": EVIDENCE_HELPER_BLOB},
                }
            }
        }
        results = [
            subprocess.CompletedProcess(
                [], 0, json.dumps(value).encode("utf-8"), b""
            )
            for value in (pull, commit, candidate_blob)
        ]

        with mock.patch.object(
            source, "_run_bootstrap_gh", side_effect=results
        ) as run_gh:
            source._authenticate_live_github_source(self.policy)

        self.assertEqual(run_gh.call_count, 3)
        candidate_call = run_gh.call_args.args[0]
        self.assertIn(
            EVIDENCE_HELPER_CURRENT_HEAD,
            candidate_call[-1],
        )
        self.assertTrue(
            candidate_call[-1].endswith(f":{EVIDENCE_HELPER_PATH}")
        )

    def test_current_candidate_head_drift_during_blob_read_fails_closed(self) -> None:
        raw = json.dumps(
            {
                "data": {
                    "repository": {
                        "nameWithOwner": REPOSITORY,
                        "pullRequest": {
                            "number": EVIDENCE_HELPER_PR,
                            "headRefOid": "7" * 40,
                        },
                        "object": {"oid": EVIDENCE_HELPER_BLOB},
                    }
                }
            }
        ).encode("utf-8")
        current_head, blob = source._normalize_current_candidate_blob(
            raw, REPOSITORY, EVIDENCE_HELPER_PR
        )

        with self.assertRaisesRegex(
            source.BootstrapSourceAdmissionError,
            "current candidate head or helper bytes differ",
        ):
            source._admit_current_candidate_blob(
                current_head,
                EVIDENCE_HELPER_CURRENT_HEAD,
                blob,
                self.policy,
            )

    def test_live_old_candidate_helper_fails_under_successor_admission(self) -> None:
        raw = json.dumps(
            {
                "data": {
                    "repository": {
                        "nameWithOwner": REPOSITORY,
                        "pullRequest": {
                            "number": EVIDENCE_HELPER_PR,
                            "headRefOid": EVIDENCE_HELPER_CURRENT_HEAD,
                        },
                        "object": {"oid": EVIDENCE_HELPER_OLD_BLOB},
                    }
                }
            }
        ).encode("utf-8")
        current_head, blob = source._normalize_current_candidate_blob(
            raw, REPOSITORY, EVIDENCE_HELPER_PR
        )

        with self.assertRaisesRegex(
            source.BootstrapSourceAdmissionError,
            "current candidate head or helper bytes differ",
        ):
            source._admit_current_candidate_blob(
                current_head,
                EVIDENCE_HELPER_CURRENT_HEAD,
                blob,
                self.policy,
            )

    def test_current_candidate_blob_representation_fails_closed(self) -> None:
        cases = (
            {},
            {"data": {"repository": None}},
            {
                "data": {
                    "repository": {
                        "nameWithOwner": "Other/repo",
                        "pullRequest": {
                            "number": EVIDENCE_HELPER_PR,
                            "headRefOid": EVIDENCE_HELPER_CURRENT_HEAD,
                        },
                        "object": {"oid": EVIDENCE_HELPER_BLOB},
                    }
                }
            },
            {
                "data": {
                    "repository": {
                        "nameWithOwner": REPOSITORY,
                        "pullRequest": {
                            "number": EVIDENCE_HELPER_PR,
                            "headRefOid": EVIDENCE_HELPER_CURRENT_HEAD,
                        },
                        "object": None,
                    }
                }
            },
            {
                "data": {
                    "repository": {
                        "nameWithOwner": REPOSITORY,
                        "pullRequest": {
                            "number": EVIDENCE_HELPER_PR,
                            "headRefOid": EVIDENCE_HELPER_CURRENT_HEAD,
                        },
                        "object": {
                            "oid": EVIDENCE_HELPER_BLOB,
                            "unexpected": True,
                        },
                    }
                }
            },
        )
        for document in cases:
            with self.subTest(document=document), self.assertRaises(
                source.BootstrapSourceAdmissionError
            ):
                source._normalize_current_candidate_blob(
                    json.dumps(document).encode("utf-8"),
                    REPOSITORY,
                    EVIDENCE_HELPER_PR,
                )

    def test_wrong_pr_head_tree_parent_receipt_and_attestation_fail_closed(self) -> None:
        cases = (
            {"policy": replace(self.policy, pull_request=820)},
            {"observed_head": "3" * 40},
            {"observed_tree": "4" * 40},
            {"observed_parent": "5" * 40},
            {"receipt": {"receipt_digest": "6" * 64}},
            {
                "attestation": {
                    **self.attestation,
                    "attestation_digest": "7" * 64,
                }
            },
        )
        for arguments in cases:
            with self.subTest(arguments=arguments), self.assertRaises(
                source.BootstrapSourceAdmissionError
            ):
                self._authenticate(**arguments)

    def test_helper_change_plus_local_claimed_pin_is_not_authority(self) -> None:
        changed_blob = "9" * 40
        candidate_local_claimed_pin = changed_blob
        record = f"100755 blob {changed_blob}\t{EVIDENCE_HELPER_PATH}\x00"
        with (
            mock.patch.object(source, "_git_text", return_value=record),
            self.assertRaisesRegex(
                source.BootstrapSourceAdmissionError, "accepted-main policy"
            ),
        ):
            source._implementation_blob(Path("/candidate"), self.policy)
        self.assertEqual(candidate_local_claimed_pin, changed_blob)

    def test_candidate_local_recomputed_digest_cannot_nominate_authority(self) -> None:
        registry_path = (
            Path(__file__).resolve().parents[1]
            / ".agents/skills/secpal-pr-review/references/repositories.json"
        )
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        changed = json.loads(json.dumps(registry))
        governance = next(
            item for item in changed["repositories"]
            if item["repository"] == REPOSITORY
        )
        admission = next(
            item
            for item in governance["lifecycle_authority_policy"][
                "bootstrap_source_admissions"
            ]
            if item["subtype"] == EVIDENCE_HELPER_SUBTYPE
        )
        admission.update(
            {
                "delivery_issue": 999,
                "pull_request": 998,
                "source_head_sha": "1" * 40,
                "source_tree_sha": "2" * 40,
                "source_parent_sha": "3" * 40,
                "validation_receipt_digest": "4" * 64,
                "final_attestation_digest": "5" * 64,
                "implementation_blob_oid": "6" * 40,
            }
        )
        admission["admission_digest"] = source.authority.digest_json(
            {
                key: value
                for key, value in admission.items()
                if key != "admission_digest"
            }
        )

        @contextmanager
        def isolated(_trust, _policy):
            yield Path("/candidate")

        with tempfile.TemporaryDirectory() as directory:
            candidate_registry = Path(directory) / "repositories.json"
            candidate_registry.write_text(json.dumps(changed), encoding="utf-8")
            with (
                mock.patch.object(
                    source.authority, "_TRUST_REGISTRY", candidate_registry
                ),
                mock.patch.object(
                    source,
                    "_observe_protected_main",
                    return_value=self._protected_main_observation(),
                ),
                mock.patch.object(
                    source,
                    "_read_protected_main_registry",
                    return_value=self._protected_main_registry(),
                ),
                mock.patch.object(source, "_read_evidence", return_value=({}, {}, {})),
                mock.patch.object(source, "_authenticate_live_github_source"),
                mock.patch.object(source, "_isolated_source_repository", isolated),
                mock.patch.object(
                    source,
                    "_authenticate_materialized_source",
                    return_value=object(),
                ),
                mock.patch.object(source, "_verify_materialized_tree"),
                self.assertRaisesRegex(
                    source.BootstrapSourceAdmissionError,
                    "not uniquely maintained",
                ),
            ):
                source.verify_pr_review_evidence_helper_source(
                    REPOSITORY,
                    999,
                    source_evidence_directory="/candidate/evidence",
                )

    def test_duplicate_active_delivery_admission_is_rejected(self) -> None:
        registry_path = (
            Path(__file__).resolve().parents[1]
            / ".agents/skills/secpal-pr-review/references/repositories.json"
        )
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        governance = next(
            item
            for item in registry["repositories"]
            if item["repository"] == REPOSITORY
        )
        admissions = governance["lifecycle_authority_policy"][
            "bootstrap_source_admissions"
        ]
        exact = next(
            item
            for item in admissions
            if item["subtype"] == EVIDENCE_HELPER_SUBTYPE
        )
        admissions.append(json.loads(json.dumps(exact)))

        with tempfile.TemporaryDirectory() as directory:
            candidate_registry = Path(directory) / "repositories.json"
            candidate_registry.write_text(json.dumps(registry), encoding="utf-8")
            with (
                mock.patch.object(
                    source.authority, "_TRUST_REGISTRY", candidate_registry
                ),
                self.assertRaises(source.authority.LifecycleAuthorityError),
            ):
                source.authority._load_lifecycle_trust_policy(REPOSITORY)

    def test_wrong_path_or_blob_is_rejected_by_byte_admission(self) -> None:
        for policy, record in (
            (
                replace(self.policy, implementation_path="scripts/other.py"),
                f"100755 blob {EVIDENCE_HELPER_BLOB}\tscripts/other.py\x00",
            ),
            (
                self.policy,
                f"100755 blob {'8' * 40}\t{EVIDENCE_HELPER_PATH}\x00",
            ),
        ):
            with (
                self.subTest(policy=policy),
                mock.patch.object(source, "_git_text", return_value=record),
                self.assertRaises(source.BootstrapSourceAdmissionError),
            ):
                source._implementation_blob(Path("/fixture"), policy)

    def test_absent_accepted_main_admission_and_cross_delivery_replay_fail(self) -> None:
        historical_only = replace(
            self.trust,
            bootstrap_source_admissions=tuple(
                item
                for item in self.trust.bootstrap_source_admissions
                if item.subtype == source.ADMISSION_SUBTYPE
            ),
        )
        with (
            mock.patch.object(
                source,
                "_load_protected_main_trust_policy",
                return_value=historical_only,
            ),
            mock.patch.object(source, "_read_evidence") as read_evidence,
            self.assertRaises(source.BootstrapSourceAdmissionError),
        ):
            source.verify_pr_review_evidence_helper_source(
                REPOSITORY,
                EVIDENCE_HELPER_ISSUE,
                source_evidence_directory="/candidate/evidence",
            )
        read_evidence.assert_not_called()
        for repository, issue in (
            ("Other/.github", EVIDENCE_HELPER_ISSUE),
            (REPOSITORY, 810),
            (REPOSITORY, 820),
        ):
            with self.subTest(repository=repository, issue=issue), self.assertRaises(
                source.BootstrapSourceAdmissionError
            ):
                with mock.patch.object(
                    source,
                    "_load_protected_main_trust_policy",
                    return_value=self.trust,
                ):
                    source._select_evidence_helper_policy(repository, issue)

    def test_closed_policy_identity_version_purpose_and_digest_fail_closed(self) -> None:
        registry_path = (
            Path(__file__).resolve().parents[1]
            / ".agents/skills/secpal-pr-review/references/repositories.json"
        )
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        governance = next(
            item
            for item in registry["repositories"]
            if item["repository"] == REPOSITORY
        )
        admissions = governance["lifecycle_authority_policy"][
            "bootstrap_source_admissions"
        ]
        exact = next(
            item
            for item in admissions
            if item["subtype"] == EVIDENCE_HELPER_SUBTYPE
        )
        mutations = (
            ("repository", "Other/repo"),
            ("delivery_issue", 817),
            ("pull_request", 818),
            ("source_head_sha", "1" * 40),
            ("source_tree_sha", "2" * 40),
            ("source_parent_sha", "3" * 40),
            ("validation_receipt_digest", "4" * 64),
            ("final_attestation_digest", "5" * 64),
            ("source_signer_identity", "attacker@example.test"),
            ("implementation_path", "scripts/other.py"),
            ("implementation_blob_oid", "6" * 40),
            ("purpose", "GENERIC_SOURCE_ADMISSION"),
            ("schema_version", "2.0"),
            ("subtype", "GENERIC_SOURCE"),
            ("policy_source", "CANDIDATE_LOCAL_REGISTRY"),
            ("admission_digest", "7" * 64),
        )
        for key, value in mutations:
            with self.subTest(key=key), tempfile.TemporaryDirectory() as directory:
                changed = json.loads(json.dumps(registry))
                changed_governance = next(
                    item
                    for item in changed["repositories"]
                    if item["repository"] == REPOSITORY
                )
                changed_exact = next(
                    item
                    for item in changed_governance["lifecycle_authority_policy"][
                        "bootstrap_source_admissions"
                    ]
                    if item["delivery_issue"] == exact["delivery_issue"]
                )
                changed_exact[key] = value
                candidate_registry = Path(directory) / "repositories.json"
                candidate_registry.write_text(json.dumps(changed), encoding="utf-8")
                with (
                    mock.patch.object(
                        source.authority, "_TRUST_REGISTRY", candidate_registry
                    ),
                    self.assertRaises(source.authority.LifecycleAuthorityError),
                ):
                    source.authority._load_lifecycle_trust_policy(REPOSITORY)

    def test_byte_verifier_never_executes_or_imports_candidate(self) -> None:
        @contextmanager
        def isolated(_trust, _policy):
            yield Path("/fixture")

        verified = self._authenticate()
        with (
            mock.patch.object(
                source,
                "_load_protected_main_trust_policy",
                return_value=self.trust,
            ),
            mock.patch.object(source, "_read_evidence", return_value=({}, {}, {})),
            mock.patch.object(source, "_authenticate_live_github_source"),
            mock.patch.object(source, "_isolated_source_repository", isolated),
            mock.patch.object(
                source, "_authenticate_materialized_source", return_value=verified
            ),
            mock.patch.object(source, "_verify_materialized_tree"),
            mock.patch.object(source, "_execute_entrypoint") as execute,
        ):
            result = source.verify_pr_review_evidence_helper_source(
                REPOSITORY,
                EVIDENCE_HELPER_ISSUE,
                source_evidence_directory="/evidence",
            )
        self.assertIs(result, verified)
        execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
