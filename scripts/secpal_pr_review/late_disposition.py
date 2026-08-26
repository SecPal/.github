# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Canonical detached authentication for post-push review disposition."""

from __future__ import annotations

import hashlib
import json
import os
import pwd
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


SCHEMA_VERSION = "1.0"
KIND = "LATE_FEEDBACK_DISPOSITION"
SIGNATURE_NAMESPACE = "secpal-late-feedback-disposition-v1"
MAXIMUM_ARTIFACT_BYTES = 64 * 1024
MAXIMUM_SIGNATURE_BYTES = 32 * 1024
OID = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
THREAD_ID = re.compile(r"^PRRT_[A-Za-z0-9_-]+$")
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


def _load_canonical_json(path: Path, label: str, maximum_bytes: int) -> tuple[Any, bytes]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise LateDispositionError(f"{label} is unavailable") from exc
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
) -> bytes:
    _value, canonical = _load_canonical_json(
        artifact_path, "late-disposition artifact", MAXIMUM_ARTIFACT_BYTES
    )
    try:
        signature = signature_path.read_bytes()
    except OSError as exc:
        raise LateDispositionError("late-disposition signature is unavailable") from exc
    if not signature or len(signature) > MAXIMUM_SIGNATURE_BYTES:
        raise LateDispositionError("late-disposition signature size is invalid")
    command_environment = signing_environment() if environment is None else environment
    if expected_signer.signature_format == "ssh":
        executable = _trusted_executable("ssh-keygen")
        completed = _run_signature_command(
            executable,
            (
                "-Y",
                "check-novalidate",
                "-n",
                SIGNATURE_NAMESPACE,
                "-s",
                str(signature_path.resolve(strict=True)),
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
                str(signature_path.resolve(strict=True)),
                str(artifact_path.resolve(strict=True)),
            ),
            environment=command_environment,
        )
        output = (completed.stdout + b"\n" + completed.stderr).decode(
            "utf-8", errors="replace"
        )
        if completed.returncode != 0:
            raise LateDispositionError("late-disposition OpenPGP signature is invalid")
        actual = signer_from_git_verification("openpgp", output)
    else:
        raise LateDispositionError("late-disposition signature format is unsupported")
    try:
        if (
            artifact_path.read_bytes() != canonical
            or signature_path.read_bytes() != signature
        ):
            raise LateDispositionError(
                "late-disposition evidence changed during signature verification"
            )
    except OSError as exc:
        raise LateDispositionError(
            "late-disposition evidence changed during signature verification"
        ) from exc
    if actual != expected_signer:
        raise LateDispositionError("late-disposition signer does not match final delivery signer")
    return canonical


def _positive_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


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
    final_eligibility_evidence_digest: str,
    thread_ids: tuple[str, ...],
    allowed_dispositions: dict[str, frozenset[str]],
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
    expected_keys = {
        "schema_version",
        "kind",
        "repository",
        "delivery_issue_number",
        "pull_request_number",
        "head_sha",
        "validated_tree_sha",
        "validation_receipt_digest",
        "validation_attestation_digest",
        "final_eligibility_evidence_digest",
        "delivery_signer",
        "authorized_action",
        "threads",
    }
    if not isinstance(payload, dict) or set(payload) != expected_keys:
        raise LateDispositionError("late-disposition artifact shape is unsupported")
    declared_signer = payload.get("delivery_signer")
    if (
        payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("kind") != KIND
        or payload.get("repository") != repository
        or payload.get("delivery_issue_number") != delivery_issue_number
        or payload.get("pull_request_number") != pull_request_number
        or payload.get("head_sha") != head_sha.lower()
        or payload.get("validated_tree_sha") != validated_tree_sha.lower()
        or payload.get("validation_receipt_digest") != validation_receipt_digest
        or payload.get("validation_attestation_digest") != validation_attestation_digest
        or payload.get("final_eligibility_evidence_digest")
        != final_eligibility_evidence_digest
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
            or not item["top_level_comment_node_id"]
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


def _atomic_write(path: Path, content: bytes) -> None:
    parent = path.parent.resolve(strict=True)
    if path.exists() and path.is_symlink():
        raise LateDispositionError("refusing to replace a symlink output")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def sign_artifact(
    artifact: dict[str, Any],
    artifact_path: Path,
    signature_path: Path,
    *,
    signer: SignerIdentity,
    signing_key: str,
    environment: dict[str, str] | None = None,
) -> None:
    if artifact_path.resolve() == signature_path.resolve():
        raise LateDispositionError("artifact and signature outputs must differ")
    canonical = canonical_json_bytes(artifact)
    if len(canonical) > MAXIMUM_ARTIFACT_BYTES:
        raise LateDispositionError("late-disposition artifact size is invalid")
    command_environment = signing_environment() if environment is None else environment
    parent = artifact_path.parent.resolve(strict=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".late-disposition.", dir=parent)
    os.close(descriptor)
    temporary_artifact = Path(temporary_name)
    temporary_signature = Path(f"{temporary_name}.sig")
    try:
        temporary_artifact.write_bytes(canonical)
        if signer.signature_format == "ssh":
            completed = _run_signature_command(
                _trusted_executable("ssh-keygen"),
                (
                    "-Y",
                    "sign",
                    "-f",
                    signing_key,
                    "-n",
                    SIGNATURE_NAMESPACE,
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
            raise LateDispositionError("late-disposition signature format is unsupported")
        if completed.returncode != 0 or not produced_signature.is_file():
            raise LateDispositionError("late-disposition signing failed")
        verify_detached_signature(
            temporary_artifact,
            produced_signature,
            signer,
            environment=command_environment,
        )
        _atomic_write(artifact_path, canonical)
        _atomic_write(signature_path, produced_signature.read_bytes())
    finally:
        temporary_artifact.unlink(missing_ok=True)
        temporary_signature.unlink(missing_ok=True)
        Path(f"{temporary_artifact}.sig").unlink(missing_ok=True)
