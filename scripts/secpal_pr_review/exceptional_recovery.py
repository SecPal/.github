# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Diagnostic admission within the existing one-use Exceptional Recovery family."""

from __future__ import annotations

import ast
import copy
import hashlib
import io
from pathlib import Path
import tempfile
import tokenize
from typing import Any

from . import bootstrap_source_admission as transport
from . import lifecycle_authority as authority


ADMISSION_KIND = "REPRODUCED_MATERIAL_SECURITY_DIAGNOSTIC"
PROFILE = "python-version-token-encoding/v1"
SOURCE_PATH = "scripts/secpal_pr_review/version_collision.py"
FUNCTION_NAME = "_verify_python_version_tokens"
FUNCTION_DIGEST = "4e9cfea26238a24d4a0e49d1adceddd95601a0fa63ef7d4ad9a909f977cb7dce"
FINDING_ID = "security:python-version-token-encoding"
CLAIM = "ENCODING_DEPENDENT_EXECUTABLE_TOKEN_EXCLUSION_BYPASS"
FIXTURE = (
    b'# coding: latin-1\npadding = "'
    + b"\xc3\xa9" * 32
    + b'"; value = f"{\'1.0\'}"\n'
)
BEFORE = b"ast.parse(blob)"
AFTER = b'ast.parse(blob.decode("utf-8", errors="strict"))'
MAXIMUM_SOURCE_BYTES = 1024 * 1024


class DiagnosticRecoveryError(ValueError):
    """A diagnostic is not independently established for exact Recovery scope."""


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def require_diagnostic_recovery_state(value: Any) -> dict[str, Any]:
    try:
        state = authority._validate_state(copy.deepcopy(value))
    except authority.LifecycleAuthorityError as exc:
        raise DiagnosticRecoveryError("diagnostic requires exact exhausted Ready state") from exc
    expected = {
        "unrestricted_review_count": 1,
        "remediation_cycle_count": 2,
        "exceptional_recovery_count": 0,
        "exceptional_recovery_history": [],
        "exceptional_continuation_count": 0,
        "exceptional_continuation_history": [],
        "cycle_3_absent": True,
        "ready": True,
        "draft": False,
        "ready_transition_count": 1,
    }
    if any(type(state[key]) is not type(item) or state[key] != item for key, item in expected.items()):
        raise DiagnosticRecoveryError("diagnostic requires exact exhausted Ready state")
    if len(state["ready_history"]) != 1 or state["ready_history"][0]["transition_kind"] != "DRAFT_TO_READY":
        raise DiagnosticRecoveryError("diagnostic requires exact exhausted Ready history")
    return state


def reproduce_security_diagnostic(prior_source: bytes, proposed_source: bytes) -> dict[str, Any]:
    """Run only the maintained, digest-pinned function; never import candidate code."""

    if any(
        not isinstance(source, bytes)
        or not 0 < len(source) <= MAXIMUM_SOURCE_BYTES
        for source in (prior_source, proposed_source)
    ):
        raise DiagnosticRecoveryError("diagnostic source exceeds the maintained profile")
    try:
        text = prior_source.decode("utf-8", errors="strict")
        parsed = ast.parse(text)
        functions = [
            node
            for node in parsed.body
            if isinstance(node, ast.FunctionDef) and node.name == FUNCTION_NAME
        ]
        function = ast.get_source_segment(text, functions[0]) if len(functions) == 1 else None
    except (UnicodeDecodeError, SyntaxError, ValueError, RecursionError) as exc:
        raise DiagnosticRecoveryError("diagnostic source is outside the maintained profile") from exc
    if function is None or _digest(function.encode("utf-8")) != FUNCTION_DIGEST:
        raise DiagnosticRecoveryError("diagnostic source is outside the maintained profile")
    if prior_source.count(BEFORE) != 1 or proposed_source != prior_source.replace(BEFORE, AFTER, 1):
        raise DiagnosticRecoveryError("diagnostic correction is not the exact maintained source delta")
    corrected = function.replace(BEFORE.decode("ascii"), AFTER.decode("ascii"), 1)
    results = []
    for source in (function, corrected):
        namespace = {
            "ast": ast,
            "io": io,
            "tokenize": tokenize,
            "VersionCollisionError": DiagnosticRecoveryError,
        }
        exec(compile(source, PROFILE, "exec"), namespace)
        try:
            namespace[FUNCTION_NAME](FIXTURE, (FIXTURE.index(b"1.0"),), "1.0")
        except DiagnosticRecoveryError as exc:
            if str(exc) != "Python version token replacement enters an interpolated string":
                raise DiagnosticRecoveryError(
                    "diagnostic reproduction failed outside the exact security claim"
                ) from exc
            results.append("EXECUTABLE_TOKEN_REJECTED")
        else:
            results.append("EXECUTABLE_TOKEN_ACCEPTED")
    if results != ["EXECUTABLE_TOKEN_ACCEPTED", "EXECUTABLE_TOKEN_REJECTED"]:
        raise DiagnosticRecoveryError(
            "diagnostic requires fail-first reproduction and exact correction proof"
        )
    command = {
        "profile": PROFILE,
        "function": FUNCTION_NAME,
        "version": "1.0",
        "offsets": [FIXTURE.index(b"1.0")],
    }
    evidence = {
        "schema_version": "1.0",
        "profile": PROFILE,
        "finding_id": FINDING_ID,
        "severity": "MATERIAL_SECURITY",
        "claim": CLAIM,
        "source_path": SOURCE_PATH,
        "prior_source_digest": _digest(prior_source),
        "proposed_source_digest": _digest(proposed_source),
        "function_digest": FUNCTION_DIGEST,
        "fixture_digest": _digest(FIXTURE),
        "command": command,
        "command_digest": authority.digest_json(command),
        "prior_result": results[0],
        "correction_result": results[1],
    }
    return {**evidence, "evidence_digest": authority.digest_json(evidence)}


