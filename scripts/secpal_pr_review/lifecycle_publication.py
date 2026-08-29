# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Protected append-only publication of native or legacy lifecycle authority."""

from __future__ import annotations

from contextlib import contextmanager
import copy
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
from typing import Any, Iterator, Mapping

from . import lifecycle_authority as authority
from .fast_path import canonical_json_bytes, digest_json


SCHEMA_VERSION = "1.0"
PUBLICATION_KIND = "SECPAL_LIFECYCLE_AUTHORITY_PUBLICATION"
PUBLICATION_DOMAIN = "secpal.lifecycle-authority-publication/v1"
OPERATIONS = frozenset({"ENROLL_EXISTING_LIFECYCLE", "ADVANCE_CURRENT_TERMINAL"})
ADVANCE_TRANSITIONS = authority.TRANSITIONS - {"INITIALIZED_DRAFT"}
PUBLICATION_FIELDS = frozenset(
    {
        "schema_version", "kind", "domain", "operation", "repository",
        "delivery_issue", "lifecycle_id", "initialization_evidence_digest",
        "pull_request", "head_sha", "terminal_authority_digest",
        "historical_proof_mode", "legacy_adoption_checkpoint_digest",
        "lifecycle_evidence", "lifecycle_evidence_digest", "publication_branch",
        "journal_predecessor_oid", "predecessor_publication_oid",
        "predecessor_publication_digest", "predecessor_terminal_authority_digest",
        "signer_identity", "signature", "publication_digest",
    }
)
_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
_AUTHOR_ENVIRONMENT = frozenset(
    {
        "GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_AUTHOR_DATE",
        "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL", "GIT_COMMITTER_DATE",
    }
)


class LifecyclePublicationError(ValueError):
    """Publication is absent, stale, ambiguous, malformed, or unauthorized."""


@dataclass(frozen=True)
class VerifiedLifecyclePublication:
    """Current publication and the independently verified lifecycle it selects."""

    publication_oid: str
    publication_digest: str
    publication_branch: str
    journal_predecessor_oid: str | None
    predecessor_publication_oid: str | None
    lifecycle: authority.VerifiedLifecycleAuthority


def _trusted_executable(name: str) -> tuple[str, Any]:
    helper = authority._load_trusted_command_helper()
    if name not in {"git", "gh"}:
        raise LifecyclePublicationError("publication executable is not allowlisted")
    for directory in helper.TRUSTED_COMMAND_DIRECTORIES:
        candidate = directory / name
        try:
            resolved = candidate.resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        if resolved.is_file() and os.access(resolved, os.X_OK):
            return str(resolved), helper
    raise LifecyclePublicationError(f"maintained {name} executable is unavailable")


