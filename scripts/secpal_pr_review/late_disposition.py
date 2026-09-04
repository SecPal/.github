# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Canonical detached authentication for post-push review disposition."""

from __future__ import annotations

import errno
import hashlib
import json
import os
import pwd
import re
import secrets
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


SCHEMA_VERSION = "1.0"
ABSENCE_SCHEMA_VERSION = "1.1"
KIND = "LATE_FEEDBACK_DISPOSITION"
SIGNATURE_NAMESPACE = "secpal-late-feedback-disposition-v1"
CLASSIFICATION_KIND = "LATE_FEEDBACK_CLASSIFICATION"
CLASSIFICATION_SIGNATURE_NAMESPACE = "secpal-late-feedback-classification-v1"
CLASSIFICATION_PURPOSE = "AUTHORIZE_LATE_FEEDBACK_DISPOSITION"
TECHNICAL_BLOCKERS = frozenset(
    {"P1", "P2", "SECURITY", "AUTHENTICATION", "INTEGRITY", "FAIL_OPEN"}
)
MAXIMUM_ARTIFACT_BYTES = 64 * 1024
MAXIMUM_SIGNATURE_BYTES = 32 * 1024
OID = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
THREAD_ID = re.compile(r"^PRRT_[A-Za-z0-9_-]+$")
IDENTITY = re.compile(r"^[^\x00-\x20\x7f]{1,256}$")
SSH_FINGERPRINT = re.compile(r"SHA256:[A-Za-z0-9+/]+={0,2}")
OPENPGP_FINGERPRINT = re.compile(r"[0-9A-Fa-f]{40,64}")
TRUSTED_COMMAND_DIRECTORIES = tuple(
    Path(value) for value in ("/usr/bin", "/bin", "/usr/local/bin", "/opt/homebrew/bin", "/opt/local/bin")
)
TRUSTED_COMMAND_PATH = os.pathsep.join(str(path) for path in TRUSTED_COMMAND_DIRECTORIES)
GIT_OVERRIDE = re.compile(r"^(?:GIT_CONFIG(?:_|$)|GIT_TRACE(?:2)?(?:_|$))")


class LateDispositionError(RuntimeError):
    """Detached late-disposition evidence is unavailable or unauthorized."""


@dataclass(frozen=True)
class SignerIdentity:
    signature_format: str
    fingerprint: str


@dataclass(frozen=True)
class ThreadAuthorization:
    thread_id: str
    top_level_comment_node_id: str
    top_level_comment_database_id: int
    finding_body_digest: str
    reply_state_digest: str
    reply_count: int
    is_resolved: bool
    is_outdated: bool
    classification: str
    disposition: str
    technically_blocking: bool
    classification_evidence_digest: str


@dataclass(frozen=True)
class LateDispositionEvidence:
    artifact_digest: str
    canonical_payload: bytes
    delivery_issue_number: int
    signer: SignerIdentity
    threads: tuple[ThreadAuthorization, ...]


@dataclass(frozen=True)
class ClassificationEvidence:
    evidence_digest: str
    canonical_payload: bytes
    repository: str
    delivery_issue_number: int
    pull_request_number: int
    head_sha: str
    signer: SignerIdentity
    finding_id: str
    finding_evidence_digest: str
    thread: ThreadAuthorization
    technical_blockers: tuple[str, ...]


@dataclass
class BoundOutput:
    directory: Path
    basename: str
    descriptor: int
    device: int
    inode: int

    def close(self) -> None:
        os.close(self.descriptor)


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8") + b"\n"


