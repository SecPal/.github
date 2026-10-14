# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Pure validation of explicit evidence-architecture declarations.

The canonical semantics remain in ``docs/evidence-architecture-contract.md``.
This module owns only the closed declaration interface and deterministic hard
projection used by Polyscope and repository preflight callers.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


SCHEMA = "secpal-evidence-architecture/v1"
CONTRACT = "docs/evidence-architecture-contract.md"
WORK_GRAPH_REFERENCE = "docs/work-graph-contract.md"
EVIDENCE_CONTRACT_REFERENCE = CONTRACT
MAX_FACT_LENGTH = 320
MAX_DOCUMENTS = 100
MAX_ITEMS = 500

_OFFICIAL_PREFIX = "https://github.com/SecPal/.github/blob/main/"
_IDENTITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,95}$")
_REPOSITORY = re.compile(r"^[^/\s]+/[^/\s]+$")
_CAPABILITIES = frozenset(
    {
        "deterministic_compute",
        "process",
        "filesystem",
        "network",
        "clock",
        "mutable_external_state",
    }
)
_PURE_CAPABILITIES = frozenset({"deterministic_compute"})
_RESPONSIBILITIES = frozenset({"normalization", "admission"})


class DeclarationError(ValueError):
    """A declaration is unavailable, open-ended, or malformed."""


@dataclass(frozen=True)
class VerifiedAgreementResult:
    """Agreement result constructed by the owner after fresh source execution."""

    proof_id: str
    owner: str
    enforcement: str
    status: str


def _bounded_fact(value: str) -> str:
    if len(value) <= MAX_FACT_LENGTH:
        return value
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    suffix = f"… [sha256:{digest}]"
    return value[: MAX_FACT_LENGTH - len(suffix)] + suffix


def _finding(code: str, rule: str, fact: str, action: str, *, item_index: int | None = None) -> dict[str, Any]:
    finding = {
        "code": code,
        "rule": rule,
        "fact": _bounded_fact(fact),
        "action": action,
        "technically_blocking": True,
        "mechanically_blocking": True,
    }
    if item_index is not None:
        finding["item_index"] = item_index
    return finding