def _source_blob(root: Path, tree: str) -> bytes:
    tree = authority._require_oid(tree, "diagnostic tree")
    if transport._git_text(root, ["cat-file", "-t", tree]).strip() != "tree":
        raise DiagnosticRecoveryError("diagnostic source identity is not a tree")
    entry = transport._git(
        root,
        ["ls-tree", "-lrz", tree, "--", f":(literal){SOURCE_PATH}"],
    ).stdout
    try:
        metadata, path = entry.decode("ascii").split("\t")
        mode, kind, blob_oid, size = metadata.split()
        authority._require_oid(blob_oid, "diagnostic source blob")
        if (
            mode != "100644"
            or kind != "blob"
            or path != SOURCE_PATH + "\0"
            or not 0 < int(size) <= MAXIMUM_SOURCE_BYTES
        ):
            raise ValueError("source boundary")
    except (ValueError, UnicodeDecodeError) as exc:
        raise DiagnosticRecoveryError("diagnostic source is outside the maintained profile") from exc
    result = bytes(transport._git(root, ["cat-file", "blob", blob_oid]).stdout)
    if len(result) != int(size):
        raise DiagnosticRecoveryError("diagnostic source size changed")
    return result


def reproduce_tree_diagnostic(root: Path, prior_tree: str, proposed_tree: str) -> dict[str, Any]:
    prior = _source_blob(root, prior_tree)
    proposed = _source_blob(root, proposed_tree)
    changed = transport._git(
        root,
        [
            "diff-tree", "--no-commit-id", "--name-only", "-r", "-z",
            prior_tree, proposed_tree, "--",
        ],
    ).stdout
    if changed != SOURCE_PATH.encode("ascii") + b"\0":
        raise DiagnosticRecoveryError("diagnostic correction includes unrelated source delta")
    return reproduce_security_diagnostic(prior, proposed)


def authenticate_maintained_code() -> str:
    """Authenticate the installed implementation against independently observed main."""

    facts = transport._normalize_protected_main(transport._observe_protected_main())
    branch = transport._run_bootstrap_gh(
        [
            "api", "--hostname", "github.com",
            "repos/SecPal/.github/branches/main",
        ]
    )
    try:
        observed = authority.loads_closed_json(branch.stdout)
        if (
            branch.returncode != 0
            or observed["protected"] is not True
            or observed["commit"]["sha"] != facts.head_sha
        ):
            raise ValueError("protected main changed")
    except (KeyError, TypeError, ValueError) as exc:
        raise DiagnosticRecoveryError("diagnostic requires authenticated protected main") from exc
    installed = Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory(prefix="secpal-recovery-maintained-") as directory:
        root = Path(directory)
        transport._git(root, ["init", "--quiet"])
        transport._git(
            root,
            [
                "fetch", "--quiet", "--no-tags", "--depth=1",
                transport.PROTECTED_MAIN_REMOTE_URL, facts.head_sha,
            ],
        )
        if transport._git_text(root, ["rev-parse", "FETCH_HEAD"]).strip() != facts.head_sha:
            raise DiagnosticRecoveryError("diagnostic maintained source changed")
        listing = transport._git(
            root, ["ls-tree", "-rz", "-r", facts.head_sha, "--", "scripts"]
        ).stdout
        maintained_paths = set()
        for entry in listing.rstrip(b"\0").split(b"\0"):
            metadata, relative = entry.decode("utf-8", errors="strict").split("\t")
            if not relative.endswith(".py"):
                continue
            mode, kind, blob_oid = metadata.split()
            path = installed / relative
            if (
                mode not in {"100644", "100755"}
                or kind != "blob"
                or path.is_symlink()
                or not path.is_file()
            ):
                raise DiagnosticRecoveryError("diagnostic candidate cannot supply maintained code")
            expected = transport._git(root, ["cat-file", "blob", blob_oid]).stdout
            if path.read_bytes() != expected:
                raise DiagnosticRecoveryError("diagnostic candidate cannot authenticate its own recovery")
            maintained_paths.add(relative)
        installed_paths = {
            path.relative_to(installed).as_posix()
            for path in (installed / "scripts").rglob("*.py")
        }
        if (
            installed_paths != maintained_paths
            or Path(__file__).relative_to(installed).as_posix()
            not in maintained_paths
        ):
            raise DiagnosticRecoveryError("diagnostic implementation is not accepted on protected main")
    return facts.head_sha