def digest_json(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _reject_nonfinite(value: str) -> Any:
    raise ValueError(f"non-finite JSON constant: {value}")


def _reject_duplicate_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _read_bounded_regular_file(
    path: Path, label: str, maximum_bytes: int
) -> bytes:
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise LateDispositionError(f"{label} is unavailable") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size < 1:
            raise LateDispositionError(f"{label} is unavailable")
        chunks: list[bytes] = []
        remaining = maximum_bytes + 1
        while remaining:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
    except OSError as exc:
        raise LateDispositionError(f"{label} is unavailable") from exc
    finally:
        os.close(descriptor)
    if not raw or len(raw) > maximum_bytes:
        raise LateDispositionError(f"{label} size is invalid")
    return raw


def _load_canonical_json_bytes(
    raw: bytes, label: str, maximum_bytes: int
) -> tuple[Any, bytes]:
    if not raw or len(raw) > maximum_bytes:
        raise LateDispositionError(f"{label} size is invalid")
    try:
        value = json.loads(
            raw,
            parse_constant=_reject_nonfinite,
            object_pairs_hook=_reject_duplicate_object,
        )
    except (UnicodeDecodeError, ValueError) as exc:
        raise LateDispositionError(f"{label} is malformed") from exc
    try:
        canonical = canonical_json_bytes(value)
    except (TypeError, ValueError) as exc:
        raise LateDispositionError(f"{label} is malformed") from exc
    if raw != canonical:
        raise LateDispositionError(f"{label} bytes are not canonical")
    return value, canonical


def _load_canonical_json(path: Path, label: str, maximum_bytes: int) -> tuple[Any, bytes]:
    raw = _read_bounded_regular_file(path, label, maximum_bytes)
    return _load_canonical_json_bytes(raw, label, maximum_bytes)


def _write_private_file(path: Path, content: bytes) -> None:
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | os.O_CLOEXEC
        | os.O_NOFOLLOW
    )
    descriptor = os.open(path, flags, 0o600)
    try:
        offset = 0
        while offset < len(content):
            offset += os.write(descriptor, content[offset:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def signer_from_git_verification(signature_format: str, output: str) -> SignerIdentity:
    if signature_format == "ssh":
        fingerprints = set(SSH_FINGERPRINT.findall(output))
        if len(fingerprints) == 1:
            return SignerIdentity("ssh", fingerprints.pop())
    elif signature_format == "openpgp":
        fingerprints = {
            match.group(1).upper()
            for match in re.finditer(
                r"(?m)^\[GNUPG:\]\s+VALIDSIG\s+([0-9A-Fa-f]{40,64})(?:\s|$)",
                output,
            )
        }
        if len(fingerprints) == 1:
            return SignerIdentity("openpgp", fingerprints.pop())
    raise LateDispositionError("final delivery signer identity is unavailable")


def _trusted_executable(name: str) -> str:
    if name not in {"git", "gpg", "ssh-keygen"}:
        raise LateDispositionError("signature executable is not allowlisted")
    for directory in TRUSTED_COMMAND_DIRECTORIES:
        candidate = directory / name
        try:
            resolved = candidate.resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        if resolved.is_file() and os.access(resolved, os.X_OK):
            return str(resolved)
    raise LateDispositionError(f"trusted {name} executable is unavailable")


def os_account_home() -> Path:
    try:
        account_home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    except (KeyError, OSError) as exc:
        raise LateDispositionError("OS account home is unavailable") from exc
    try:
        home = account_home.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise LateDispositionError("OS account home is unavailable") from exc
    if not home.is_dir() or not home.is_absolute():
        raise LateDispositionError("OS account home is unavailable")
    return home


def signing_environment(*, account_home: Path | None = None) -> dict[str, str]:
    if account_home is None:
        home = os_account_home()
    else:
        try:
            home = account_home.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise LateDispositionError("OS account home is unavailable") from exc
    if not home.is_dir() or not home.is_absolute():
        raise LateDispositionError("OS account home is unavailable")
    environment = {
        key: value
        for key, value in os.environ.items()
        if not GIT_OVERRIDE.match(key)
        and not key.startswith(("DYLD_", "LD_", "PYTHON"))
        and key
        not in {
            "BASH_ENV",
            "CDPATH",
            "ENV",
            "HOME",
            "XDG_CONFIG_HOME",
            "GNUPGHOME",
            "GPG_TTY",
            "GPG_AGENT_INFO",
            "PINENTRY_USER_DATA",
            "SHELLOPTS",
            "SSH_AGENT_PID",
            "SSH_ASKPASS",
            "SSH_AUTH_SOCK",
            "GIT_ASKPASS",
        }
    }
    environment.update(
        {
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "GNUPGHOME": str(home / ".gnupg"),
            "PATH": TRUSTED_COMMAND_PATH,
            "GIT_CONFIG_NOSYSTEM": "1",
        }
    )
    return environment


def _run_signature_command(
    executable: str,
    arguments: Sequence[str],
    *,
    environment: dict[str, str],
    stdin: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    try:
        if stdin is None:
            completed = _run_signature_command_without_input(
                executable, arguments, environment
            )
        else:
            completed = _run_signature_command_with_input(
                executable, arguments, environment, stdin
            )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LateDispositionError("signature command is unavailable") from exc
    return completed


def _run_signature_command_without_input(
    executable: str,
    arguments: Sequence[str],
    environment: dict[str, str],
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [executable, *arguments],
        check=False,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        env=environment,
        timeout=30,
    )


def _run_signature_command_with_input(
    executable: str,
    arguments: Sequence[str],
    environment: dict[str, str],
    stdin: bytes,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [executable, *arguments],
        check=False,
        input=stdin,
        capture_output=True,
        env=environment,
        timeout=30,
    )


def _read_global_git_value(key: str, environment: dict[str, str]) -> str:
    executable = _trusted_executable("git")
    arguments = ("config", "--global", "--get", key)
    try:
        completed = subprocess.run(
            [executable, *arguments],
            check=False,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            env=environment,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LateDispositionError("OS-account signing configuration is unavailable") from exc
    if completed.returncode not in (0, 1):
        raise LateDispositionError("OS-account signing configuration is unavailable")
    return completed.stdout.decode("utf-8", errors="replace").strip()


def read_signing_configuration(
    *, environment: dict[str, str] | None = None
) -> tuple[str, str]:
    command_environment = signing_environment() if environment is None else environment
    signature_format = _read_global_git_value(
        "gpg.format", command_environment
    ) or "openpgp"
    signing_key = _read_global_git_value("user.signingkey", command_environment)
    if signature_format not in {"ssh", "openpgp"} or not signing_key:
        raise LateDispositionError(
            "OS-account signing configuration is missing or unsupported"
        )
    return signature_format, signing_key


def verify_detached_signature(
    artifact_path: Path,
    signature_path: Path,
    expected_signer: SignerIdentity,
    *,
    environment: dict[str, str] | None = None,
    signature_namespace: str = SIGNATURE_NAMESPACE,
) -> bytes:
    artifact = _read_bounded_regular_file(
        artifact_path, "late-disposition artifact", MAXIMUM_ARTIFACT_BYTES
    )
    _value, canonical = _load_canonical_json_bytes(
        artifact, "late-disposition artifact", MAXIMUM_ARTIFACT_BYTES
    )
    signature = _read_bounded_regular_file(
        signature_path,
        "late-disposition signature",
        MAXIMUM_SIGNATURE_BYTES,
    )
    command_environment = signing_environment() if environment is None else environment
    with tempfile.TemporaryDirectory(prefix="secpal-late-verify-") as directory:
        snapshot_root = Path(directory)
        os.chmod(snapshot_root, 0o700)
        snapshot_artifact = snapshot_root / "artifact.json"
        snapshot_signature = snapshot_root / "artifact.sig"
        _write_private_file(snapshot_artifact, canonical)
        _write_private_file(snapshot_signature, signature)
        if expected_signer.signature_format == "ssh":
            executable = _trusted_executable("ssh-keygen")
            completed = _run_signature_command(
                executable,
                (
                    "-Y",
                    "check-novalidate",
                    "-n",
                    signature_namespace,
                    "-s",
                    str(snapshot_signature),
                ),
                environment=command_environment,
                stdin=canonical,
            )
            output = (completed.stdout + b"\n" + completed.stderr).decode(
                "utf-8", errors="replace"
            )
            if completed.returncode != 0:
                raise LateDispositionError("late-disposition SSH signature is invalid")
            actual = signer_from_git_verification("ssh", output)
        elif expected_signer.signature_format == "openpgp":
            executable = _trusted_executable("gpg")
            completed = _run_signature_command(
                executable,
                (
                    "--batch",
                    "--no-tty",
                    "--status-fd=1",
                    "--verify",
                    str(snapshot_signature),
                    str(snapshot_artifact),
                ),
                environment=command_environment,
            )
            if completed.returncode != 0:
                raise LateDispositionError("late-disposition OpenPGP signature is invalid")
            status_output = completed.stdout.decode("utf-8", errors="replace")
            actual = signer_from_git_verification("openpgp", status_output)
        else:
            raise LateDispositionError("late-disposition signature format is unsupported")
    if actual != expected_signer:
        raise LateDispositionError("late-disposition signer does not match final delivery signer")
    return canonical


def _positive_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def parse_classification_artifact(
    artifact_path: Path,
    signature_path: Path,
    *,
    expected_signer: SignerIdentity,
    repository: str,
    delivery_issue_number: int,
    pull_request_number: int,
    head_sha: str,
    thread_id: str,
    signature_environment: dict[str, str] | None = None,
    require_nonblocking_disposition: bool = True,
) -> ClassificationEvidence:
    canonical = verify_detached_signature(
        artifact_path,
        signature_path,
        expected_signer,
        environment=signature_environment,
        signature_namespace=CLASSIFICATION_SIGNATURE_NAMESPACE,
    )
    payload, _canonical = _load_canonical_json_bytes(
        canonical, "late classification artifact", MAXIMUM_ARTIFACT_BYTES
    )
    expected_keys = {
        "schema_version",
        "kind",
        "repository",
        "delivery_issue_number",
        "pull_request_number",
        "head_sha",
        "delivery_signer",
        "authorized_purpose",
        "finding_id",
        "finding_evidence_digest",
        "thread",
    }
    declared_signer = payload.get("delivery_signer") if isinstance(payload, dict) else None
    if (
        not isinstance(payload, dict)
        or set(payload) != expected_keys
        or payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("kind") != CLASSIFICATION_KIND
        or payload.get("repository") != repository
        or payload.get("delivery_issue_number") != delivery_issue_number
        or payload.get("pull_request_number") != pull_request_number
        or payload.get("head_sha") != head_sha.lower()
        or payload.get("authorized_purpose") != CLASSIFICATION_PURPOSE
        or not isinstance(payload.get("finding_id"), str)
        or not IDENTITY.fullmatch(payload["finding_id"])
        or not isinstance(payload.get("finding_evidence_digest"), str)
        or not DIGEST.fullmatch(payload["finding_evidence_digest"])
        or not isinstance(declared_signer, dict)
        or set(declared_signer) != {"format", "fingerprint"}
        or declared_signer
        != {
            "format": expected_signer.signature_format,
            "fingerprint": expected_signer.fingerprint,
        }
    ):
        raise LateDispositionError(
            "late classification artifact binding is invalid or stale"
        )
    item = payload.get("thread")
    item_keys = {
        "thread_id",
        "top_level_comment_node_id",
        "top_level_comment_database_id",
        "finding_body_digest",
        "reply_state_digest",
        "reply_count",
        "is_resolved",
        "is_outdated",
        "classification",
        "disposition",
        "technically_blocking",
        "technical_blockers",
    }
    if not isinstance(item, dict) or set(item) != item_keys:
        raise LateDispositionError("late classification thread entry is malformed")
    blockers = item.get("technical_blockers")
    if (
        not isinstance(blockers, list)
        or any(not isinstance(value, str) for value in blockers)
        or len(blockers) != len(set(blockers))
        or any(value not in TECHNICAL_BLOCKERS for value in blockers)
    ):
        raise LateDispositionError("late classification risk facts are malformed")
    technically_blocking = item.get("technically_blocking")
    if technically_blocking is not bool(blockers):
        raise LateDispositionError("late classification risk facts are inconsistent")
    if (
        item.get("thread_id") != thread_id
        or not THREAD_ID.fullmatch(thread_id)
        or not isinstance(item.get("top_level_comment_node_id"), str)
        or not IDENTITY.fullmatch(item["top_level_comment_node_id"])
        or not _positive_integer(item.get("top_level_comment_database_id"))
        or not isinstance(item.get("finding_body_digest"), str)
        or not DIGEST.fullmatch(item["finding_body_digest"])
        or not isinstance(item.get("reply_state_digest"), str)
        or not DIGEST.fullmatch(item["reply_state_digest"])
        or not isinstance(item.get("reply_count"), int)
        or isinstance(item.get("reply_count"), bool)
        or item["reply_count"] < 0
        or item.get("is_resolved") is not False
        or not isinstance(item.get("is_outdated"), bool)
        or not isinstance(technically_blocking, bool)
    ):
        raise LateDispositionError("late classification thread binding is malformed")
    if require_nonblocking_disposition and (
        item.get("classification") != "INVALID_FALSE_OR_MISLEADING"
        or item.get("disposition") != "DISPROVEN_WITH_EVIDENCE"
        or technically_blocking is not False
        or blockers
    ):
        raise LateDispositionError("late classification is not resolution-eligible")
    digest = hashlib.sha256(canonical).hexdigest()
    return ClassificationEvidence(
        evidence_digest=digest,
        canonical_payload=canonical,
        repository=repository,
        delivery_issue_number=delivery_issue_number,
        pull_request_number=pull_request_number,
        head_sha=head_sha.lower(),
        signer=expected_signer,
        finding_id=payload["finding_id"],
        finding_evidence_digest=payload["finding_evidence_digest"],
        thread=ThreadAuthorization(
            thread_id=thread_id,
            top_level_comment_node_id=item["top_level_comment_node_id"],
            top_level_comment_database_id=item["top_level_comment_database_id"],
            finding_body_digest=item["finding_body_digest"],
            reply_state_digest=item["reply_state_digest"],
            reply_count=item["reply_count"],
            is_resolved=False,
            is_outdated=item["is_outdated"],
            classification=item["classification"],
            disposition=item["disposition"],
            technically_blocking=technically_blocking,
            classification_evidence_digest=digest,
        ),
        technical_blockers=tuple(blockers),
    )


def parse_artifact(
    artifact_path: Path,
    signature_path: Path,
    *,
    expected_signer: SignerIdentity,
    repository: str,
    delivery_issue_number: int,
    pull_request_number: int,
    head_sha: str,
    validated_tree_sha: str,
    validation_receipt_digest: str,
    validation_attestation_digest: str,
    final_eligibility_evidence_digest: str | None,
    thread_ids: tuple[str, ...],
    allowed_dispositions: dict[str, frozenset[str]],
    final_eligibility_absence_recovery_digest: str | None = None,
    signature_environment: dict[str, str] | None = None,
) -> LateDispositionEvidence:
    canonical = verify_detached_signature(
        artifact_path,
        signature_path,
        expected_signer,
        environment=signature_environment,
    )
    try:
        payload = json.loads(
            canonical,
            parse_constant=_reject_nonfinite,
            object_pairs_hook=_reject_duplicate_object,
        )
    except (TypeError, ValueError) as exc:
        raise LateDispositionError("late-disposition artifact is malformed") from exc
    common_keys = {
        "schema_version",
        "kind",
        "repository",
        "delivery_issue_number",
        "pull_request_number",
        "head_sha",
        "validated_tree_sha",
        "validation_receipt_digest",
        "validation_attestation_digest",
        "delivery_signer",
        "authorized_action",
        "threads",
    }
    manifest_mode = (
        isinstance(payload, dict)
        and payload.get("schema_version") == SCHEMA_VERSION
        and set(payload) == common_keys | {"final_eligibility_evidence_digest"}
        and isinstance(final_eligibility_evidence_digest, str)
        and DIGEST.fullmatch(final_eligibility_evidence_digest)
        and final_eligibility_absence_recovery_digest is None
    )
    absence_mode = (
        isinstance(payload, dict)
        and payload.get("schema_version") == ABSENCE_SCHEMA_VERSION
        and set(payload)
        == common_keys
        | {
            "final_eligibility_status",
            "final_eligibility_absence_recovery_digest",
        }
        and final_eligibility_evidence_digest is None
    )
    if not manifest_mode and not absence_mode:
        raise LateDispositionError("late-disposition artifact shape is unsupported")
    declared_signer = payload.get("delivery_signer")
    if (
        payload.get("kind") != KIND
        or payload.get("repository") != repository
        or payload.get("delivery_issue_number") != delivery_issue_number
        or payload.get("pull_request_number") != pull_request_number
        or payload.get("head_sha") != head_sha.lower()
        or payload.get("validated_tree_sha") != validated_tree_sha.lower()
        or payload.get("validation_receipt_digest") != validation_receipt_digest
        or payload.get("validation_attestation_digest") != validation_attestation_digest
        or (
            manifest_mode
            and payload.get("final_eligibility_evidence_digest")
            != final_eligibility_evidence_digest
        )
        or (
            absence_mode
            and (
                payload.get("final_eligibility_status")
                != "NO_ELIGIBILITY_WAS_AUTHENTICATED_AT_FINAL_VALIDATION"
                or payload.get("final_eligibility_absence_recovery_digest")
                != final_eligibility_absence_recovery_digest
                or not isinstance(final_eligibility_absence_recovery_digest, str)
                or not DIGEST.fullmatch(final_eligibility_absence_recovery_digest)
            )
        )
        or payload.get("authorized_action") != "RESOLVE_EXACT_REVIEW_THREADS"
        or not isinstance(declared_signer, dict)
        or set(declared_signer) != {"format", "fingerprint"}
        or declared_signer
        != {
            "format": expected_signer.signature_format,
            "fingerprint": expected_signer.fingerprint,
        }
    ):
        raise LateDispositionError("late-disposition artifact binding is invalid or stale")
    threads = payload.get("threads")
    if not isinstance(threads, list) or len(threads) != 1:
        raise LateDispositionError("late-disposition thread set is malformed")
    parsed: list[ThreadAuthorization] = []
    for item in threads:
        item_keys = {
            "thread_id",
            "top_level_comment_node_id",
            "top_level_comment_database_id",
            "finding_body_digest",
            "reply_state_digest",
            "reply_count",
            "is_resolved",
            "is_outdated",
            "classification",
            "disposition",
            "technically_blocking",
            "classification_evidence_digest",
            "authorized_action",
        }
        if not isinstance(item, dict) or set(item) != item_keys:
            raise LateDispositionError("late-disposition thread entry is malformed")
        classification = item.get("classification")
        disposition = item.get("disposition")
        if (
            not isinstance(item.get("thread_id"), str)
            or not THREAD_ID.fullmatch(item["thread_id"])
            or not isinstance(item.get("top_level_comment_node_id"), str)
            or not IDENTITY.fullmatch(item["top_level_comment_node_id"])
            or not _positive_integer(item.get("top_level_comment_database_id"))
            or not isinstance(item.get("finding_body_digest"), str)
            or not DIGEST.fullmatch(item["finding_body_digest"])
            or not isinstance(item.get("reply_state_digest"), str)
            or not DIGEST.fullmatch(item["reply_state_digest"])
            or not isinstance(item.get("reply_count"), int)
            or isinstance(item.get("reply_count"), bool)
            or item["reply_count"] < 0
            or item.get("is_resolved") is not False
            or not isinstance(item.get("is_outdated"), bool)
            or classification != "INVALID_FALSE_OR_MISLEADING"
            or disposition not in allowed_dispositions.get(classification, frozenset())
            or item.get("technically_blocking") is not False
            or not isinstance(item.get("classification_evidence_digest"), str)
            or not DIGEST.fullmatch(item["classification_evidence_digest"])
            or item.get("authorized_action") != "RESOLVE_REVIEW_THREAD"
        ):
            raise LateDispositionError("late-disposition thread is ineligible")
        parsed.append(
            ThreadAuthorization(
                thread_id=item["thread_id"],
                top_level_comment_node_id=item["top_level_comment_node_id"],
                top_level_comment_database_id=item["top_level_comment_database_id"],
                finding_body_digest=item["finding_body_digest"],
                reply_state_digest=item["reply_state_digest"],
                reply_count=item["reply_count"],
                is_resolved=False,
                is_outdated=item["is_outdated"],
                classification=classification,
                disposition=disposition,
                technically_blocking=False,
                classification_evidence_digest=item["classification_evidence_digest"],
            )
        )
    observed_ids = tuple(item.thread_id for item in parsed)
    if observed_ids != thread_ids or len(observed_ids) != len(set(observed_ids)):
        raise LateDispositionError("late-disposition evidence must cover requested threads exactly")
    return LateDispositionEvidence(
        artifact_digest=hashlib.sha256(canonical).hexdigest(),
        canonical_payload=canonical,
        delivery_issue_number=delivery_issue_number,
        signer=expected_signer,
        threads=tuple(parsed),
    )


def _open_bound_output(
    path: Path, *, repository_root: Path | None = None
) -> BoundOutput:
    if path.name in {"", ".", ".."} or path != path.parent / path.name:
        raise LateDispositionError("output must use a simple filename")
    try:
        directory = path.parent.resolve(strict=True)
        repository = (
            repository_root.resolve(strict=True)
            if repository_root is not None
            else None
        )
        metadata = directory.stat()
    except (OSError, RuntimeError) as exc:
        raise LateDispositionError("late-disposition output location is unavailable") from exc
    if repository is not None and (
        directory == repository or repository in directory.parents
    ):
        raise LateDispositionError(
            "late-disposition evidence must be stored outside the delivery repository"
        )
    if metadata.st_uid != os.getuid() or metadata.st_mode & 0o077:
        raise LateDispositionError("late-disposition output directory is not private")
    flags = (
        os.O_RDONLY
        | os.O_DIRECTORY
        | os.O_CLOEXEC
        | os.O_NOFOLLOW
    )
    descriptor = -1
    try:
        descriptor = os.open(directory, flags)
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
            raise LateDispositionError("late-disposition output directory changed")
        try:
            existing = os.stat(path.name, dir_fd=descriptor, follow_symlinks=False)
        except FileNotFoundError:
            existing = None
        if existing is not None and not stat.S_ISREG(existing.st_mode):
            raise LateDispositionError("refusing to replace an unsafe output")
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        raise
    return BoundOutput(
        directory=directory,
        basename=path.name,
        descriptor=descriptor,
        device=opened.st_dev,
        inode=opened.st_ino,
    )


def _atomic_write_bound(output: BoundOutput, content: bytes) -> None:
    temporary = f".{output.basename}.{secrets.token_hex(12)}"
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | os.O_CLOEXEC
        | os.O_NOFOLLOW
    )
    descriptor = -1
    try:
        descriptor = os.open(temporary, flags, 0o600, dir_fd=output.descriptor)
        offset = 0
        while offset < len(content):
            offset += os.write(descriptor, content[offset:])
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        try:
            existing = os.stat(
                output.basename,
                dir_fd=output.descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            existing = None
        if existing is not None and not stat.S_ISREG(existing.st_mode):
            raise LateDispositionError("refusing to replace an unsafe output")
        os.replace(
            temporary,
            output.basename,
            src_dir_fd=output.descriptor,
            dst_dir_fd=output.descriptor,
        )
        try:
            os.fsync(output.descriptor)
        except OSError as exc:
            if exc.errno not in {errno.EINVAL, errno.ENOTSUP}:
                raise
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temporary, dir_fd=output.descriptor)
        except FileNotFoundError:
            pass
        raise


def _atomic_write(
    path: Path, content: bytes, *, repository_root: Path | None = None
) -> None:
    output = _open_bound_output(path, repository_root=repository_root)
    try:
        _atomic_write_bound(output, content)
    finally:
        output.close()


def sign_artifact(
    artifact: dict[str, Any],
    artifact_path: Path,
    signature_path: Path,
    *,
    signer: SignerIdentity,
    signing_key: str,
    environment: dict[str, str] | None = None,
    signature_namespace: str = SIGNATURE_NAMESPACE,
    repository_root: Path | None = None,
) -> None:
    canonical = canonical_json_bytes(artifact)
    if len(canonical) > MAXIMUM_ARTIFACT_BYTES:
        raise LateDispositionError("late-disposition artifact size is invalid")
    artifact_output = _open_bound_output(
        artifact_path, repository_root=repository_root
    )
    signature_output: BoundOutput | None = None
    try:
        signature_output = _open_bound_output(
            signature_path, repository_root=repository_root
        )
        if (
            artifact_output.device,
            artifact_output.inode,
            artifact_output.basename,
        ) == (
            signature_output.device,
            signature_output.inode,
            signature_output.basename,
        ):
            raise LateDispositionError("artifact and signature outputs must differ")
        command_environment = (
            signing_environment() if environment is None else environment
        )
        with tempfile.TemporaryDirectory(prefix="secpal-late-sign-") as directory:
            snapshot_root = Path(directory)
            os.chmod(snapshot_root, 0o700)
            temporary_artifact = snapshot_root / "artifact.json"
            temporary_signature = snapshot_root / "artifact.sig"
            _write_private_file(temporary_artifact, canonical)
            if signer.signature_format == "ssh":
                completed = _run_signature_command(
                    _trusted_executable("ssh-keygen"),
                    (
                        "-Y",
                        "sign",
                        "-f",
                        signing_key,
                        "-n",
                        signature_namespace,
                        str(temporary_artifact),
                    ),
                    environment=command_environment,
                )
                produced_signature = Path(f"{temporary_artifact}.sig")
            elif signer.signature_format == "openpgp":
                completed = _run_signature_command(
                    _trusted_executable("gpg"),
                    (
                        "--batch",
                        "--no-tty",
                        "--armor",
                        "--local-user",
                        signing_key,
                        "--output",
                        str(temporary_signature),
                        "--detach-sign",
                        str(temporary_artifact),
                    ),
                    environment=command_environment,
                )
                produced_signature = temporary_signature
            else:
                raise LateDispositionError(
                    "late-disposition signature format is unsupported"
                )
            if completed.returncode != 0 or not produced_signature.is_file():
                raise LateDispositionError("late-disposition signing failed")
            produced = _read_bounded_regular_file(
                produced_signature,
                "late-disposition signature",
                MAXIMUM_SIGNATURE_BYTES,
            )
            verify_detached_signature(
                temporary_artifact,
                produced_signature,
                signer,
                environment=command_environment,
                signature_namespace=signature_namespace,
            )
            _atomic_write_bound(artifact_output, canonical)
            _atomic_write_bound(signature_output, produced)
    finally:
        if signature_output is not None:
            signature_output.close()
        artifact_output.close()