def _closed_mapping(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise DeclarationError(f"{label} has unknown or missing fields")
    return dict(value)


def _identity(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _IDENTITY.fullmatch(value):
        raise DeclarationError(f"{label} is not a bounded semantic identity")
    return value


def _boolean(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise DeclarationError(f"{label} must be boolean")
    return value


def _bounded_sequence(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list) or len(value) > MAX_ITEMS:
        raise DeclarationError(f"{label} is not a bounded list")
    return value


def _optional_identity(value: Any, label: str) -> str | None:
    if value is None:
        return None
    return _identity(value, label)


def _parse_runtime_declaration(value: Any) -> dict[str, Any]:
    item = _closed_mapping(
        value,
        {"delegation", "generic_authorities"},
        "runtime baseline declaration",
    )
    delegation = item["delegation"]
    if delegation not in {"direct", "transitive_work_graph"}:
        raise DeclarationError("runtime baseline delegation is unsupported")
    authorities = _bounded_sequence(
        item["generic_authorities"], "runtime baseline generic authorities"
    )
    if any(
        not isinstance(authority, str) or not 1 <= len(authority) <= 200
        for authority in authorities
    ):
        raise DeclarationError("runtime baseline authority identity is malformed")
    return {
        "delegation": delegation,
        "generic_authorities": tuple(authorities),
    }


def runtime_declaration(document: Any) -> dict[str, Any]:
    """Return the explicit runtime delegation from one closed declaration."""

    if not isinstance(document, Mapping) or "runtime_baseline" not in document:
        raise DeclarationError("runtime baseline declaration is missing")
    return _parse_runtime_declaration(document["runtime_baseline"])


def _parse_proof_results(document: Any) -> dict[str, tuple[str, str, str]]:
    if document is None:
        return {}
    if not isinstance(document, Sequence) or isinstance(document, (str, bytes, Mapping)):
        raise DeclarationError("agreement results are not authenticated")
    results: dict[str, tuple[str, str, str]] = {}
    for index, result in enumerate(_bounded_sequence(list(document), "agreement results")):
        if not isinstance(result, VerifiedAgreementResult):
            raise DeclarationError("agreement result lacks verified authority")
        proof_id = _identity(result.proof_id, f"agreement result {index} id")
        if proof_id in results:
            raise DeclarationError("agreement result identities are duplicated")
        if result.status not in {"passed", "failed", "unavailable"}:
            raise DeclarationError(f"agreement result {proof_id} uses an unsupported state")
        results[proof_id] = (result.owner, result.enforcement, result.status)
    return results


def _parse_declaration(document: Any, index: int) -> dict[str, Any]:
    item = _closed_mapping(
        document,
        {
            "schema",
            "repository",
            "runtime_baseline",
            "external_operations",
            "pure_surfaces",
            "invariant_declarations",
        },
        f"declaration {index}",
    )
    if item["schema"] != SCHEMA:
        raise DeclarationError(f"declaration {index} schema is unsupported")
    repository = item["repository"]
    if not isinstance(repository, str) or not _REPOSITORY.fullmatch(repository):
        raise DeclarationError(f"declaration {index} repository is malformed")
    runtime = _parse_runtime_declaration(item["runtime_baseline"])

    operations: list[dict[str, Any]] = []
    for operation_index, raw in enumerate(
        _bounded_sequence(item["external_operations"], "external operations")
    ):
        operation = _closed_mapping(
            raw,
            {"id", "reachable", "fallible", "trusted", "diagnostic_identity"},
            f"external operation {operation_index}",
        )
        operation_id = _identity(operation["id"], f"external operation {operation_index} id")
        diagnostic = operation["diagnostic_identity"]
        if diagnostic is not None:
            diagnostic = _closed_mapping(
                diagnostic, {"id", "kind"}, f"external operation {operation_id} diagnostic"
            )
            diagnostic = {
                "id": _identity(diagnostic["id"], f"external operation {operation_id} diagnostic id"),
                "kind": _identity(
                    diagnostic["kind"], f"external operation {operation_id} diagnostic kind"
                ),
            }
        operations.append(
            {
                "id": operation_id,
                "reachable": _boolean(operation["reachable"], f"operation {operation_id} reachable"),
                "fallible": _boolean(operation["fallible"], f"operation {operation_id} fallible"),
                "trusted": _boolean(operation["trusted"], f"operation {operation_id} trusted"),
                "diagnostic_identity": diagnostic,
            }
        )

    surfaces: list[dict[str, Any]] = []
    for surface_index, raw in enumerate(
        _bounded_sequence(item["pure_surfaces"], "pure surfaces")
    ):
        surface = _closed_mapping(
            raw,
            {"id", "responsibility", "capabilities", "source"},
            f"pure surface {surface_index}",
        )
        surface_id = _identity(surface["id"], f"pure surface {surface_index} id")
        responsibility = surface["responsibility"]
        if responsibility not in _RESPONSIBILITIES:
            raise DeclarationError(f"pure surface {surface_id} responsibility is unsupported")
        capabilities = _bounded_sequence(
            surface["capabilities"], f"pure surface {surface_id} capabilities"
        )
        if any(
            not isinstance(capability, str) or capability not in _CAPABILITIES
            for capability in capabilities
        ):
            raise DeclarationError(f"pure surface {surface_id} has an unknown capability")
        if len(set(capabilities)) != len(capabilities):
            raise DeclarationError(f"pure surface {surface_id} capabilities are duplicated")
        surfaces.append(
            {
                "id": surface_id,
                "responsibility": responsibility,
                "source": surface["source"],
                "capabilities": tuple(capabilities),
            }
        )

    invariants: list[dict[str, Any]] = []
    for invariant_index, raw in enumerate(
        _bounded_sequence(item["invariant_declarations"], "invariant declarations")
    ):
        if not isinstance(raw, Mapping):
            raise DeclarationError(f"invariant declaration {invariant_index} is malformed")
        role = raw.get("role")
        if role == "owner":
            invariant = _closed_mapping(
                raw, {"id", "invariant", "role", "surface"}, f"invariant declaration {invariant_index}"
            )
            invariants.append(
                {
                    "id": _identity(invariant["id"], f"invariant declaration {invariant_index} id"),
                    "invariant": _identity(
                        invariant["invariant"], f"invariant declaration {invariant_index} invariant"
                    ),
                    "role": role,
                    "surface": _identity(invariant["surface"], "owner surface"),
                }
            )
        elif role == "independent_enforcement":
            invariant = _closed_mapping(
                raw,
                {
                    "id",
                    "invariant",
                    "role",
                    "owner",
                    "derivation",
                    "agreement_proof",
                    "surface",
                },
                f"invariant declaration {invariant_index}",
            )
            invariants.append(
                {
                    "id": _identity(invariant["id"], f"invariant declaration {invariant_index} id"),
                    "invariant": _identity(
                        invariant["invariant"], f"invariant declaration {invariant_index} invariant"
                    ),
                    "role": role,
                    "surface": _identity(invariant["surface"], "independent surface"),
                    "owner": _optional_identity(invariant["owner"], "independent owner"),
                    "derivation": _optional_identity(
                        invariant["derivation"], "independent derivation"
                    ),
                    "agreement_proof": _optional_identity(
                        invariant["agreement_proof"], "independent agreement proof"
                    ),
                }
            )
        else:
            raise DeclarationError(f"invariant declaration {invariant_index} role is unsupported")

    identities = [entry["id"] for entry in (*operations, *surfaces, *invariants)]
    if len(identities) != len(set(identities)):
        raise DeclarationError(f"declaration {repository} identities are duplicated")
    return {
        "repository": repository,
        "runtime_baseline": runtime,
        "external_operations": operations,
        "pure_surfaces": surfaces,
        "invariant_declarations": invariants,
    }


def assess_declarations(
    declarations: Sequence[Any],
    *,
    proof_results: Any = None,
    dispatch_requested: bool = False,
) -> dict[str, Any]:
    """Validate a bounded set of explicit declarations and project hard findings."""

    findings: list[dict[str, Any]] = []
    if not isinstance(declarations, Sequence) or isinstance(declarations, (str, bytes)):
        declarations = ()
        findings.append(
            _finding(
                "MALFORMED_DECLARATION",
                "evidence architecture sections 1, 2, and 4",
                "Declaration set is unavailable or malformed",
                "Provide the closed evidence-architecture declaration schema.",
            )
        )
    if len(declarations) > MAX_DOCUMENTS:
        declarations = ()
        findings.append(
            _finding(
                "MALFORMED_DECLARATION",
                "evidence architecture sections 1, 2, and 4",
                "Declaration set exceeds the bounded document limit",
                "Reduce the declaration set to the managed repository scope.",
            )
        )

    try:
        proofs = _parse_proof_results(proof_results)
        parsed = [_parse_declaration(item, index) for index, item in enumerate(declarations)]
    except (DeclarationError, TypeError, ValueError):
        proofs = {}
        parsed = []
        findings.append(
            _finding(
                "MALFORMED_DECLARATION",
                "evidence architecture sections 1, 2, and 4",
                "Closed declaration validation failed; raw input was not retained",
                "Correct the named closed declaration fields before validation or dispatch.",
            )
        )

    operations = [entry for document in parsed for entry in document["external_operations"]]
    surfaces = [entry for document in parsed for entry in document["pure_surfaces"]]
    invariants = [entry for document in parsed for entry in document["invariant_declarations"]]

    invariant_ids = [entry["id"] for entry in invariants]
    if len(invariant_ids) != len(set(invariant_ids)):
        findings.append(
            _finding(
                "DUPLICATE_INVARIANT_IDENTITY",
                "evidence architecture section 2",
                "Declared invariant identities are ambiguous across the managed scope",
                "Use unique identities so agreement paths bind exactly one declared owner and enforcement.",
            )
        )

    if dispatch_requested and (not parsed or not operations):
        findings.append(
            _finding(
                "DISPATCH_DECLARATION_MISSING",
                "evidence architecture section 4",
                "External dispatch has no complete explicit operation declaration",
                "Declare every reachable fallible trusted operation before dispatch.",
            )
        )

    operation_index = 0
    for document in parsed:
        diagnostic_ids = set()
        for operation in document["external_operations"]:
            if operation["reachable"] and operation["fallible"] and operation["trusted"]:
                diagnostic = operation["diagnostic_identity"]
                if (diagnostic is None or diagnostic["kind"] != "semantic"
                        or diagnostic["id"] in diagnostic_ids):
                    findings.append(
                        _finding(
                            "OPAQUE_TRUSTED_FAILURE_BOUNDARY",
                            "evidence architecture section 4",
                            "Declared operation lacks a unique closed semantic diagnostic identity",
                            "Define a bounded unique identity without raw output or secret material.",
                            item_index=operation_index,
                        )
                    )
                if diagnostic is not None:
                    diagnostic_ids.add(diagnostic["id"])
            operation_index += 1

    for surface_index, surface in enumerate(surfaces):
        forbidden = sorted(set(surface["capabilities"]) - _PURE_CAPABILITIES)
        if forbidden:
            findings.append(
                _finding(
                    "PURE_SURFACE_FORBIDDEN_CAPABILITY",
                    "evidence architecture section 1",
                    "Declared pure surface has forbidden external capabilities",
                    "Remove external capabilities or reclassify the responsibility through architecture review.",
                    item_index=surface_index,
                )
            )

    owners: dict[str, list[str]] = defaultdict(list)
    owner_indices: dict[str, list[int]] = defaultdict(list)
    for invariant_index, invariant in enumerate(invariants):
        if invariant["role"] == "owner":
            owners[invariant["invariant"]].append(invariant["id"])
            owner_indices[invariant["invariant"]].append(invariant_index)
    for invariant_id, owner_ids in sorted(owners.items()):
        if len(owner_ids) > 1:
            findings.append(
                _finding(
                    "DUPLICATE_INVARIANT_OWNER",
                    "evidence architecture section 2",
                    "Declared invariant has multiple explicit owners",
                    "Retain exactly one authoritative declared owner.",
                    item_index=owner_indices[invariant_id][0],
                )
            )

    for invariant_index, invariant in enumerate(invariants):
        if invariant["role"] != "independent_enforcement":
            continue
        expected_owners = owners.get(invariant["invariant"], [])
        owner_valid = len(expected_owners) == 1 and invariant["owner"] == expected_owners[0]
        proof_id = invariant["agreement_proof"]
        proof_valid = proof_id is not None and proofs.get(proof_id) == (invariant["owner"], invariant["id"], "passed")
        if not owner_valid or invariant["derivation"] is None or not proof_valid:
            findings.append(
                _finding(
                    "INDEPENDENT_ENFORCEMENT_UNPROVEN",
                    "evidence architecture section 2",
                    "Independent enforcement lacks matching owner, derivation, or executed agreement proof",
                    "Name the authoritative owner and derivation, then supply passing executable agreement evidence.",
                    item_index=invariant_index,
                )
            )

    return {
        "schema": "secpal-evidence-architecture-assessment/v1",
        "semantics": CONTRACT,
        "status": "blocked" if findings else "pass",
        "dispatch_requested": dispatch_requested,
        "declaration_count": len(parsed),
        "external_operation_count": len(operations),
        "pure_surface_count": len(surfaces),
        "invariant_declaration_count": len(invariants),
        "findings": findings,
        "human_judgment_status": "explicit_review_required",
        "human_judgment_obligations": [
            "undeclared semantic roles",
            "conceptual responsibility and layer boundaries",
            "trust-boundary justification not present in declarations",
        ],
        "claims_complete_architecture_judgment": False,
    }


def _canonical_reference(reference: str) -> str | None:
    normalized = reference.strip()
    if normalized.startswith(_OFFICIAL_PREFIX):
        normalized = normalized[len(_OFFICIAL_PREFIX) :]
    if normalized.startswith("SecPal/.github/"):
        normalized = normalized[len("SecPal/.github/") :]
    if normalized.startswith("./"):
        normalized = normalized[2:]
    if normalized in {WORK_GRAPH_REFERENCE, EVIDENCE_CONTRACT_REFERENCE}:
        return normalized
    return None


def assess_runtime_baseline(
    references: Sequence[str],
    *,
    declared_mode: str | None = None,
    declared_authorities: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Classify explicit Markdown references without interpreting policy prose."""

    if declared_mode not in {None, "direct", "transitive_work_graph"}:
        return {
            "state": "CONTRADICTORY_DELEGATION",
            "findings": [
                _finding(
                    "CONTRADICTORY_RUNTIME_BASELINE_DELEGATION",
                    "evidence architecture status",
                    "Runtime baseline declares an unsupported delegation mode",
                    "Declare direct or supported transitive work-graph delegation.",
                )
            ],
        }
    canonical = {_canonical_reference(reference) for reference in references}
    canonical.discard(None)
    authorities = tuple(declared_authorities or ())
    if len(authorities) > 1:
        state = "DUPLICATE_GENERIC_AUTHORITY"
        findings = [
            _finding(
                "DUPLICATE_GENERIC_EVIDENCE_AUTHORITY",
                "evidence architecture status",
                "Runtime baseline references a second generic evidence-architecture authority",
                "Delegate only to the canonical contract or its supported work-graph incorporation.",
            )
        ]
    elif declared_mode is not None and authorities != (
        EVIDENCE_CONTRACT_REFERENCE
        if declared_mode == "direct"
        else WORK_GRAPH_REFERENCE,
    ):
        state = "CONTRADICTORY_DELEGATION"
        findings = [
            _finding(
                "CONTRADICTORY_RUNTIME_BASELINE_DELEGATION",
                "evidence architecture status",
                "Declared generic authority contradicts the closed delegation mode",
                "Declare exactly the canonical direct or supported transitive authority.",
            )
        ]
    elif EVIDENCE_CONTRACT_REFERENCE in canonical:
        state = "VALID_DIRECT_DELEGATION"
        findings = []
    elif WORK_GRAPH_REFERENCE in canonical:
        state = "VALID_TRANSITIVE_SUPPORTED_DELEGATION"
        findings = []
    else:
        state = "MISSING_DELEGATION"
        findings = [
            _finding(
                "MISSING_RUNTIME_BASELINE_DELEGATION",
                "evidence architecture status",
                "Active runtime baseline has no canonical evidence-architecture delegation",
                "Reference the canonical companion directly or its normative work-graph incorporation.",
            )
        ]

    if declared_mode is not None and not findings:
        observed = {
            "direct": EVIDENCE_CONTRACT_REFERENCE in canonical,
            "transitive_work_graph": WORK_GRAPH_REFERENCE in canonical,
        }[declared_mode]
        if not observed:
            state = "CONTRADICTORY_DELEGATION"
            findings = [
                _finding(
                    "CONTRADICTORY_RUNTIME_BASELINE_DELEGATION",
                    "evidence architecture status",
                    "Declared delegation mode contradicts the structured canonical reference",
                    "Make the declaration and active runtime baseline reference agree.",
                )
            ]
    return {"state": state, "findings": findings}
