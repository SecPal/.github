# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Independent enrollment and current-terminal publication for lifecycle authority.

Dynamic publication state lives in a dedicated Git ref namespace, outside the
delivery tree.  The mutable ref is resolved once; its immutable one-file commit
and signed document are then the sole semantic inputs. Writers use exact
compare-and-swap advancement.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any, Mapping

from . import lifecycle_authority as authority
from .fast_path import canonical_json_bytes, digest_json


SCHEMA_VERSION = "1.0"
PUBLICATION_KIND = "SECPAL_LIFECYCLE_AUTHORITY_PUBLICATION"
PUBLICATION_DOMAIN = "secpal.lifecycle-authority-publication/v1"
OPERATIONS = frozenset({"ENROLL_EXISTING_LIFECYCLE", "ADVANCE_CURRENT_TERMINAL"})
ADVANCE_TRANSITIONS = authority.TRANSITIONS - {"INITIALIZED_DRAFT"}
PUBLICATION_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "domain",
        "operation",
        "repository",
        "delivery_issue",
        "lifecycle_id",
        "initialization_evidence_digest",
        "pull_request",
        "head_sha",
        "terminal_authority_digest",
        "lifecycle_evidence",
        "lifecycle_evidence_digest",
        "publication_ref",
        "predecessor_publication_oid",
        "predecessor_publication_digest",
        "predecessor_terminal_authority_digest",
        "signer_identity",
        "signature",
        "publication_digest",
    }
)
_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")


class LifecyclePublicationError(ValueError):
    """Publication is absent, stale, ambiguous, malformed, or unauthorized."""


@dataclass(frozen=True)
class VerifiedLifecyclePublication:
    """Current publication and the independently verified lifecycle it selects."""

    publication_oid: str
    publication_digest: str
    publication_ref: str
    predecessor_publication_oid: str | None
    lifecycle: authority.VerifiedLifecycleAuthority


def _publication_ref(repository: str, delivery_issue: int) -> str:
    policy = authority._load_lifecycle_trust_policy(repository)
    if not isinstance(delivery_issue, int) or isinstance(delivery_issue, bool) or delivery_issue < 1:
        raise LifecyclePublicationError("delivery issue is invalid")
    repository_namespace = hashlib.sha256(repository.encode("utf-8")).hexdigest()
    return f"{policy.publication_ref_namespace}/{repository_namespace}/{delivery_issue}"


def _trusted_git() -> tuple[str, dict[str, str]]:
    helper = authority._load_trusted_command_helper()
    for directory in helper.TRUSTED_COMMAND_DIRECTORIES:
        candidate = directory / "git"
        try:
            resolved = candidate.resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        if resolved.is_file() and os.access(resolved, os.X_OK):
            return str(resolved), helper.command_environment("git")
    raise LifecyclePublicationError("maintained Git executable is unavailable")


