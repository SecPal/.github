#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
"""Regression coverage for policy-selected local lifecycle credentials."""

from __future__ import annotations

import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest import TestCase, main, mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.secpal_pr_review import lifecycle_authority as authority
from scripts.secpal_pr_review import lifecycle_execution as execution


REPOSITORY = "SecPal/.github"
ROUTINE = "routine@secpal.app"
LEGACY_ADOPTION = "legacy-adoption@secpal.app"
DOMAIN = "secpal-role-signing-regression-v1"


def generate_ssh_credential(path: Path) -> str:
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(path)],
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    algorithm, encoded, *_comment = Path(f"{path}.pub").read_text(
        encoding="utf-8"
    ).split()
    return f"{algorithm} {encoded}"


class RoleSpecificLifecycleSigningTests(TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory(prefix="secpal-role-signing-")
        self.addCleanup(self.directory.cleanup)
        self.home = Path(self.directory.name)
        self.routine_key = self.home / "routine"
        self.legacy_key = self.home / "legacy"
        routine_public = generate_ssh_credential(self.routine_key)
        legacy_public = generate_ssh_credential(self.legacy_key)
        self.environment = execution.late_disposition.signing_environment(
            account_home=self.home
        )
        self.git_config("gpg.format", "ssh")
        self.git_config("user.signingkey", str(self.routine_key))
        self.policy = authority.LifecycleTrustPolicy(
            repository=REPOSITORY,
            accepted_formats=frozenset({"ssh"}),
            transition_signer_identities=frozenset({ROUTINE}),
            authority_signer_identities=frozenset({ROUTINE}),
            publication_signer_identities=frozenset({ROUTINE}),
            genesis_admission_signer_identities=frozenset({ROUTINE}),
            legacy_adoption_signer_identities=frozenset({LEGACY_ADOPTION}),
            signers={
                ROUTINE: authority.TrustedSigner(ROUTINE, (routine_public,), ()),
                LEGACY_ADOPTION: authority.TrustedSigner(
                    LEGACY_ADOPTION, (legacy_public,), ()
                ),
            },
            initialization_anchors=(),
        )

    def git_config(self, key: str, value: str, *, add: bool = False) -> None:
        arguments = ["git", "config", "--global"]
        if add:
            arguments.append("--add")
        arguments.extend((key, value))
        subprocess.run(arguments, check=True, env=self.environment)

    def add_mapping(self, identity: str, credential: str) -> None:
        self.git_config(
            execution.late_disposition.ROLE_CREDENTIAL_CONFIG_KEY,
            json.dumps(
                {"identity": identity, "credential": credential},
                separators=(",", ":"),
                sort_keys=True,
            ),
            add=True,
        )

    def policy_context(self):
        return (
            mock.patch.object(
                execution.authority,
                "_load_lifecycle_trust_policy",
                return_value=self.policy,
            ),
            mock.patch.object(
                execution.late_disposition,
                "os_account_home",
                return_value=self.home,
            ),
        )

    def legacy_signer(self) -> tuple[str, authority.Signer]:
        policy_patch, home_patch = self.policy_context()
        with policy_patch, home_patch:
            return execution._production_legacy_adoption_signer(REPOSITORY)

    def verify(
        self, signer: authority.Signer, identity: str, payload: bytes = b"payload\n"
    ) -> authority.VerifiedSignature:
        signature = signer(payload, DOMAIN)
        return authority._policy_signature_verifier(self.policy)(
            payload, signature, identity, DOMAIN
        )

    def test_routine_role_preserves_compatible_global_default(self) -> None:
        policy_patch, home_patch = self.policy_context()
        with policy_patch, home_patch:
            signers = execution._production_signing_authorities(REPOSITORY, ROUTINE)
        self.assertEqual(
            self.verify(signers.transition_signer, ROUTINE).signer_identity,
            ROUTINE,
        )
        self.assertEqual(signers.authority_identity, ROUTINE)
        self.assertEqual(signers.publication_identity, ROUTINE)

    def test_legacy_role_selects_distinct_explicit_credential(self) -> None:
        self.add_mapping(LEGACY_ADOPTION, str(self.legacy_key))
        identity, signer = self.legacy_signer()
        self.assertEqual(identity, LEGACY_ADOPTION)
        self.assertEqual(self.verify(signer, identity).signer_identity, identity)

    def test_global_routine_default_cannot_override_distinct_mapping(self) -> None:
        self.add_mapping(LEGACY_ADOPTION, str(self.legacy_key))
        _identity, signer = self.legacy_signer()
        signature = signer(b"credential precedence\n", DOMAIN)
        with self.assertRaises(authority.LifecycleAuthorityError):
            authority._policy_signature_verifier(self.policy)(
                b"credential precedence\n", signature, ROUTINE, DOMAIN
            )

    def test_wrong_distinct_credential_fails_cryptographic_policy_match(self) -> None:
        self.add_mapping(LEGACY_ADOPTION, str(self.routine_key))
        _identity, signer = self.legacy_signer()
        with self.assertRaisesRegex(
            execution.LifecycleExecutionError, "does not match accepted policy identity"
        ):
            signer(b"wrong credential\n", DOMAIN)

    def test_missing_distinct_mapping_fails_closed(self) -> None:
        with self.assertRaisesRegex(
            execution.LifecycleExecutionError, "role credential mapping is missing"
        ):
            self.legacy_signer()

    def test_duplicate_and_malformed_mappings_fail_closed(self) -> None:
        cases = (
            ("duplicate", [
                {"identity": LEGACY_ADOPTION, "credential": str(self.legacy_key)},
                {"identity": LEGACY_ADOPTION, "credential": str(self.legacy_key)},
            ]),
            ("empty", [{"identity": LEGACY_ADOPTION, "credential": ""}]),
            ("relative", [{"identity": LEGACY_ADOPTION, "credential": "legacy"}]),
        )
        for label, mappings in cases:
            with self.subTest(label=label):
                subprocess.run(
                    [
                        "git", "config", "--global", "--unset-all",
                        execution.late_disposition.ROLE_CREDENTIAL_CONFIG_KEY,
                    ],
                    check=False,
                    env=self.environment,
                )
                for mapping in mappings:
                    self.git_config(
                        execution.late_disposition.ROLE_CREDENTIAL_CONFIG_KEY,
                        json.dumps(mapping),
                        add=True,
                    )
                with self.assertRaises(execution.LifecycleExecutionError):
                    self.legacy_signer()

    def test_unsupported_format_fails_closed(self) -> None:
        self.git_config("gpg.format", "x509")
        self.add_mapping(LEGACY_ADOPTION, str(self.legacy_key))
        with self.assertRaisesRegex(
            execution.LifecycleExecutionError, "signing format is unsupported"
        ):
            self.legacy_signer()

    def test_nul_containing_mapping_fails_closed(self) -> None:
        raw = json.dumps(
            {"identity": LEGACY_ADOPTION, "credential": "/credential\x00suffix"}
        )
        policy_patch, home_patch = self.policy_context()
        with policy_patch, home_patch, mock.patch.object(
            execution.late_disposition,
            "_read_global_git_values",
            return_value=(raw,),
        ), self.assertRaisesRegex(
            execution.LifecycleExecutionError, "mapping is malformed"
        ):
            execution._production_legacy_adoption_signer(REPOSITORY)

    def test_policy_role_must_select_exactly_one_identity(self) -> None:
        self.policy = authority.LifecycleTrustPolicy(
            **{
                **self.policy.__dict__,
                "legacy_adoption_signer_identities": frozenset(
                    {LEGACY_ADOPTION, ROUTINE}
                ),
            }
        )
        self.add_mapping(LEGACY_ADOPTION, str(self.legacy_key))
        with self.assertRaisesRegex(
            execution.LifecycleExecutionError,
            "not one closed maintained signer",
        ):
            self.legacy_signer()

    def test_unusable_noninteractive_credential_fails_closed(self) -> None:
        self.add_mapping(LEGACY_ADOPTION, str(self.home / "missing"))
        _identity, signer = self.legacy_signer()
        with self.assertRaisesRegex(
            execution.LifecycleExecutionError, "credential is unusable"
        ):
            signer(b"unusable credential\n", DOMAIN)

    def test_production_bridge_accepts_no_identity_or_key_path(self) -> None:
        self.assertEqual(
            list(
                inspect.signature(
                    execution._production_legacy_adoption_signer
                ).parameters
            ),
            ["repository"],
        )

    def test_signing_does_not_mutate_global_config_or_require_ssh_agent(self) -> None:
        self.add_mapping(LEGACY_ADOPTION, str(self.legacy_key))
        before = (self.home / ".gitconfig").read_bytes()
        with mock.patch.dict(
            os.environ,
            {"SSH_AUTH_SOCK": "/hostile/agent", "SSH_ASKPASS": "/hostile/askpass"},
        ):
            identity, signer = self.legacy_signer()
            self.verify(signer, identity)
            closed = execution.late_disposition.signing_environment(
                account_home=self.home
            )
        self.assertEqual((self.home / ".gitconfig").read_bytes(), before)
        self.assertNotIn("SSH_AUTH_SOCK", closed)
        self.assertNotIn("SSH_ASKPASS", closed)

    def test_private_credential_content_is_never_returned(self) -> None:
        self.add_mapping(LEGACY_ADOPTION, str(self.legacy_key))
        private = self.legacy_key.read_text(encoding="utf-8")
        identity, signer = self.legacy_signer()
        serialized = json.dumps(signer(b"secret confinement\n", DOMAIN))
        self.assertNotIn(private, serialized)
        self.assertEqual(identity, LEGACY_ADOPTION)

    def test_exact_adoption_v2_constructors_receive_production_legacy_signer(
        self,
    ) -> None:
        self.add_mapping(LEGACY_ADOPTION, str(self.legacy_key))
        identity, signer = self.legacy_signer()
        state = authority.initial_state()
        state.update(unrestricted_review_count=1, remediation_cycle_count=1)
        history = [
            {
                "sequence": 1, "kind": "PR_CREATED_DRAFT",
                "observed_at": "2026-09-01T00:00:00Z", "head_sha": "a" * 40,
                "reviewed_head_sha": None,
            },
            {
                "sequence": 2, "kind": "REMEDIATION_HEAD_OBSERVED",
                "observed_at": "2026-09-02T00:00:00Z", "head_sha": "b" * 40,
                "reviewed_head_sha": None,
            },
        ]
        admission = authority.create_pre_enrollment_review_budget_consumption_admission(
            admission_id="role-signing-admission", repository=REPOSITORY,
            delivery_issue=836, pull_request=900, head_sha="b" * 40,
            tree_sha="c" * 40, pull_request_state="OPEN",
            commit_signature_evidence_digest="1" * 64,
            validation_receipt_digest="2" * 64,
            source_validation_evidence_digest="3" * 64,
            adoption_source_evidence_digest="4" * 64,
            observed_pre_enrollment_history=history, intended_state=state,
            adoption_timestamp="2026-09-03T00:00:00Z",
            signer_identity=identity, signer=signer,
        )
        evidence = {
            "schema_version": authority.EXACT_ADOPTION_CONSUMPTION_VERSION,
            "kind": authority.EXACT_ADOPTION_EVIDENCE_KIND,
            "domain": authority.EXACT_ADOPTION_CONSUMPTION_EVIDENCE_DOMAIN,
            "proof_version": authority.EXACT_ADOPTION_CONSUMPTION_VERSION,
            "repository": REPOSITORY, "delivery_issue": 836, "pull_request": 900,
            "head_sha": "b" * 40, "tree_sha": "c" * 40,
            "adoption_evidence_digest": "5" * 64,
            "intended_state_digest": "6" * 64,
        }
        with mock.patch.object(
            authority, "_verify_exact_state_adoption_evidence", return_value=evidence
        ):
            authorization = authority.create_exact_state_adoption_authorization(
                adoption_evidence=evidence,
                authorization_id="role-signing-authorization", bounded_uses=1,
                signer_identity=identity, signer=signer,
            )
            proof = authority.create_exact_state_adoption_proof(
                adoption_evidence=evidence, authorization=authorization,
                signer_identity=identity, signer=signer,
            )
        self.assertEqual(admission["signer_identity"], LEGACY_ADOPTION)
        self.assertEqual(authorization["signer_identity"], LEGACY_ADOPTION)
        self.assertEqual(proof["signer_identity"], LEGACY_ADOPTION)


if __name__ == "__main__":
    main()
