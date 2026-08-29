#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Behavior evidence for the #736 evidence-architecture hard boundary."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from secpal_evidence_architecture import governance  # noqa: E402


def declaration() -> dict:
    return {
        "schema": "secpal-evidence-architecture/v1",
        "repository": "SecPal/deployment",
        "runtime_baseline": {
            "delegation": "direct",
            "generic_authorities": ["docs/evidence-architecture-contract.md"],
        },
        "external_operations": [
            {
                "id": "provider.create-host",
                "reachable": True,
                "fallible": True,
                "trusted": True,
                "diagnostic_identity": {
                    "id": "provider.create-host.failed",
                    "kind": "semantic",
                },
            }
        ],
        "pure_surfaces": [
            {
                "id": "host.normalize",
                "responsibility": "normalization",
                "capabilities": ["deterministic_compute"],
            }
        ],
        "invariant_declarations": [
            {
                "id": "host.digest.owner",
                "invariant": "host.digest",
                "role": "owner",
            },
            {
                "id": "host.digest.edge",
                "invariant": "host.digest",
                "role": "independent_enforcement",
                "owner": "host.digest.owner",
                "derivation": "normalized_digest_agreement",
                "agreement_proof": "host-digest-agreement",
            },
        ],
    }


def proof_results(status: str = "passed") -> dict:
    return {
        "schema": "secpal-evidence-agreement-results/v1",
        "results": [
            {
                "id": "host-digest-agreement",
                "kind": "executable",
                "status": status,
            }
        ],
    }


def finding_codes(report: dict) -> set[str]:
    return {finding["code"] for finding in report["findings"]}


class DispatchDiagnosticTests(unittest.TestCase):
    def test_reachable_fallible_trusted_operation_with_semantic_identity_passes(self):
        report = governance.assess_declarations(
            [declaration()], proof_results=proof_results(), dispatch_requested=True
        )

        self.assertEqual(report["findings"], [])
        self.assertEqual(report["status"], "pass")

    def test_missing_diagnostic_identity_refuses_dispatch(self):
        mutated = declaration()
        mutated["external_operations"][0]["diagnostic_identity"] = None

        report = governance.assess_declarations(
            [mutated], proof_results=proof_results(), dispatch_requested=True
        )

        self.assertIn("OPAQUE_TRUSTED_FAILURE_BOUNDARY", finding_codes(report))
        finding = next(
            item
            for item in report["findings"]
            if item["code"] == "OPAQUE_TRUSTED_FAILURE_BOUNDARY"
        )
        self.assertEqual(finding["rule"], "evidence architecture section 4")
        self.assertTrue(finding["mechanically_blocking"])

    def test_raw_provider_output_is_not_a_diagnostic_identity(self):
        for kind in ("raw_output", "provider_response", "secret_material"):
            with self.subTest(kind=kind):
                mutated = declaration()
                mutated["external_operations"][0]["diagnostic_identity"]["kind"] = kind
                report = governance.assess_declarations(
                    [mutated], proof_results=proof_results(), dispatch_requested=True
                )
                self.assertIn("OPAQUE_TRUSTED_FAILURE_BOUNDARY", finding_codes(report))

    def test_unreachable_or_nonfallible_operation_is_not_falsely_rejected(self):
        for field in ("reachable", "fallible", "trusted"):
            with self.subTest(field=field):
                mutated = declaration()
                mutated["external_operations"][0][field] = False
                mutated["external_operations"][0]["diagnostic_identity"] = None
                report = governance.assess_declarations(
                    [mutated], proof_results=proof_results(), dispatch_requested=True
                )
                self.assertNotIn("OPAQUE_TRUSTED_FAILURE_BOUNDARY", finding_codes(report))

    def test_dispatch_without_a_declaration_fails_closed(self):
        report = governance.assess_declarations([], dispatch_requested=True)
        self.assertIn("DISPATCH_DECLARATION_MISSING", finding_codes(report))

    def test_oversized_identity_is_bounded_without_losing_rule_identity(self):
        mutated = declaration()
        mutated["external_operations"][0]["id"] = "x" * 10000
        report = governance.assess_declarations(
            [mutated], proof_results=proof_results(), dispatch_requested=True
        )

        finding = report["findings"][0]
        self.assertEqual(finding["code"], "MALFORMED_DECLARATION")
        self.assertLessEqual(len(finding["fact"]), governance.MAX_FACT_LENGTH)
        self.assertNotIn("x" * 100, finding["fact"])


class PureSurfaceCapabilityTests(unittest.TestCase):
    def test_each_forbidden_capability_is_live(self):
        for capability in (
            "process",
            "filesystem",
            "network",
            "clock",
            "mutable_external_state",
        ):
            with self.subTest(capability=capability):
                mutated = declaration()
                mutated["pure_surfaces"][0]["capabilities"] = [capability]
                report = governance.assess_declarations(
                    [mutated], proof_results=proof_results()
                )
                self.assertIn("PURE_SURFACE_FORBIDDEN_CAPABILITY", finding_codes(report))

    def test_closed_allowed_capability_set_passes(self):
        report = governance.assess_declarations(
            [declaration()], proof_results=proof_results()
        )
        self.assertNotIn("PURE_SURFACE_FORBIDDEN_CAPABILITY", finding_codes(report))

    def test_unknown_capability_fails_closed(self):
        for capability in ("future_ambient_access", {"untrusted": "shape"}):
            with self.subTest(capability=capability):
                mutated = declaration()
                mutated["pure_surfaces"][0]["capabilities"] = [capability]
                report = governance.assess_declarations(
                    [mutated], proof_results=proof_results()
                )
                self.assertIn("MALFORMED_DECLARATION", finding_codes(report))

    def test_undeclared_source_shape_is_not_classified(self):
        empty = declaration()
        empty["pure_surfaces"] = []
        report = governance.assess_declarations([empty], proof_results=proof_results())
        self.assertEqual(report["pure_surface_count"], 0)
        self.assertEqual(report["human_judgment_status"], "explicit_review_required")