def _closed_git_environment(
    repository_root: Path,
    extra_environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    _, helper = _trusted_executable("git")
    environment = {
        "PATH": helper.TRUSTED_COMMAND_PATH,
        "HOME": str(repository_root),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PAGER": "cat",
        "GIT_PAGER": "cat",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_OPTIONAL_LOCKS": "0",
    }
    if extra_environment:
        if not set(extra_environment) <= _AUTHOR_ENVIRONMENT | {"GIT_ASKPASS"}:
            raise LifecyclePublicationError("publication Git environment override is forbidden")
        environment.update(extra_environment)
    return environment


def _run_git(
    repository_root: Path,
    arguments: list[str],
    *,
    input_bytes: bytes | None = None,
    extra_environment: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    executable, _ = _trusted_executable("git")
    try:
        root = repository_root.resolve(strict=True)
        return subprocess.run(
            [executable, "-C", str(root), *arguments], input=input_bytes,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
            timeout=30, env=_closed_git_environment(root, extra_environment),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise LifecyclePublicationError("trusted Git publication operation failed") from exc


def _run_gh(arguments: list[str]) -> subprocess.CompletedProcess[bytes]:
    executable, helper = _trusted_executable("gh")
    base = helper.command_environment("gh")
    environment = {
        "PATH": helper.TRUSTED_COMMAND_PATH, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
        "PAGER": "cat", "GH_PAGER": "cat", "GH_HOST": "github.com",
    }
    for key in ("HOME", "GH_CONFIG_DIR"):
        if key in base:
            environment[key] = base[key]
    for key in ("GH_TOKEN", "GITHUB_TOKEN"):
        if key in base:
            environment[key] = base[key]
    try:
        return subprocess.run(
            [executable, *arguments], stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
            timeout=30, env=environment,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise LifecyclePublicationError("trusted GitHub protection observation failed") from exc


def _verify_live_protection(policy: authority.LifecycleTrustPolicy) -> int:
    result = _run_gh(
        ["api", "--hostname", "github.com",
         f"repos/{policy.repository}/rulesets/{policy.publication_ruleset_id}"]
    )
    if result.returncode != 0:
        raise LifecyclePublicationError("publication branch protection is unavailable")
    try:
        value = json.loads(result.stdout, object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LifecyclePublicationError("publication branch protection is malformed") from exc
    if not isinstance(value, dict):
        raise LifecyclePublicationError("publication branch protection is malformed")
    rules = value.get("rules")
    conditions = value.get("conditions")
    ref_names = conditions.get("ref_name") if isinstance(conditions, dict) else None
    if (
        value.get("id") != policy.publication_ruleset_id
        or value.get("target") != "branch"
        or value.get("enforcement") != "active"
        or value.get("bypass_actors") != []
        or not isinstance(ref_names, dict)
        or ref_names.get("include") != [policy.publication_branch]
        or ref_names.get("exclude") != []
        or not isinstance(rules, list)
        or not policy.publication_required_rules
        <= {item.get("type") for item in rules if isinstance(item, dict)}
    ):
        raise LifecyclePublicationError("publication branch protection contract is not active")
    return policy.publication_ruleset_id


def _github_token() -> str:
    result = _run_gh(["auth", "token", "--hostname", "github.com"])
    token = result.stdout.decode("utf-8", "strict").strip() if result.returncode == 0 else ""
    if not token or "\n" in token or len(token) > 4096:
        raise LifecyclePublicationError("maintained publication credential is unavailable")
    return token


@contextmanager
def _isolated_repository(
    policy: authority.LifecycleTrustPolicy,
    *,
    write: bool,
) -> Iterator[tuple[Path, Mapping[str, str] | None]]:
    with tempfile.TemporaryDirectory(prefix="secpal-lifecycle-publication-") as directory:
        root = Path(directory)
        if _run_git(root, ["init", "--bare", "."]).returncode != 0:
            raise LifecyclePublicationError("isolated publication repository is unavailable")
        credential_environment: Mapping[str, str] | None = None
        if write and policy.publication_remote_url.startswith("https://github.com/"):
            token = _github_token()
            askpass = root / "secpal-publication-askpass"
            askpass.write_text(
                "#!/bin/sh\ncase \"$1\" in *Username*) printf '%s\\n' x-access-token ;; *) printf '%s\\n' '"
                + token.replace("'", "'\\''") + "' ;; esac\n",
                encoding="utf-8",
            )
            askpass.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
            credential_environment = {"GIT_ASKPASS": str(askpass)}
        yield root, credential_environment


def _resolve_current_once(repository_root: Path, observed_ref: str) -> str | None:
    result = _run_git(repository_root, ["rev-parse", "--verify", "--quiet", observed_ref])
    if result.returncode == 1:
        return None
    value = result.stdout.decode("ascii", "strict").strip() if result.returncode == 0 else ""
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


def _write_publication_object(
    repository_root: Path, payload: bytes, journal_predecessor_oid: str | None,
) -> str:
    blob = _run_git(repository_root, ["hash-object", "-w", "--stdin"], input_bytes=payload)
    blob_oid = blob.stdout.decode("ascii", "strict").strip() if blob.returncode == 0 else ""
    if not _OID.fullmatch(blob_oid):
        raise LifecyclePublicationError("immutable publication blob creation failed")
    tree = _run_git(
        repository_root, ["mktree"],
        input_bytes=f"100644 blob {blob_oid}\tpublication.json\n".encode("ascii"),
    )
    tree_oid = tree.stdout.decode("ascii", "strict").strip() if tree.returncode == 0 else ""
    if not _OID.fullmatch(tree_oid):
        raise LifecyclePublicationError("publication object tree creation failed")
    arguments = ["commit-tree", tree_oid]
    if journal_predecessor_oid is not None:
        arguments.extend(["-p", journal_predecessor_oid])
    committed = _run_git(
        repository_root, arguments,
        input_bytes=b"SecPal lifecycle authority publication\n",
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


def _read_publication_object(repository_root: Path, object_oid: str) -> tuple[bytes, str | None]:
    if not _OID.fullmatch(object_oid):
        raise LifecyclePublicationError("publication object identity is invalid")
    object_type = _run_git(repository_root, ["cat-file", "-t", object_oid])
    if object_type.returncode != 0 or object_type.stdout != b"commit\n":
        raise LifecyclePublicationError("publication object is not an immutable Git commit")
    parents = _run_git(repository_root, ["rev-list", "--parents", "-n", "1", object_oid])
    values = parents.stdout.decode("ascii", "strict").strip().split() if parents.returncode == 0 else []
    if not values or values[0] != object_oid or len(values) not in {1, 2}:
        raise LifecyclePublicationError("publication journal topology is invalid")
    listing = _run_git(repository_root, ["ls-tree", "-z", object_oid])
    entries = [item for item in listing.stdout.split(b"\0") if item] if listing.returncode == 0 else []
    prefix = b"100644 blob "
    if len(entries) != 1 or not entries[0].startswith(prefix) or not entries[0].endswith(b"\tpublication.json"):
        raise LifecyclePublicationError("publication object tree is invalid")
    blob_oid = entries[0][len(prefix):].split(b"\t", 1)[0].decode("ascii", "strict")
    return _read_blob(repository_root, blob_oid), (values[1] if len(values) == 2 else None)


def _observe_remote_current_once(
    repository_root: Path,
    remote_url: str,
    publication_branch: str,
    *,
    credential_environment: Mapping[str, str] | None = None,
) -> str | None:
    observed_ref = "refs/secpal-observed/current"
    _run_git(repository_root, ["update-ref", "-d", observed_ref])
    result = _run_git(
        repository_root,
        ["fetch", "--no-tags", remote_url, f"{publication_branch}:{observed_ref}"],
        extra_environment=credential_environment,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", "replace")
        if "couldn't find remote ref" in stderr:
            return None
        raise LifecyclePublicationError("maintained publication journal cannot be observed")
    return _resolve_current_once(repository_root, observed_ref)


def _cas_remote_ref(
    repository_root: Path,
    remote_url: str,
    publication_branch: str,
    new_oid: str,
    old_oid: str | None,
    *,
    credential_environment: Mapping[str, str] | None = None,
) -> None:
    lease = f"--force-with-lease={publication_branch}:{old_oid or ''}"
    result = _run_git(
        repository_root,
        ["push", "--porcelain", lease, remote_url, f"{new_oid}:{publication_branch}"],
        extra_environment=credential_environment,
    )
    if result.returncode != 0:
        raise LifecyclePublicationError("publication journal changed during compare-and-swap")


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise LifecyclePublicationError("canonical JSON contains a duplicate field")
        value[key] = item
    return value


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


def _verify_publication_document(
    raw: bytes, *, object_oid: str, expected_branch: str,
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
    policy = authority._load_lifecycle_trust_policy(repository)
    if document["publication_branch"] != expected_branch or expected_branch != policy.publication_branch:
        raise LifecyclePublicationError("publication branch binding is invalid")
    for field in (
        "initialization_evidence_digest", "terminal_authority_digest",
        "lifecycle_evidence_digest", "publication_digest",
    ):
        authority._require_digest(document[field], field)
    authority._require_identity(document["lifecycle_id"], "lifecycle identity")
    authority._require_positive_int(document["pull_request"], "pull request")
    authority._require_oid(document["head_sha"], "publication head")
    if document["historical_proof_mode"] not in {authority.NATIVE_PROOF_MODE, authority.LEGACY_PROOF_MODE}:
        raise LifecyclePublicationError("publication historical-proof mode is invalid")
    for field in ("journal_predecessor_oid", "predecessor_publication_oid"):
        if document[field] is not None and not _OID.fullmatch(document[field]):
            raise LifecyclePublicationError(f"{field} is invalid")
    for field in (
        "legacy_adoption_checkpoint_digest", "predecessor_publication_digest",
        "predecessor_terminal_authority_digest",
    ):
        if document[field] is not None:
            authority._require_digest(document[field], field)
    if document["operation"] == "ENROLL_EXISTING_LIFECYCLE":
        if any(document[field] is not None for field in (
            "predecessor_publication_oid", "predecessor_publication_digest",
            "predecessor_terminal_authority_digest",
        )):
            raise LifecyclePublicationError("enrollment publication cannot claim a lifecycle predecessor")
    elif any(document[field] is None for field in (
        "predecessor_publication_oid", "predecessor_publication_digest",
        "predecessor_terminal_authority_digest",
    )):
        raise LifecyclePublicationError("terminal advancement requires an exact lifecycle predecessor")
    evidence = document["lifecycle_evidence"]
    evidence_raw = canonical_json_bytes(evidence)
    if document["lifecycle_evidence_digest"] != hashlib.sha256(evidence_raw).hexdigest():
        raise LifecyclePublicationError("publication lifecycle-evidence digest mismatch")
    verified = (
        authority.verify_lifecycle_authority_for_publication(evidence_raw)
        if document["operation"] == "ENROLL_EXISTING_LIFECYCLE"
        else authority._verify_lifecycle_authority_for_journal(evidence_raw)
    )
    if (
        verified.repository != repository
        or verified.delivery_issue != issue
        or verified.lifecycle_id != document["lifecycle_id"]
        or verified.initialization_evidence_digest != document["initialization_evidence_digest"]
        or verified.pull_request != document["pull_request"]
        or verified.head_sha != document["head_sha"]
        or verified.authority_digest != document["terminal_authority_digest"]
        or verified.historical_proof_mode != document["historical_proof_mode"]
        or verified.legacy_adoption_checkpoint_digest != document["legacy_adoption_checkpoint_digest"]
    ):
        raise LifecyclePublicationError("publication does not bind its verified lifecycle terminal")
    signer = authority._require_identity(document["signer_identity"], "publication signer")
    signed = {key: copy.deepcopy(value) for key, value in document.items() if key != "publication_digest"}
    if document["publication_digest"] != digest_json(signed):
        raise LifecyclePublicationError("publication digest mismatch")
    try:
        authority._verify_signature(
            canonical_json_bytes(authority._unsigned(document, "publication_digest", "signature")),
            document["signature"], signer, PUBLICATION_DOMAIN,
            policy.publication_signer_identities,
            authority._policy_signature_verifier(policy),
        )
    except authority.LifecycleAuthorityError as exc:
        raise LifecyclePublicationError(
            f"publication object {object_oid} signature policy failed"
        ) from exc
    return document, verified


def _lifecycle_bundle(document: Mapping[str, Any]) -> Mapping[str, Any]:
    evidence = document["lifecycle_evidence"]
    bundle = (
        evidence.get("lifecycle_evidence")
        if isinstance(evidence, dict) and evidence.get("kind") == authority.PUBLICATION_EVIDENCE_KIND
        else evidence
    )
    if not isinstance(bundle, dict):
        raise LifecyclePublicationError("publication lifecycle bundle is malformed")
    return bundle


def _require_exact_successor(
    predecessor: authority.VerifiedLifecycleAuthority,
    predecessor_document: Mapping[str, Any],
    successor: authority.VerifiedLifecycleAuthority,
    successor_document: Mapping[str, Any],
) -> None:
    predecessor_bundle = _lifecycle_bundle(predecessor_document)
    successor_bundle = _lifecycle_bundle(successor_document)
    old_events = predecessor_bundle["transition_authorizations"]
    old_authorities = predecessor_bundle["authority_chain"]
    new_events = successor_bundle["transition_authorizations"]
    new_authorities = successor_bundle["authority_chain"]
    if (
        successor.repository != predecessor.repository
        or successor.delivery_issue != predecessor.delivery_issue
        or successor.lifecycle_id != predecessor.lifecycle_id
        or successor.initialization_evidence_digest != predecessor.initialization_evidence_digest
        or successor.historical_proof_mode != predecessor.historical_proof_mode
        or successor.legacy_adoption_checkpoint_digest != predecessor.legacy_adoption_checkpoint_digest
        or len(new_events) != len(old_events) + 1
        or len(new_authorities) != len(old_authorities) + 1
        or new_events[:-1] != old_events
        or new_authorities[:-1] != old_authorities
        or new_authorities[-1]["predecessor_authority_digest"] != predecessor.authority_digest
        or new_authorities[-1]["transition_kind"] not in ADVANCE_TRANSITIONS
    ):
        raise LifecyclePublicationError("terminal publication is not one exact allowed successor")
    old_evidence = predecessor_document["lifecycle_evidence"]
    new_evidence = successor_document["lifecycle_evidence"]
    if isinstance(old_evidence, dict) and old_evidence.get("kind") == authority.PUBLICATION_EVIDENCE_KIND:
        if (
            not isinstance(new_evidence, dict)
            or new_evidence.get("kind") != authority.PUBLICATION_EVIDENCE_KIND
            or new_evidence.get("enrollment_mode") != old_evidence.get("enrollment_mode")
            or new_evidence.get("legacy_adoption_checkpoint") != old_evidence.get("legacy_adoption_checkpoint")
        ):
            raise LifecyclePublicationError("lifecycle enrollment root changed during advancement")


def _publication_fields(
    *, operation: str, verified: authority.VerifiedLifecycleAuthority,
    bundle: Mapping[str, Any], bundle_raw: bytes, publication_branch: str,
    journal_predecessor_oid: str | None, predecessor: Mapping[str, Any] | None,
    predecessor_oid: str | None, signer_identity: str,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION, "kind": PUBLICATION_KIND,
        "domain": PUBLICATION_DOMAIN, "operation": operation,
        "repository": verified.repository, "delivery_issue": verified.delivery_issue,
        "lifecycle_id": verified.lifecycle_id,
        "initialization_evidence_digest": verified.initialization_evidence_digest,
        "pull_request": verified.pull_request, "head_sha": verified.head_sha,
        "terminal_authority_digest": verified.authority_digest,
        "historical_proof_mode": verified.historical_proof_mode,
        "legacy_adoption_checkpoint_digest": verified.legacy_adoption_checkpoint_digest,
        "lifecycle_evidence": copy.deepcopy(bundle),
        "lifecycle_evidence_digest": hashlib.sha256(bundle_raw).hexdigest(),
        "publication_branch": publication_branch,
        "journal_predecessor_oid": journal_predecessor_oid,
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


def _walk_journal(
    repository_root: Path, tip_oid: str, publication_branch: str,
) -> tuple[
    list[tuple[str, dict[str, Any], authority.VerifiedLifecycleAuthority]],
    dict[tuple[str, int], tuple[str, dict[str, Any], authority.VerifiedLifecycleAuthority]],
]:
    reversed_entries: list[tuple[str, bytes, str | None]] = []
    seen: set[str] = set()
    oid: str | None = tip_oid
    while oid is not None:
        if oid in seen:
            raise LifecyclePublicationError("publication journal contains a cycle")
        seen.add(oid)
        raw, parent = _read_publication_object(repository_root, oid)
        reversed_entries.append((oid, raw, parent))
        oid = parent
    entries: list[tuple[str, dict[str, Any], authority.VerifiedLifecycleAuthority]] = []
    latest: dict[tuple[str, int], tuple[str, dict[str, Any], authority.VerifiedLifecycleAuthority]] = {}
    for oid, raw, parent in reversed(reversed_entries):
        document, lifecycle = _verify_publication_document(
            raw, object_oid=oid, expected_branch=publication_branch
        )
        if document["journal_predecessor_oid"] != parent:
            raise LifecyclePublicationError("publication journal parent binding is invalid")
        key = (document["repository"], document["delivery_issue"])
        previous = latest.get(key)
        if document["operation"] == "ENROLL_EXISTING_LIFECYCLE":
            if previous is not None:
                raise LifecyclePublicationError("delivery lifecycle has multiple enrollment roots")
        else:
            if previous is None:
                raise LifecyclePublicationError("publication journal is truncated before enrollment")
            old_oid, old_document, old_lifecycle = previous
            if (
                document["predecessor_publication_oid"] != old_oid
                or document["predecessor_publication_digest"] != old_document["publication_digest"]
                or document["predecessor_terminal_authority_digest"] != old_lifecycle.authority_digest
            ):
                raise LifecyclePublicationError("publication predecessor binding is invalid")
            _require_exact_successor(old_lifecycle, old_document, lifecycle, document)
        item = (oid, document, lifecycle)
        entries.append(item)
        latest[key] = item
    return entries, latest


def enroll_existing_lifecycle(
    serialized_evidence: bytes | str,
    *, signer_identity: str, signer: authority.Signer,
) -> VerifiedLifecyclePublication:
    """Publish one native lifecycle or one explicit legacy migration checkpoint."""

    bundle, bundle_raw = _canonical_bundle(serialized_evidence)
    verified = authority.verify_lifecycle_authority_for_publication(bundle_raw)
    policy = authority._load_lifecycle_trust_policy(verified.repository)
    _verify_live_protection(policy)
    with _isolated_repository(policy, write=True) as (root, credential_environment):
        tip = _observe_remote_current_once(
            root, policy.publication_remote_url, policy.publication_branch,
            credential_environment=credential_environment,
        )
        latest = {} if tip is None else _walk_journal(root, tip, policy.publication_branch)[1]
        if (verified.repository, verified.delivery_issue) in latest:
            raise LifecyclePublicationError("delivery lifecycle is already enrolled")
        fields = _publication_fields(
            operation="ENROLL_EXISTING_LIFECYCLE", verified=verified,
            bundle=bundle, bundle_raw=bundle_raw,
            publication_branch=policy.publication_branch,
            journal_predecessor_oid=tip, predecessor=None,
            predecessor_oid=None, signer_identity=signer_identity,
        )
        raw = _sign_publication(fields, signer)
        object_oid = _write_publication_object(root, raw, tip)
        document, lifecycle = _verify_publication_document(
            raw, object_oid=object_oid, expected_branch=policy.publication_branch
        )
        _cas_remote_ref(
            root, policy.publication_remote_url, policy.publication_branch,
            object_oid, tip, credential_environment=credential_environment,
        )
    return VerifiedLifecyclePublication(
        object_oid, document["publication_digest"], policy.publication_branch,
        tip, None, lifecycle,
    )


def advance_current_terminal(
    serialized_evidence: bytes | str,
    *, signer_identity: str, signer: authority.Signer,
) -> VerifiedLifecyclePublication:
    """Append one exact #750 successor to the protected global journal."""

    bundle, bundle_raw = _canonical_bundle(serialized_evidence)
    successor = authority._verify_lifecycle_authority_for_journal(bundle_raw)
    policy = authority._load_lifecycle_trust_policy(successor.repository)
    _verify_live_protection(policy)
    with _isolated_repository(policy, write=True) as (root, credential_environment):
        tip = _observe_remote_current_once(
            root, policy.publication_remote_url, policy.publication_branch,
            credential_environment=credential_environment,
        )
        if tip is None:
            raise LifecyclePublicationError("current lifecycle publication is unavailable")
        _, latest = _walk_journal(root, tip, policy.publication_branch)
        previous = latest.get((successor.repository, successor.delivery_issue))
        if previous is None:
            raise LifecyclePublicationError("current lifecycle publication is unavailable")
        predecessor_oid, predecessor_document, predecessor = previous
        _require_exact_successor(
            predecessor, predecessor_document, successor,
            {"lifecycle_evidence": bundle},
        )
        fields = _publication_fields(
            operation="ADVANCE_CURRENT_TERMINAL", verified=successor,
            bundle=bundle, bundle_raw=bundle_raw,
            publication_branch=policy.publication_branch,
            journal_predecessor_oid=tip, predecessor=predecessor_document,
            predecessor_oid=predecessor_oid, signer_identity=signer_identity,
        )
        raw = _sign_publication(fields, signer)
        object_oid = _write_publication_object(root, raw, tip)
        document, lifecycle = _verify_publication_document(
            raw, object_oid=object_oid, expected_branch=policy.publication_branch
        )
        _cas_remote_ref(
            root, policy.publication_remote_url, policy.publication_branch,
            object_oid, tip, credential_environment=credential_environment,
        )
    return VerifiedLifecyclePublication(
        object_oid, document["publication_digest"], policy.publication_branch,
        tip, predecessor_oid, lifecycle,
    )


def verify_current_lifecycle_authority(
    repository: str,
    delivery_issue: int,
    expected: authority.ExpectedLifecycle | None = None,
) -> VerifiedLifecyclePublication:
    """Verify live protection, resolve once, then authenticate immutable ancestry."""

    policy = authority._load_lifecycle_trust_policy(repository)
    _verify_live_protection(policy)
    with _isolated_repository(policy, write=False) as (root, credential_environment):
        tip = _observe_remote_current_once(
            root, policy.publication_remote_url, policy.publication_branch,
            credential_environment=credential_environment,
        )
        if tip is None:
            raise LifecyclePublicationError("current lifecycle publication is unavailable")
        _, latest = _walk_journal(root, tip, policy.publication_branch)
        key = (repository, authority._require_positive_int(delivery_issue, "delivery issue"))
        current = latest.get(key)
        if current is None:
            raise LifecyclePublicationError("current lifecycle publication is unavailable")
        publication_oid, document, lifecycle = current
    if expected is not None:
        authority._compare_expected(lifecycle, expected)
    return VerifiedLifecyclePublication(
        publication_oid, document["publication_digest"], policy.publication_branch,
        document["journal_predecessor_oid"],
        document["predecessor_publication_oid"], lifecycle,
    )