def _run_git(
    repository_root: Path,
    arguments: list[str],
    *,
    input_bytes: bytes | None = None,
    extra_environment: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    executable, environment = _trusted_git()
    if extra_environment:
        environment.update(extra_environment)
    try:
        return subprocess.run(
            [executable, "-C", str(repository_root.resolve(strict=True)), *arguments],
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=30,
            env=environment,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise LifecyclePublicationError("trusted Git publication operation failed") from exc


def _resolve_current_once(repository_root: Path, publication_ref: str) -> str | None:
    result = _run_git(
        repository_root, ["rev-parse", "--verify", "--quiet", publication_ref]
    )
    if result.returncode == 1:
        return None
    if result.returncode != 0:
        raise LifecyclePublicationError("current lifecycle publication cannot be resolved")
    value = result.stdout.decode("ascii", "strict").strip()
    if not _OID.fullmatch(value):
        raise LifecyclePublicationError("current publication object identity is invalid")
    return value


def _read_blob(repository_root: Path, object_oid: str) -> bytes:
    if not _OID.fullmatch(object_oid):
        raise LifecyclePublicationError("publication object identity is invalid")
    object_type = _run_git(repository_root, ["cat-file", "-t", object_oid])
    if object_type.returncode != 0 or object_type.stdout != b"blob\n":
        raise LifecyclePublicationError("publication object is not an immutable Git blob")
    result = _run_git(repository_root, ["cat-file", "blob", object_oid])
    if result.returncode != 0:
        raise LifecyclePublicationError("publication object cannot be read")
    return result.stdout


def _write_blob(repository_root: Path, payload: bytes) -> str:
    result = _run_git(repository_root, ["hash-object", "-w", "--stdin"], input_bytes=payload)
    value = result.stdout.decode("ascii", "strict").strip() if result.returncode == 0 else ""
    if not _OID.fullmatch(value):
        raise LifecyclePublicationError("immutable publication object creation failed")
    return value


def _hash_blob(repository_root: Path, payload: bytes) -> str:
    result = _run_git(repository_root, ["hash-object", "--stdin"], input_bytes=payload)
    value = result.stdout.decode("ascii", "strict").strip() if result.returncode == 0 else ""
    if not _OID.fullmatch(value):
        raise LifecyclePublicationError("publication object identity cannot be derived")
    return value


def _write_publication_object(
    repository_root: Path, payload: bytes, predecessor_oid: str | None
) -> str:
    blob_oid = _write_blob(repository_root, payload)
    tree = _run_git(
        repository_root, ["mktree"],
        input_bytes=f"100644 blob {blob_oid}\tpublication.json\n".encode("ascii"),
    )
    tree_oid = tree.stdout.decode("ascii", "strict").strip() if tree.returncode == 0 else ""
    if not _OID.fullmatch(tree_oid):
        raise LifecyclePublicationError("publication object tree creation failed")
    arguments = ["commit-tree", tree_oid]
    if predecessor_oid is not None:
        arguments.extend(["-p", predecessor_oid])
    committed = _run_git(
        repository_root, arguments, input_bytes=b"SecPal lifecycle authority publication\n",
        extra_environment={
            "GIT_AUTHOR_NAME": "SecPal Lifecycle Publication",
            "GIT_AUTHOR_EMAIL": "publication@secpal.invalid",
            "GIT_AUTHOR_DATE": "@0 +0000",
            "GIT_COMMITTER_NAME": "SecPal Lifecycle Publication",
            "GIT_COMMITTER_EMAIL": "publication@secpal.invalid",
            "GIT_COMMITTER_DATE": "@0 +0000",
        },
    )
    object_oid = committed.stdout.decode("ascii", "strict").strip() if committed.returncode == 0 else ""
    if not _OID.fullmatch(object_oid):
        raise LifecyclePublicationError("immutable publication object creation failed")
    return object_oid


def _read_publication_object(
    repository_root: Path, object_oid: str
) -> tuple[bytes, str | None]:
    if not _OID.fullmatch(object_oid):
        raise LifecyclePublicationError("publication object identity is invalid")
    object_type = _run_git(repository_root, ["cat-file", "-t", object_oid])
    if object_type.returncode != 0 or object_type.stdout != b"commit\n":
        raise LifecyclePublicationError("publication object is not an immutable Git commit")
    parents = _run_git(repository_root, ["rev-list", "--parents", "-n", "1", object_oid])
    values = parents.stdout.decode("ascii", "strict").strip().split() if parents.returncode == 0 else []
    if not values or values[0] != object_oid or len(values) not in {1, 2}:
        raise LifecyclePublicationError("publication object parent topology is invalid")
    listing = _run_git(repository_root, ["ls-tree", "-z", object_oid])
    expected_prefix = b"100644 blob "
    entries = listing.stdout.split(b"\0") if listing.returncode == 0 else []
    entries = [entry for entry in entries if entry]
    if len(entries) != 1 or not entries[0].startswith(expected_prefix) or not entries[0].endswith(b"\tpublication.json"):
        raise LifecyclePublicationError("publication object tree is invalid")
    blob_oid = entries[0][len(expected_prefix):].split(b"\t", 1)[0].decode("ascii", "strict")
    return _read_blob(repository_root, blob_oid), (values[1] if len(values) == 2 else None)


def _observe_remote_current_once(
    repository_root: Path, remote_url: str, publication_ref: str
) -> str | None:
    observed_ref = "refs/secpal-observed/current"
    _run_git(repository_root, ["update-ref", "-d", observed_ref])
    result = _run_git(
        repository_root,
        ["fetch", "--no-tags", remote_url, f"{publication_ref}:{observed_ref}"],
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", "replace")
        if "couldn't find remote ref" in stderr:
            return None
        raise LifecyclePublicationError("maintained current publication cannot be observed")
    return _resolve_current_once(repository_root, observed_ref)


def _cas_remote_ref(
    repository_root: Path, remote_url: str, publication_ref: str,
    new_oid: str, old_oid: str | None,
) -> None:
    lease = f"--force-with-lease={publication_ref}:{old_oid or ''}"
    result = _run_git(
        repository_root,
        ["push", "--porcelain", lease, remote_url, f"{new_oid}:{publication_ref}"],
    )
    if result.returncode != 0:
        raise LifecyclePublicationError("current publication changed during compare-and-swap")


def _canonical_bundle(serialized_evidence: bytes | str) -> tuple[dict[str, Any], bytes]:
    raw = serialized_evidence.encode("utf-8") if isinstance(serialized_evidence, str) else serialized_evidence
    if not isinstance(raw, bytes):
        raise LifecyclePublicationError("lifecycle evidence must be canonical serialized JSON")
    try:
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LifecyclePublicationError("lifecycle evidence is malformed") from exc
    if not isinstance(value, dict) or canonical_json_bytes(value) != raw:
        raise LifecyclePublicationError("lifecycle evidence is not canonical")
    return value, raw


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise LifecyclePublicationError("canonical JSON contains a duplicate field")
        value[key] = item
    return value


def _verify_publication_document(
    raw: bytes,
    *,
    object_oid: str,
    expected_ref: str,
) -> tuple[dict[str, Any], authority.VerifiedLifecycleAuthority]:
    try:
        document = json.loads(raw, object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LifecyclePublicationError("publication document is malformed") from exc
    if not isinstance(document, dict) or canonical_json_bytes(document) != raw:
        raise LifecyclePublicationError("publication document is not canonical")
    if frozenset(document) != PUBLICATION_FIELDS:
        raise LifecyclePublicationError("publication document has missing or unknown fields")
    if document["schema_version"] != SCHEMA_VERSION:
        raise LifecyclePublicationError("unknown publication version")
    if document["kind"] != PUBLICATION_KIND or document["domain"] != PUBLICATION_DOMAIN:
        raise LifecyclePublicationError("unknown publication kind or domain")
    if document["operation"] not in OPERATIONS:
        raise LifecyclePublicationError("unknown publication operation")
    repository = authority._require_repository(document["repository"])
    issue = authority._require_positive_int(document["delivery_issue"], "delivery issue")
    if document["publication_ref"] != expected_ref or expected_ref != _publication_ref(repository, issue):
        raise LifecyclePublicationError("publication namespace binding is invalid")
    for field in (
        "initialization_evidence_digest",
        "terminal_authority_digest",
        "lifecycle_evidence_digest",
        "publication_digest",
    ):
        authority._require_digest(document[field], field)
    authority._require_identity(document["lifecycle_id"], "lifecycle identity")
    authority._require_positive_int(document["pull_request"], "pull request")
    authority._require_oid(document["head_sha"], "publication head")
    predecessor_oid = document["predecessor_publication_oid"]
    if predecessor_oid is not None and not _OID.fullmatch(predecessor_oid):
        raise LifecyclePublicationError("predecessor publication object is invalid")
    for field in ("predecessor_publication_digest", "predecessor_terminal_authority_digest"):
        if document[field] is not None:
            authority._require_digest(document[field], field)
    if document["operation"] == "ENROLL_EXISTING_LIFECYCLE":
        if any(document[field] is not None for field in (
            "predecessor_publication_oid",
            "predecessor_publication_digest",
            "predecessor_terminal_authority_digest",
        )):
            raise LifecyclePublicationError("enrollment publication cannot claim a predecessor")
    elif (
        any(document[field] is None for field in (
            "predecessor_publication_oid", "predecessor_publication_digest",
            "predecessor_terminal_authority_digest",
        ))
    ):
        raise LifecyclePublicationError("terminal advancement requires an exact predecessor")
    evidence = document["lifecycle_evidence"]
    evidence_raw = canonical_json_bytes(evidence)
    if document["lifecycle_evidence_digest"] != hashlib.sha256(evidence_raw).hexdigest():
        raise LifecyclePublicationError("publication lifecycle-evidence digest mismatch")
    verified = authority.verify_lifecycle_authority_for_publication(evidence_raw)
    if (
        verified.repository != repository
        or verified.delivery_issue != issue
        or verified.lifecycle_id != document["lifecycle_id"]
        or verified.initialization_evidence_digest != document["initialization_evidence_digest"]
        or verified.pull_request != document["pull_request"]
        or verified.head_sha != document["head_sha"]
        or verified.authority_digest != document["terminal_authority_digest"]
    ):
        raise LifecyclePublicationError("publication does not bind its verified lifecycle terminal")
    signer = authority._require_identity(document["signer_identity"], "publication signer")
    signed = {key: copy.deepcopy(value) for key, value in document.items() if key != "publication_digest"}
    if document["publication_digest"] != digest_json(signed):
        raise LifecyclePublicationError("publication digest mismatch")
    unsigned = authority._unsigned(document, "publication_digest", "signature")
    policy = authority._load_lifecycle_trust_policy(repository)
    try:
        authority._verify_signature(
            canonical_json_bytes(unsigned), document["signature"], signer,
            PUBLICATION_DOMAIN, policy.publication_signer_identities,
            authority._policy_signature_verifier(policy),
        )
    except authority.LifecycleAuthorityError as exc:
        raise LifecyclePublicationError(
            f"publication object {object_oid} signature policy failed"
        ) from exc
    return document, verified


def _publication_fields(
    *, operation: str, verified: authority.VerifiedLifecycleAuthority,
    bundle: Mapping[str, Any], bundle_raw: bytes, publication_ref: str,
    predecessor: Mapping[str, Any] | None, predecessor_oid: str | None,
    signer_identity: str,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": PUBLICATION_KIND,
        "domain": PUBLICATION_DOMAIN,
        "operation": operation,
        "repository": verified.repository,
        "delivery_issue": verified.delivery_issue,
        "lifecycle_id": verified.lifecycle_id,
        "initialization_evidence_digest": verified.initialization_evidence_digest,
        "pull_request": verified.pull_request,
        "head_sha": verified.head_sha,
        "terminal_authority_digest": verified.authority_digest,
        "lifecycle_evidence": copy.deepcopy(bundle),
        "lifecycle_evidence_digest": hashlib.sha256(bundle_raw).hexdigest(),
        "publication_ref": publication_ref,
        "predecessor_publication_oid": predecessor_oid,
        "predecessor_publication_digest": None if predecessor is None else predecessor["publication_digest"],
        "predecessor_terminal_authority_digest": None if predecessor is None else predecessor["terminal_authority_digest"],
        "signer_identity": authority._require_identity(signer_identity, "publication signer"),
    }


def _sign_publication(fields: Mapping[str, Any], signer: authority.Signer) -> bytes:
    signature = authority._normalize_signature(
        signer(canonical_json_bytes(fields), PUBLICATION_DOMAIN), fields["signer_identity"]
    )
    signed = {**copy.deepcopy(dict(fields)), "signature": signature}
    return canonical_json_bytes({**signed, "publication_digest": digest_json(signed)})


def enroll_existing_lifecycle(
    repository_root: Path,
    serialized_evidence: bytes | str,
    *, signer_identity: str,
    signer: authority.Signer,
) -> VerifiedLifecyclePublication:
    """Publish one verified historical lifecycle without resetting its history."""

    bundle, bundle_raw = _canonical_bundle(serialized_evidence)
    verified = authority.verify_lifecycle_authority_for_publication(bundle_raw)
    policy = authority._load_lifecycle_trust_policy(verified.repository)
    publication_ref = _publication_ref(verified.repository, verified.delivery_issue)
    if _observe_remote_current_once(
        repository_root, policy.publication_remote_url, publication_ref
    ) is not None:
        raise LifecyclePublicationError("delivery lifecycle is already enrolled")
    fields = _publication_fields(
        operation="ENROLL_EXISTING_LIFECYCLE", verified=verified, bundle=bundle,
        bundle_raw=bundle_raw, publication_ref=publication_ref, predecessor=None,
        predecessor_oid=None, signer_identity=signer_identity,
    )
    raw = _sign_publication(fields, signer)
    object_oid = _write_publication_object(repository_root, raw, None)
    document, lifecycle = _verify_publication_document(
        raw, object_oid=object_oid, expected_ref=publication_ref
    )
    _cas_remote_ref(
        repository_root, policy.publication_remote_url, publication_ref, object_oid, None
    )
    return VerifiedLifecyclePublication(
        publication_oid=object_oid,
        publication_digest=document["publication_digest"],
        publication_ref=publication_ref,
        predecessor_publication_oid=None,
        lifecycle=lifecycle,
    )


def _require_exact_successor(
    predecessor: authority.VerifiedLifecycleAuthority,
    predecessor_document: Mapping[str, Any],
    successor: authority.VerifiedLifecycleAuthority,
    successor_bundle: Mapping[str, Any],
) -> None:
    predecessor_bundle = predecessor_document["lifecycle_evidence"]
    old_events = predecessor_bundle["transition_authorizations"]
    old_authorities = predecessor_bundle["authority_chain"]
    new_events = successor_bundle["transition_authorizations"]
    new_authorities = successor_bundle["authority_chain"]
    if (
        successor.repository != predecessor.repository
        or successor.delivery_issue != predecessor.delivery_issue
        or successor.lifecycle_id != predecessor.lifecycle_id
        or successor.initialization_evidence_digest != predecessor.initialization_evidence_digest
        or len(new_events) != len(old_events) + 1
        or len(new_authorities) != len(old_authorities) + 1
        or new_events[:-1] != old_events
        or new_authorities[:-1] != old_authorities
        or new_authorities[-1]["predecessor_authority_digest"] != predecessor.authority_digest
        or new_authorities[-1]["transition_kind"] not in ADVANCE_TRANSITIONS
    ):
        raise LifecyclePublicationError("terminal publication is not one exact allowed successor")


def advance_current_terminal(
    repository_root: Path,
    serialized_evidence: bytes | str,
    *, signer_identity: str,
    signer: authority.Signer,
) -> VerifiedLifecyclePublication:
    """Advance CURRENT to one verified successor using exact ref compare-and-swap."""

    bundle, bundle_raw = _canonical_bundle(serialized_evidence)
    successor = authority.verify_lifecycle_authority_for_publication(bundle_raw)
    policy = authority._load_lifecycle_trust_policy(successor.repository)
    publication_ref = _publication_ref(successor.repository, successor.delivery_issue)
    predecessor_oid = _observe_remote_current_once(
        repository_root, policy.publication_remote_url, publication_ref
    )
    if predecessor_oid is None:
        raise LifecyclePublicationError("current lifecycle publication is unavailable")
    predecessor_raw, predecessor_parent = _read_publication_object(
        repository_root, predecessor_oid
    )
    predecessor_document, predecessor = _verify_publication_document(
        predecessor_raw, object_oid=predecessor_oid, expected_ref=publication_ref
    )
    if predecessor_parent != predecessor_document["predecessor_publication_oid"]:
        raise LifecyclePublicationError("publication Git parent binding is invalid")
    _require_exact_successor(predecessor, predecessor_document, successor, bundle)
    fields = _publication_fields(
        operation="ADVANCE_CURRENT_TERMINAL", verified=successor, bundle=bundle,
        bundle_raw=bundle_raw, publication_ref=publication_ref,
        predecessor=predecessor_document, predecessor_oid=predecessor_oid,
        signer_identity=signer_identity,
    )
    raw = _sign_publication(fields, signer)
    object_oid = _write_publication_object(repository_root, raw, predecessor_oid)
    document, lifecycle = _verify_publication_document(
        raw, object_oid=object_oid, expected_ref=publication_ref
    )
    _cas_remote_ref(
        repository_root, policy.publication_remote_url, publication_ref,
        object_oid, predecessor_oid,
    )
    return VerifiedLifecyclePublication(
        publication_oid=object_oid,
        publication_digest=document["publication_digest"],
        publication_ref=publication_ref,
        predecessor_publication_oid=predecessor_oid,
        lifecycle=lifecycle,
    )


def verify_current_lifecycle_authority(
    repository: str,
    delivery_issue: int,
    expected: authority.ExpectedLifecycle | None = None,
) -> VerifiedLifecyclePublication:
    """Resolve CURRENT independently, then verify its immutable publication chain."""

    policy = authority._load_lifecycle_trust_policy(repository)
    publication_ref = _publication_ref(repository, delivery_issue)
    with tempfile.TemporaryDirectory(prefix="secpal-lifecycle-publication-") as directory:
        repository_root = Path(directory)
        initialized = _run_git(repository_root.parent, ["init", "--bare", str(repository_root)])
        if initialized.returncode != 0:
            raise LifecyclePublicationError("publication observation repository is unavailable")
        current_oid = _observe_remote_current_once(
            repository_root, policy.publication_remote_url, publication_ref
        )
        if current_oid is None:
            raise LifecyclePublicationError("current lifecycle publication is unavailable")
        current_raw, current_parent = _read_publication_object(
            repository_root, current_oid
        )
        seen: set[str] = set()
        documents: list[tuple[str, dict[str, Any], authority.VerifiedLifecycleAuthority]] = []
        object_oid: str | None = current_oid
        raw: bytes | None = current_raw
        git_parent: str | None = current_parent
        while object_oid is not None and raw is not None:
            if object_oid in seen:
                raise LifecyclePublicationError("publication predecessor chain contains a cycle")
            seen.add(object_oid)
            document, lifecycle = _verify_publication_document(
                raw, object_oid=object_oid, expected_ref=publication_ref,
            )
            if git_parent != document["predecessor_publication_oid"]:
                raise LifecyclePublicationError("publication Git parent binding is invalid")
            documents.append((object_oid, document, lifecycle))
            object_oid = document["predecessor_publication_oid"]
            if object_oid is None:
                raw = None
            else:
                raw, git_parent = _read_publication_object(repository_root, object_oid)
    documents.reverse()
    if not documents or documents[0][1]["operation"] != "ENROLL_EXISTING_LIFECYCLE":
        raise LifecyclePublicationError("publication chain has no enrollment root")
    previous_oid: str | None = None
    previous_document: dict[str, Any] | None = None
    previous_lifecycle: authority.VerifiedLifecycleAuthority | None = None
    for oid, document, lifecycle in documents:
        if previous_document is not None:
            if (
                document["operation"] != "ADVANCE_CURRENT_TERMINAL"
                or document["predecessor_publication_oid"] != previous_oid
                or document["predecessor_publication_digest"] != previous_document["publication_digest"]
                or document["predecessor_terminal_authority_digest"] != previous_lifecycle.authority_digest
            ):
                raise LifecyclePublicationError("publication predecessor binding is invalid")
            _require_exact_successor(
                previous_lifecycle, previous_document, lifecycle,
                document["lifecycle_evidence"],
            )
        previous_oid, previous_document, previous_lifecycle = oid, document, lifecycle
    if previous_document is None or previous_lifecycle is None:
        raise LifecyclePublicationError("current lifecycle publication is unavailable")
    if expected is not None:
        authority._compare_expected(previous_lifecycle, expected)
    return VerifiedLifecyclePublication(
        publication_oid=current_oid,
        publication_digest=previous_document["publication_digest"],
        publication_ref=publication_ref,
        predecessor_publication_oid=previous_document["predecessor_publication_oid"],
        lifecycle=previous_lifecycle,
    )