class RuntimeBaselineDelegationTests(unittest.TestCase):
    def test_direct_and_supported_transitive_delegation_are_distinct_valid_states(self):
        direct = governance.assess_runtime_baseline(
            (governance.EVIDENCE_CONTRACT_REFERENCE, governance.WORK_GRAPH_REFERENCE)
        )
        transitive = governance.assess_runtime_baseline(
            (governance.WORK_GRAPH_REFERENCE,)
        )

        self.assertEqual(direct["state"], "VALID_DIRECT_DELEGATION")
        self.assertEqual(transitive["state"], "VALID_TRANSITIVE_SUPPORTED_DELEGATION")

        repository_qualified = governance.assess_runtime_baseline(
            ("SecPal/.github/docs/work-graph-contract.md",)
        )
        self.assertEqual(
            repository_qualified["state"],
            "VALID_TRANSITIVE_SUPPORTED_DELEGATION",
        )

    def test_missing_delegation_fails(self):
        report = governance.assess_runtime_baseline(())
        self.assertEqual(report["state"], "MISSING_DELEGATION")
        self.assertTrue(report["findings"])

    def test_declared_mode_contradicting_observed_reference_fails(self):
        report = governance.assess_runtime_baseline(
            (governance.WORK_GRAPH_REFERENCE,), declared_mode="direct"
        )
        self.assertEqual(report["state"], "CONTRADICTORY_DELEGATION")

    def test_second_generic_evidence_authority_fails(self):
        report = governance.assess_runtime_baseline(
            (governance.WORK_GRAPH_REFERENCE,),
            declared_mode="transitive_work_graph",
            declared_authorities=(
                governance.WORK_GRAPH_REFERENCE,
                "docs/local/evidence-architecture-contract.md",
            ),
        )
        self.assertEqual(report["state"], "DUPLICATE_GENERIC_AUTHORITY")

    def test_similarly_named_undeclared_link_is_not_inferred_as_authority(self):
        report = governance.assess_runtime_baseline(
            (
                governance.WORK_GRAPH_REFERENCE,
                "docs/local/evidence-architecture-contract.md",
            )
        )
        self.assertEqual(
            report["state"], "VALID_TRANSITIVE_SUPPORTED_DELEGATION"
        )


class InvariantOwnershipTests(unittest.TestCase):
    def test_exactly_one_owner_and_passing_independent_enforcement_pass(self):
        report = governance.assess_declarations(
            [declaration()], proof_results=proof_results()
        )
        self.assertEqual(report["findings"], [])

    def test_duplicate_explicit_owner_fails(self):
        mutated = declaration()
        duplicate = copy.deepcopy(mutated["invariant_declarations"][0])
        duplicate["id"] = "host.digest.other-owner"
        mutated["invariant_declarations"].append(duplicate)

        report = governance.assess_declarations([mutated], proof_results=proof_results())
        self.assertIn("DUPLICATE_INVARIANT_OWNER", finding_codes(report))

    def test_independent_enforcement_requires_owner_derivation_and_proof(self):
        mutations = {
            "owner": None,
            "derivation": None,
            "agreement_proof": None,
        }
        for field, value in mutations.items():
            with self.subTest(field=field):
                mutated = declaration()
                mutated["invariant_declarations"][1][field] = value
                report = governance.assess_declarations(
                    [mutated], proof_results=proof_results()
                )
                self.assertIn("INDEPENDENT_ENFORCEMENT_UNPROVEN", finding_codes(report))

    def test_broken_executable_agreement_proof_fails(self):
        report = governance.assess_declarations(
            [declaration()], proof_results=proof_results("failed")
        )
        self.assertIn("INDEPENDENT_ENFORCEMENT_UNPROVEN", finding_codes(report))

    def test_malformed_agreement_result_fails_closed(self):
        malformed = proof_results()
        malformed["results"][0]["status"] = ["passed"]
        report = governance.assess_declarations(
            [declaration()], proof_results=malformed
        )
        self.assertIn("MALFORMED_DECLARATION", finding_codes(report))

    def test_similar_implementation_without_declaration_is_not_inferred(self):
        empty = declaration()
        empty["invariant_declarations"] = []
        report = governance.assess_declarations([empty])
        self.assertEqual(report["invariant_declaration_count"], 0)
        self.assertNotIn("DUPLICATE_INVARIANT_OWNER", finding_codes(report))


class HumanJudgmentBoundaryTests(unittest.TestCase):
    def test_machine_report_keeps_architecture_judgment_explicit(self):
        report = governance.assess_declarations(
            [declaration()], proof_results=proof_results()
        )

        self.assertEqual(report["human_judgment_status"], "explicit_review_required")
        self.assertIn("undeclared semantic roles", report["human_judgment_obligations"])
        self.assertFalse(report["claims_complete_architecture_judgment"])


if __name__ == "__main__":
    unittest.main()