def derive_admission(
    observed: Any, repository_root: Path, proposed_tree: str, authorization_id: str,
) -> dict[str, Any]:
    """Derive evidence from an already authenticated publication and immutable trees."""

    from . import lifecycle_orchestration as orchestration

    lifecycle = observed.lifecycle
    require_diagnostic_recovery_state(lifecycle.state)
    if lifecycle.repository != "SecPal/.github":
        raise DiagnosticRecoveryError("diagnostic profile belongs to another repository")
    authorization_id = authority._require_identity(
        authorization_id, "Recovery authorization identity"
    )
    prior_tree = orchestration._immutable_commit_tree(
        repository_root, lifecycle.repository, lifecycle.head_sha
    )
    diagnostic = reproduce_tree_diagnostic(repository_root, prior_tree, proposed_tree)
    return {
        "schema_version": "1.1",
        "kind": "READY_EXCEPTIONAL_RECOVERY",
        "admission_kind": ADMISSION_KIND,
        "authorization_id": authorization_id,
        "repository": lifecycle.repository,
        "delivery_issue_number": lifecycle.delivery_issue,
        "pull_request_number": lifecycle.pull_request,
        "lifecycle_id": lifecycle.lifecycle_id,
        "publication_oid": observed.publication_oid,
        "publication_digest": observed.publication_digest,
        "authority_digest": lifecycle.authority_digest,
        "prior_ready_head_sha": lifecycle.head_sha,
        "prior_ready_tree_sha": prior_tree,
        "recovery_tree_sha": proposed_tree,
        "finding_ids": [FINDING_ID],
        "thread_ids": [],
        "diagnostic": diagnostic,
        "lifecycle": {
            "unrestricted_reviews": 1,
            "remediation_cycles": 2,
            "cycle_3": False,
            "draft": False,
            "ready": True,
            "ready_transition": False,
            "exceptional_recovery_count": 1,
        },
    }


def verify_admission(value: Any, observed: Any, repository_root: Path) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DiagnosticRecoveryError("diagnostic Recovery evidence is malformed")
    try:
        expected = derive_admission(observed, repository_root, value["recovery_tree_sha"], value["authorization_id"])
        if authority.canonical_json_bytes(value) != authority.canonical_json_bytes(expected):
            raise DiagnosticRecoveryError(
                "diagnostic Recovery evidence differs from independently reproduced authority"
            )
    except (KeyError, TypeError, authority.LifecycleAuthorityError) as exc:
        raise DiagnosticRecoveryError("diagnostic Recovery evidence is malformed") from exc
    return expected


def authorization_scope(
    evidence: dict[str, Any], resulting_head_sha: str
) -> dict[str, Any]:
    return {
        "pull_request": evidence["pull_request_number"],
        "predecessor_head_sha": evidence["prior_ready_head_sha"],
        "resulting_head_sha": authority._require_oid(
            resulting_head_sha, "Recovery successor head"
        ),
        "finding_ids": evidence["finding_ids"],
        "admission_kind": ADMISSION_KIND,
        "recovery_evidence": evidence,
    }


def require_successor(root: Path, evidence: dict[str, Any], resulting_head: str) -> None:
    from . import lifecycle_orchestration as orchestration

    tree = orchestration._immutable_commit_tree(
        root, evidence["repository"], resulting_head
    )
    parents = transport._git_text(
        root, ["show", "-s", "--format=%P", resulting_head]
    ).strip().split()
    if tree != evidence["recovery_tree_sha"] or parents != [evidence["prior_ready_head_sha"]]:
        raise DiagnosticRecoveryError("diagnostic Recovery requires the exact sole-parent successor")
