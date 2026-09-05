# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Authenticate exact implementation sources admitted by accepted-main policy.

The #810 subtype retains its exact isolated execution boundary.  Byte-only
subtypes expose no entrypoint or execution mechanism.  Lifecycle orchestration
and signed one-use transition authorization remain the sole mutation authority.
"""

from __future__ import annotations

import ast
from contextlib import contextmanager
import copy
from dataclasses import dataclass
import importlib.util
import json
import os
from pathlib import Path
import re
import selectors
import subprocess
import sys
import tempfile
import time
from typing import Any, Iterator, Mapping

from . import fast_path
from . import late_disposition
from . import lifecycle_authority as authority
from . import lifecycle_publication as publication


ADMISSION_KIND = "BOOTSTRAP_SOURCE_ADMISSION"
ADMISSION_SUBTYPE = "FIRST_READY_EXECUTOR_BOOTSTRAP_SOURCE"
PURPOSE = "FIRST_READY_EXECUTOR_BOOTSTRAP"
IMPLEMENTATION_PATH = "scripts/secpal_pr_review/lifecycle_execution.py"
ENTRYPOINT = "execute_lifecycle_transition"
EVIDENCE_HELPER_ADMISSION_SUBTYPE = "PR_REVIEW_EVIDENCE_HELPER_SOURCE"
EVIDENCE_HELPER_PURPOSE = "PR_REVIEW_EVIDENCE_HELPER_SOURCE_ADMISSION"
EVIDENCE_HELPER_IMPLEMENTATION_PATH = "scripts/secpal-pr-review.py"
ACCEPTED_MAIN_POLICY_SOURCE = "ACCEPTED_MAIN_REPOSITORY_REGISTRY"
PROTECTED_MAIN_REPOSITORY = "SecPal/.github"
PROTECTED_MAIN_DEFAULT_BRANCH = "main"
PROTECTED_MAIN_REMOTE_URL = "https://github.com/SecPal/.github.git"
PROTECTED_MAIN_REGISTRY_PATH = (
    ".agents/skills/secpal-pr-review/references/repositories.json"
)
_ADMISSION_HELPER = Path(__file__).resolve().parents[1] / "secpal-pr-review-actions.py"
_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
_DIGEST = re.compile(r"[0-9a-f]{64}")
_VERIFIED_SOURCE = object()
MAXIMUM_EVIDENCE_BYTES = late_disposition.MAXIMUM_ARTIFACT_BYTES
_BOOTSTRAP_COMMAND_TIMEOUT_SECONDS = 30
_BOOTSTRAP_COMMAND_DIRECTORIES = (
    Path("/usr/bin"),
    Path("/bin"),
    Path("/usr/local/bin"),
    Path("/opt/homebrew/bin"),
    Path("/opt/local/bin"),
)
_BOOTSTRAP_COMMAND_PATH = os.pathsep.join(
    str(path) for path in _BOOTSTRAP_COMMAND_DIRECTORIES
)
_BOOTSTRAP_GIT_CONFIG = (
    ("core.fsmonitor", "false"),
    ("gpg.program", "gpg"),
    ("gpg.openpgp.program", "gpg"),
    ("gpg.ssh.program", "ssh-keygen"),
    ("gpg.x509.program", "gpgsm"),
)
SOURCE_ADMISSION_FAILURE = "SOURCE_ADMISSION_FAILURE"
HISTORICAL_EVIDENCE_PRESENT = "HISTORICAL_EVIDENCE_PRESENT"
HISTORICAL_EVIDENCE_RECOVERY = (
    "HISTORICAL_EVIDENCE_UNAVAILABLE_BUT_EXACT_RECOVERY_AUTHORIZED"
)
_EXECUTION_DIAGNOSTIC_IDENTITIES = frozenset(
    {
        "AUTHORIZATION_ORCHESTRATION_FAILURE",
        "CURRENT_OBSERVATION_VERIFICATION_FAILURE",
        "GITHUB_OBSERVATION_FAILURE",
        "GITHUB_MUTATION_READBACK_FAILURE",
        "SIGNING_SUCCESSOR_DERIVATION_FAILURE",
        "LIFECYCLE_PUBLICATION_FAILURE",
        "FINAL_CONVERGENCE_FAILURE",
        "UNEXPECTED_CLOSED_CHILD_FAILURE",
    }
)
_DIAGNOSTIC_EXECUTOR_BLOB_OID = "4cfd9eb73a522224f9dfca4176d1aad386b81d50"
_PROTECTED_MAIN_QUERY = """query($owner:String!,$name:String!){
  repository(owner:$owner,name:$name){
    nameWithOwner
    defaultBranchRef{name target{... on Commit{oid}}}
  }
}"""
_DIAGNOSTIC_RAISE_SITES = (
    (("classify_observed_state", 97), "AUTHORIZATION_ORCHESTRATION_FAILURE"),
    (("classify_observed_state", 99), "AUTHORIZATION_ORCHESTRATION_FAILURE"),
    (("_validate_live_pull_request", 117), "GITHUB_OBSERVATION_FAILURE"),
    (("_validate_live_pull_request", 125), "GITHUB_OBSERVATION_FAILURE"),
    (("_validate_live_pull_request", 133), "GITHUB_OBSERVATION_FAILURE"),
    (("_authenticate_predecessor_decision", 185), "AUTHORIZATION_ORCHESTRATION_FAILURE"),
    (("_authenticate_predecessor_decision", 197), "AUTHORIZATION_ORCHESTRATION_FAILURE"),
    (("_validate_transition_delta", 232), "CURRENT_OBSERVATION_VERIFICATION_FAILURE"),
    (("_validate_transition_delta", 253), "CURRENT_OBSERVATION_VERIFICATION_FAILURE"),
    (("_authenticate_target", 269), "CURRENT_OBSERVATION_VERIFICATION_FAILURE"),
    (("_authenticate_target", 277), "CURRENT_OBSERVATION_VERIFICATION_FAILURE"),
    (("_append_successor_evidence", 304), "CURRENT_OBSERVATION_VERIFICATION_FAILURE"),
    (("_append_successor_evidence", 388), "SIGNING_SUCCESSOR_DERIVATION_FAILURE"),
    (("_append_successor_evidence", 404), "SIGNING_SUCCESSOR_DERIVATION_FAILURE"),
    (("_single_role_identity", 410), "SIGNING_SUCCESSOR_DERIVATION_FAILURE"),
    (("_local_signer", 419), "SIGNING_SUCCESSOR_DERIVATION_FAILURE"),
    (("sign", 447), "SIGNING_SUCCESSOR_DERIVATION_FAILURE"),
    (("sign", 451), "SIGNING_SUCCESSOR_DERIVATION_FAILURE"),
    (("sign", 453), "SIGNING_SUCCESSOR_DERIVATION_FAILURE"),
    (("_production_signing_authorities", 469), "SIGNING_SUCCESSOR_DERIVATION_FAILURE"),
    (("_production_signing_authorities", 480), "AUTHORIZATION_ORCHESTRATION_FAILURE"),
    (("_read_live_github", 505), "GITHUB_OBSERVATION_FAILURE"),
    (("_read_live_github", 511), "GITHUB_OBSERVATION_FAILURE"),
    (("_read_live_github", 519), "GITHUB_OBSERVATION_FAILURE"),
    (("_read_live_github", 529), "GITHUB_OBSERVATION_FAILURE"),
    (("_write_live_github", 541), "GITHUB_MUTATION_READBACK_FAILURE"),
    (("_execute_lifecycle_transition", 592), "AUTHORIZATION_ORCHESTRATION_FAILURE"),
    (("_execute_lifecycle_transition", 597), "AUTHORIZATION_ORCHESTRATION_FAILURE"),
    (("_execute_lifecycle_transition", 615), "CURRENT_OBSERVATION_VERIFICATION_FAILURE"),
    (("_execute_lifecycle_transition", 629), "FINAL_CONVERGENCE_FAILURE"),
    (("_execute_lifecycle_transition", 640), "CURRENT_OBSERVATION_VERIFICATION_FAILURE"),
    (("_execute_lifecycle_transition", 652), "GITHUB_MUTATION_READBACK_FAILURE"),
    (("_execute_lifecycle_transition", 661), "GITHUB_MUTATION_READBACK_FAILURE"),
    (("_execute_lifecycle_transition", 678), "GITHUB_MUTATION_READBACK_FAILURE"),
    (("_execute_lifecycle_transition", 682), "CURRENT_OBSERVATION_VERIFICATION_FAILURE"),
    (("_execute_lifecycle_transition", 692), "GITHUB_MUTATION_READBACK_FAILURE"),
    (("_execute_lifecycle_transition", 697), "CURRENT_OBSERVATION_VERIFICATION_FAILURE"),
    (("_execute_lifecycle_transition", 707), "GITHUB_MUTATION_READBACK_FAILURE"),
    (("_execute_lifecycle_transition", 744), "LIFECYCLE_PUBLICATION_FAILURE"),
    (("_execute_lifecycle_transition", 758), "FINAL_CONVERGENCE_FAILURE"),
)
_LAUNCHER_TEMPLATE = r"""
import dataclasses
import hashlib
import json
from pathlib import Path
import sys

RAISE_SITES = __SECPAL_DIAGNOSTIC_RAISE_SITES__
EXPECTED_BLOB = "4cfd9eb73a522224f9dfca4176d1aad386b81d50"

def diagnostic_identity(error, lifecycle_execution, expected):
    if (
        lifecycle_execution is None
        or type(error) is not lifecycle_execution.LifecycleExecutionError
    ):
        return "UNEXPECTED_CLOSED_CHILD_FAILURE"
    traceback = error.__traceback__
    executor_sites = []
    while traceback is not None:
        frame = traceback.tb_frame
        if frame.f_code.co_filename == str(expected):
            executor_sites.append((frame.f_code.co_name, traceback.tb_lineno))
        traceback = traceback.tb_next
    if executor_sites:
        return RAISE_SITES.get(executor_sites[-1], "UNEXPECTED_CLOSED_CHILD_FAILURE")
    return "UNEXPECTED_CLOSED_CHILD_FAILURE"

lifecycle_execution = None
expected = None
try:
    source_root = Path(sys.argv[1]).resolve(strict=True)
    expected = source_root / "scripts/secpal_pr_review/lifecycle_execution.py"
    raw = expected.read_bytes()
    header = f"blob {len(raw)}\0".encode("ascii")
    if hashlib.sha1(header + raw).hexdigest() != EXPECTED_BLOB:
        raise RuntimeError("admitted lifecycle executor blob changed")
    stdlib = [value for value in sys.path if value and "site-packages" not in value]
    sys.path[:] = [str(source_root), *stdlib]
    from scripts.secpal_pr_review import lifecycle_execution

    if Path(lifecycle_execution.__file__).resolve(strict=True) != expected:
        raise RuntimeError("admitted lifecycle executor import was substituted")
    for name, module in tuple(sys.modules.items()):
        if name.startswith("scripts.secpal_pr_review"):
            location = getattr(module, "__file__", None)
            if location is not None and source_root not in Path(location).resolve(strict=True).parents:
                raise RuntimeError("admitted sibling import escaped the authenticated tree")
    authorization = sys.stdin.buffer.read()
    result = lifecycle_execution.execute_lifecycle_transition(
        "SecPal/.github", 810, authorization
    )
except Exception as error:
    payload = {
        "diagnostic_identity": diagnostic_identity(error, lifecycle_execution, expected),
        "status": "REJECTED",
    }
    sys.stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    raise SystemExit(70)
else:
    payload = dataclasses.asdict(result) if dataclasses.is_dataclass(result) else result
    sys.stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
"""
_LAUNCHER = _LAUNCHER_TEMPLATE.replace(
    "__SECPAL_DIAGNOSTIC_RAISE_SITES__", repr(dict(_DIAGNOSTIC_RAISE_SITES))
)


class BootstrapSourceAdmissionError(ValueError):
    """The exact maintained implementation source cannot be authenticated."""

    def __init__(
        self, message: str, *, diagnostic_identity: str = SOURCE_ADMISSION_FAILURE
    ) -> None:
        super().__init__(message)
        self.diagnostic_identity = diagnostic_identity


@dataclass(frozen=True)
class GitHubSourceObservation:
    """Provider representation captured without deciding policy conformance."""

    pull_request_json: bytes
    commit_json: bytes


@dataclass(frozen=True)
class ProtectedMainObservation:
    """One provider representation of the registered default-branch tip."""

    repository_json: bytes


@dataclass(frozen=True)
class ProtectedMainFacts:
    """Canonical protected-main identity derived from one provider read."""

    repository: str
    default_branch: str
    head_sha: str


@dataclass(frozen=True)
class GitHubSourceFacts:
    """Canonical source facts produced by pure representation normalization."""

    base_repository: str
    base_ref: str
    head_repository: str
    pull_request: int
    state: str
    draft: bool
    head_sha: str
    commit_sha: str
    tree_sha: str
    parent_shas: tuple[str, ...]
    github_verified: bool
    github_verification_reason: str


@dataclass(frozen=True)
class RecoveryReviewFacts:
    """Canonical bounded live review state for the exact recovery source."""

    repository: str
    pull_request: int
    head_sha: str
    base_ref: str
    state: str
    review_decision: str
    feedback_inventory_digest: str
    conversation_comment_count: int
    review_thread_count: int
    resolved_review_thread_count: int


@dataclass(frozen=True)
class VerifiedBootstrapSource:
    """Stable source facts exposed only after complete accepted-main checks."""

    repository: str
    delivery_issue: int
    pull_request: int
    head_sha: str
    tree_sha: str
    parent_sha: str
    validation_receipt_digest: str
    final_attestation_digest: str
    signer_identity: str
    implementation_path: str
    implementation_blob_oid: str
    entrypoint: str | None
    purpose: str
    policy_source: str | None
    admission_digest: str
    historical_evidence_status: str
    recovery_authority_digest: str | None
    recovery_validation_digest: str | None
    recovery_technical_security_gate_digest: str | None
    _verification_seal: object


def is_verified_bootstrap_source(value: Any) -> bool:
    return (
        isinstance(value, VerifiedBootstrapSource)
        and value._verification_seal is _VERIFIED_SOURCE
    )


def _load_actions_helper() -> Any:
    module_name = "secpal_bootstrap_source_accepted_main_actions"
    loaded = sys.modules.get(module_name)
    if loaded is not None:
        if Path(getattr(loaded, "__file__", "")).resolve() != _ADMISSION_HELPER:
            raise BootstrapSourceAdmissionError(
                "accepted-main validation helper path was substituted"
            )
        return loaded
    spec = importlib.util.spec_from_file_location(module_name, _ADMISSION_HELPER)
    if spec is None or spec.loader is None:
        raise BootstrapSourceAdmissionError(
            "accepted-main validation helper is unavailable"
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException as exc:
        sys.modules.pop(module_name, None)
        raise BootstrapSourceAdmissionError(
            "accepted-main validation helper could not be loaded"
        ) from exc
    return module


def _select_policy_from_trust(
    trust: authority.LifecycleTrustPolicy,
    repository: str,
    delivery_issue: int,
    subtype: str,
    purpose: str,
) -> tuple[authority.LifecycleTrustPolicy, authority.BootstrapSourceAdmissionPolicy]:
    matches = [
        item
        for item in trust.bootstrap_source_admissions
        if item.repository == repository
        and item.delivery_issue == delivery_issue
        and item.subtype == subtype
        and item.purpose == purpose
    ]
    if len(matches) != 1:
        raise BootstrapSourceAdmissionError(
            "bootstrap source admission is not uniquely maintained"
        )
    return trust, matches[0]


def _select_policy(
    repository: str, delivery_issue: int
) -> tuple[authority.LifecycleTrustPolicy, authority.BootstrapSourceAdmissionPolicy]:
    """Select only the historical #810 policy from the installed registry."""

    try:
        repository = authority._require_repository(repository)
        delivery_issue = authority._require_positive_int(
            delivery_issue, "bootstrap delivery issue"
        )
        trust = authority._load_lifecycle_trust_policy(repository)
    except authority.LifecycleAuthorityError as exc:
        raise BootstrapSourceAdmissionError(str(exc)) from exc
    return _select_policy_from_trust(
        trust, repository, delivery_issue, ADMISSION_SUBTYPE, PURPOSE
    )


def _closed_json(value: bytes | str, label: str) -> dict[str, Any]:
    try:
        parsed = authority.loads_closed_json(
            value.encode("utf-8") if isinstance(value, str) else value
        )
    except (
        AttributeError,
        TypeError,
        UnicodeEncodeError,
        json.JSONDecodeError,
        authority.LifecycleAuthorityError,
    ) as exc:
        raise BootstrapSourceAdmissionError(f"{label} is malformed") from exc
    if not isinstance(parsed, dict):
        raise BootstrapSourceAdmissionError(f"{label} is malformed")
    return parsed


def _read_evidence(directory: Path | str) -> tuple[dict[str, Any], ...]:
    try:
        root = Path(directory).resolve(strict=True)
    except (OSError, RuntimeError, TypeError) as exc:
        raise BootstrapSourceAdmissionError("source evidence directory is unavailable") from exc
    if not root.is_dir():
        raise BootstrapSourceAdmissionError("source evidence directory is unavailable")
    values: list[dict[str, Any]] = []
    for filename, label in (
        ("reviewed-state.json", "reviewed-state evidence"),
        ("validation-receipt.json", "validation receipt"),
        ("final-attestation.json", "final attestation"),
    ):
        try:
            raw = late_disposition._read_bounded_regular_file(
                root / filename, label, MAXIMUM_EVIDENCE_BYTES
            )
        except late_disposition.LateDispositionError as exc:
            raise BootstrapSourceAdmissionError(str(exc)) from exc
        values.append(_closed_json(raw, label))
    return tuple(values)


def _resolve_bootstrap_executable(name: str) -> str:
    """Resolve the two pre-authentication tools without importing candidate code."""

    if name not in {"git", "gh"}:
        raise BootstrapSourceAdmissionError(
            "bootstrap source-admission executable is not allowlisted"
        )
    for directory in _BOOTSTRAP_COMMAND_DIRECTORIES:
        candidate = directory / name
        try:
            resolved = candidate.resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        if resolved.is_file() and os.access(resolved, os.X_OK):
            return str(resolved)
    raise BootstrapSourceAdmissionError(
        "bootstrap source-admission executable is unavailable"
    )


def _bootstrap_command_environment(name: str, root: Path | None) -> dict[str, str]:
    if name not in {"git", "gh"}:
        raise BootstrapSourceAdmissionError(
            "bootstrap source-admission executable is not allowlisted"
        )
    environment = {
        "PATH": _BOOTSTRAP_COMMAND_PATH,
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PAGER": "cat",
    }
    if name == "gh":
        environment.update({"GH_PAGER": "cat", "GH_HOST": "github.com"})
        for key in ("HOME", "GH_CONFIG_DIR", "GH_TOKEN", "GITHUB_TOKEN"):
            value = os.environ.get(key)
            if value is not None:
                environment[key] = value
        return environment
    if root is None:
        raise BootstrapSourceAdmissionError(
            "bootstrap Git repository root is unavailable"
        )
    environment.update(
        {
            "HOME": str(root),
            "GIT_PAGER": "cat",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_NO_LAZY_FETCH": "1",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_CONFIG_COUNT": str(len(_BOOTSTRAP_GIT_CONFIG)),
        }
    )
    for index, (key, value) in enumerate(_BOOTSTRAP_GIT_CONFIG):
        environment[f"GIT_CONFIG_KEY_{index}"] = key
        environment[f"GIT_CONFIG_VALUE_{index}"] = value
    return environment


def _stop_bootstrap_child(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is None:
        try:
            process.terminate()
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            process.wait()
    else:
        process.wait()


def _run_bootstrap_command(
    name: str,
    arguments: list[str],
    *,
    root: Path | None = None,
    input_bytes: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    """Run one closed command while bounding both output streams during capture."""

    executable = _resolve_bootstrap_executable(name)
    if not isinstance(arguments, list) or not all(
        isinstance(value, str) for value in arguments
    ):
        raise BootstrapSourceAdmissionError(
            "bootstrap source-admission command is malformed"
        )
    if input_bytes is not None and (
        not isinstance(input_bytes, bytes) or len(input_bytes) > MAXIMUM_EVIDENCE_BYTES
    ):
        raise BootstrapSourceAdmissionError(
            "bootstrap source-admission input has invalid size"
        )
    command = [executable]
    if name == "git":
        if root is None:
            raise BootstrapSourceAdmissionError(
                "bootstrap Git repository root is unavailable"
            )
        try:
            root = root.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise BootstrapSourceAdmissionError(
                "bootstrap Git repository root is unavailable"
            ) from exc
        command.extend(["-C", str(root)])
    command.extend(arguments)
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=None,
            env=_bootstrap_command_environment(name, root),
        )
    except OSError as exc:
        raise BootstrapSourceAdmissionError(
            "bootstrap source-admission command failed"
        ) from exc
    selector = selectors.DefaultSelector()
    stdout: list[bytes] = []
    stderr: list[bytes] = []
    sizes = {"stdout": 0, "stderr": 0}
    pending_input = memoryview(input_bytes or b"")
    try:
        assert process.stdout is not None and process.stderr is not None
        for label, stream in (("stdout", process.stdout), ("stderr", process.stderr)):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, label)
        if process.stdin is not None:
            os.set_blocking(process.stdin.fileno(), False)
            if pending_input:
                selector.register(process.stdin, selectors.EVENT_WRITE, "stdin")
            else:
                process.stdin.close()
        deadline = time.monotonic() + _BOOTSTRAP_COMMAND_TIMEOUT_SECONDS
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _stop_bootstrap_child(process)
                raise BootstrapSourceAdmissionError(
                    "bootstrap source-admission command timed out"
                )
            events = selector.select(min(remaining, 0.1))
            if not events and process.poll() is not None:
                if process.stdin is not None and not process.stdin.closed:
                    try:
                        selector.unregister(process.stdin)
                    except KeyError:
                        pass
                    process.stdin.close()
                events = [
                    (key, selectors.EVENT_READ)
                    for key in tuple(selector.get_map().values())
                    if key.data != "stdin"
                ]
            for key, _mask in events:
                stream = key.fileobj
                label = key.data
                if label == "stdin":
                    try:
                        written = os.write(stream.fileno(), pending_input)
                    except BlockingIOError:
                        continue
                    except BrokenPipeError:
                        written = len(pending_input)
                    pending_input = pending_input[written:]
                    if not pending_input:
                        selector.unregister(stream)
                        stream.close()
                    continue
                remaining_capacity = MAXIMUM_EVIDENCE_BYTES - sizes[label]
                try:
                    chunk = os.read(stream.fileno(), min(65536, remaining_capacity + 1))
                except BlockingIOError:
                    continue
                if not chunk:
                    selector.unregister(stream)
                    stream.close()
                    continue
                if len(chunk) > remaining_capacity:
                    _stop_bootstrap_child(process)
                    raise BootstrapSourceAdmissionError(
                        "bootstrap source-admission output limit exceeded"
                    )
                sizes[label] += len(chunk)
                (stdout if label == "stdout" else stderr).append(chunk)
        try:
            returncode = process.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired as exc:
            _stop_bootstrap_child(process)
            raise BootstrapSourceAdmissionError(
                "bootstrap source-admission command timed out"
            ) from exc
        return subprocess.CompletedProcess(
            command, returncode, b"".join(stdout), b"".join(stderr)
        )
    finally:
        selector.close()
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None and not stream.closed:
                stream.close()
        if process.poll() is None:
            _stop_bootstrap_child(process)


def _run_bootstrap_git(
    root: Path,
    arguments: list[str],
    *,
    input_bytes: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    return _run_bootstrap_command(
        "git", arguments, root=root, input_bytes=input_bytes
    )


def _run_bootstrap_gh(arguments: list[str]) -> subprocess.CompletedProcess[bytes]:
    return _run_bootstrap_command("gh", arguments)


def _git(
    root: Path,
    arguments: list[str],
    *,
    input_bytes: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    result = _run_bootstrap_git(root, arguments, input_bytes=input_bytes)
    if result.returncode != 0:
        raise BootstrapSourceAdmissionError("immutable source Git operation failed")
    return result


def _git_text(root: Path, arguments: list[str]) -> str:
    try:
        return _git(root, arguments).stdout.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise BootstrapSourceAdmissionError("immutable source Git output is malformed") from exc


def _observe_protected_main() -> ProtectedMainObservation:
    """Read the registered default-branch tip once through the trusted gh boundary."""

    result = _run_bootstrap_gh(
        [
            "api",
            "--hostname",
            "github.com",
            "graphql",
            "-f",
            f"query={_PROTECTED_MAIN_QUERY}",
            "-f",
            "owner=SecPal",
            "-f",
            "name=.github",
        ]
    )
    if result.returncode != 0:
        raise BootstrapSourceAdmissionError(
            "protected-main GitHub authority is unavailable"
        )
    return ProtectedMainObservation(repository_json=bytes(result.stdout))


def _normalize_protected_main(
    observation: ProtectedMainObservation,
) -> ProtectedMainFacts:
    """Normalize one closed default-branch representation without admitting it."""

    if not isinstance(observation, ProtectedMainObservation):
        raise BootstrapSourceAdmissionError("protected-main authority is malformed")
    try:
        document = json.loads(
            observation.repository_json,
            object_pairs_hook=publication._reject_duplicate_pairs,
        )
        if not isinstance(document, dict) or set(document) != {"data"}:
            raise BootstrapSourceAdmissionError("protected-main authority is malformed")
        data = document["data"]
        repository = data["repository"]
        default_branch = repository["defaultBranchRef"]
        target = default_branch["target"]
        if (
            not isinstance(data, dict)
            or set(data) != {"repository"}
            or not isinstance(repository, dict)
            or set(repository) != {"nameWithOwner", "defaultBranchRef"}
            or not isinstance(default_branch, dict)
            or set(default_branch) != {"name", "target"}
            or not isinstance(target, dict)
            or set(target) != {"oid"}
        ):
            raise BootstrapSourceAdmissionError("protected-main authority is malformed")
        facts = ProtectedMainFacts(
            repository=authority._require_repository(repository["nameWithOwner"]),
            default_branch=default_branch["name"],
            head_sha=authority._require_oid(target["oid"], "protected-main head"),
        )
    except BootstrapSourceAdmissionError:
        raise
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        authority.LifecycleAuthorityError,
        publication.LifecyclePublicationError,
    ) as exc:
        raise BootstrapSourceAdmissionError(
            "protected-main authority is malformed"
        ) from exc
    if (
        facts.repository != PROTECTED_MAIN_REPOSITORY
        or facts.default_branch != PROTECTED_MAIN_DEFAULT_BRANCH
    ):
        raise BootstrapSourceAdmissionError(
            "protected-main repository or default branch changed"
        )
    return facts


def _read_protected_main_registry(main_oid: str) -> bytes:
    """Read the registry blob from one independently observed immutable commit."""

    try:
        main_oid = authority._require_oid(main_oid, "protected-main head")
    except authority.LifecycleAuthorityError as exc:
        raise BootstrapSourceAdmissionError(str(exc)) from exc
    with tempfile.TemporaryDirectory(
        prefix="secpal-protected-main-policy-"
    ) as directory:
        root = Path(directory).resolve()
        root.chmod(0o700)
        _git(root, ["init", "--quiet"])
        _git(root, ["remote", "add", "origin", PROTECTED_MAIN_REMOTE_URL])
        _git(
            root,
            ["fetch", "--quiet", "--no-tags", "--depth=1", "origin", main_oid],
        )
        fetched = _git_text(root, ["rev-parse", "FETCH_HEAD"]).strip()
        if fetched != main_oid:
            raise BootstrapSourceAdmissionError(
                "protected-main object substitution detected"
            )
        record = _git_text(
            root,
            [
                "ls-tree",
                "-z",
                "--full-tree",
                main_oid,
                "--",
                f":(literal){PROTECTED_MAIN_REGISTRY_PATH}",
            ],
        )
        if not record.endswith("\x00") or record.count("\x00") != 1:
            raise BootstrapSourceAdmissionError(
                "protected-main repository registry is unavailable"
            )
        metadata, separator, path = record[:-1].partition("\t")
        fields = metadata.split()
        if (
            separator != "\t"
            or path != PROTECTED_MAIN_REGISTRY_PATH
            or len(fields) != 3
            or fields[0] not in {"100644", "100755"}
            or fields[1] != "blob"
            or not _OID.fullmatch(fields[2])
        ):
            raise BootstrapSourceAdmissionError(
                "protected-main repository registry is not a regular blob"
            )
        raw = _git(root, ["cat-file", "blob", fields[2]]).stdout
        if not raw or len(raw) > MAXIMUM_EVIDENCE_BYTES:
            raise BootstrapSourceAdmissionError(
                "protected-main repository registry has invalid size"
            )
        return bytes(raw)


def _load_protected_main_trust_policy(
    repository: str,
) -> authority.LifecycleTrustPolicy:
    """Load policy only from the independently observed immutable main object."""

    try:
        repository = authority._require_repository(repository)
    except authority.LifecycleAuthorityError as exc:
        raise BootstrapSourceAdmissionError(str(exc)) from exc
    if repository != PROTECTED_MAIN_REPOSITORY:
        raise BootstrapSourceAdmissionError(
            "protected-main source admission has a fixed repository"
        )
    facts = _normalize_protected_main(_observe_protected_main())
    if facts.repository != repository:
        raise BootstrapSourceAdmissionError(
            "protected-main repository observation changed"
        )
    registry_document = _read_protected_main_registry(facts.head_sha)
    try:
        trust = authority._parse_lifecycle_trust_policy(
            registry_document, repository
        )
    except authority.LifecycleAuthorityError as exc:
        raise BootstrapSourceAdmissionError(
            "protected-main repository registry is invalid"
        ) from exc
    if trust.publication_remote_url != PROTECTED_MAIN_REMOTE_URL:
        raise BootstrapSourceAdmissionError(
            "protected-main source repository changed"
        )
    return trust


def _select_evidence_helper_policy(
    repository: str, delivery_issue: int
) -> tuple[authority.LifecycleTrustPolicy, authority.BootstrapSourceAdmissionPolicy]:
    """Select the byte-only admission solely from authenticated protected main."""

    try:
        repository = authority._require_repository(repository)
        delivery_issue = authority._require_positive_int(
            delivery_issue, "bootstrap delivery issue"
        )
    except authority.LifecycleAuthorityError as exc:
        raise BootstrapSourceAdmissionError(str(exc)) from exc
    trust = _load_protected_main_trust_policy(repository)
    return _select_policy_from_trust(
        trust,
        repository,
        delivery_issue,
        EVIDENCE_HELPER_ADMISSION_SUBTYPE,
        EVIDENCE_HELPER_PURPOSE,
    )


def _verify_materialized_tree(
    root: Path, policy: authority.BootstrapSourceAdmissionPolicy
) -> None:
    head = _git_text(root, ["rev-parse", "HEAD"]).strip()
    tree = _git_text(root, ["rev-parse", "HEAD^{tree}"]).strip()
    status = _git_text(
        root, ["status", "--porcelain=v2", "--untracked-files=all"]
    )
    if head != policy.source_head_sha or tree != policy.source_tree_sha or status:
        raise BootstrapSourceAdmissionError(
            "materialized source differs from the authenticated immutable tree"
        )


def _allowed_signers(root: Path, trust: authority.LifecycleTrustPolicy, identity: str) -> Path:
    signer = trust.signers.get(identity)
    if signer is None or not signer.ssh_public_keys:
        raise BootstrapSourceAdmissionError("source signer has no maintained SSH key")
    path = root / ".git" / "accepted-source-signers"
    path.write_text(
        "".join(f"{identity} {key}\n" for key in signer.ssh_public_keys),
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path


def _verify_commit_signature(
    root: Path,
    trust: authority.LifecycleTrustPolicy,
    policy: authority.BootstrapSourceAdmissionPolicy,
) -> None:
    allowed = _allowed_signers(root, trust, policy.source_signer_identity)
    result = _run_bootstrap_git(
        root,
        [
            "-c", f"gpg.ssh.allowedSignersFile={allowed}",
            "verify-commit", "--raw", policy.source_head_sha,
        ],
    )
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    principals = re.findall(r'(?m)^Good "git" signature for ([^\r\n]+) with ', output)
    if result.returncode != 0 or principals != [policy.source_signer_identity]:
        raise BootstrapSourceAdmissionError(
            "source commit signature or maintained signer binding is invalid"
        )


def _observe_github(
    policy: authority.BootstrapSourceAdmissionPolicy,
) -> GitHubSourceObservation:
    """Capture the exact provider representations without admitting them."""

    pr_result = _run_bootstrap_gh(
        ["api", "--hostname", "github.com", f"repos/{policy.repository}/pulls/{policy.pull_request}"]
    )
    commit_result = _run_bootstrap_gh(
        ["api", "--hostname", "github.com", f"repos/{policy.repository}/commits/{policy.source_head_sha}"]
    )
    if pr_result.returncode != 0 or commit_result.returncode != 0:
        raise BootstrapSourceAdmissionError("source GitHub authority is unavailable")
    return GitHubSourceObservation(
        pull_request_json=bytes(pr_result.stdout),
        commit_json=bytes(commit_result.stdout),
    )


def _normalize_github_observation(
    observation: GitHubSourceObservation,
) -> GitHubSourceFacts:
    """Purely normalize a bounded GitHub representation into canonical facts."""

    if not isinstance(observation, GitHubSourceObservation):
        raise BootstrapSourceAdmissionError("source GitHub authority is malformed")
    try:
        pull = json.loads(
            observation.pull_request_json,
            object_pairs_hook=publication._reject_duplicate_pairs,
        )
        commit = json.loads(
            observation.commit_json,
            object_pairs_hook=publication._reject_duplicate_pairs,
        )
        facts = GitHubSourceFacts(
            base_repository=authority._require_repository(
                pull["base"]["repo"]["full_name"]
            ),
            base_ref=pull["base"]["ref"],
            head_repository=authority._require_repository(
                pull["head"]["repo"]["full_name"]
            ),
            pull_request=authority._require_positive_int(
                pull["number"], "source pull request"
            ),
            state=pull["state"].upper(),
            draft=pull["draft"],
            head_sha=authority._require_oid(pull["head"]["sha"], "source head"),
            commit_sha=authority._require_oid(commit["sha"], "source commit"),
            tree_sha=authority._require_oid(
                commit["commit"]["tree"]["sha"], "source tree"
            ),
            parent_shas=tuple(
                authority._require_oid(item["sha"], "source parent")
                for item in commit["parents"]
            ),
            github_verified=commit["commit"]["verification"]["verified"],
            github_verification_reason=commit["commit"]["verification"]["reason"],
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BootstrapSourceAdmissionError("source GitHub authority is malformed") from exc
    except (AttributeError, KeyError, TypeError, authority.LifecycleAuthorityError) as exc:
        raise BootstrapSourceAdmissionError("source GitHub authority is malformed") from exc
    if (
        not isinstance(facts.base_ref, str)
        or not facts.base_ref
        or facts.base_ref != facts.base_ref.strip()
        or not isinstance(facts.state, str)
        or type(facts.draft) is not bool
        or not isinstance(facts.github_verification_reason, str)
        or type(facts.github_verified) is not bool
    ):
        raise BootstrapSourceAdmissionError("source GitHub authority is malformed")
    return facts


def _admit_github_source(
    facts: GitHubSourceFacts,
    policy: authority.BootstrapSourceAdmissionPolicy,
) -> None:
    """Purely admit canonical facts against one exact maintained policy."""

    valid = (
        isinstance(facts, GitHubSourceFacts)
        and facts.base_repository == policy.repository
        and facts.base_ref == policy.source_base_ref
        and facts.head_repository == policy.repository
        and facts.pull_request == policy.pull_request
        and facts.state == policy.source_pr_state
        and facts.draft is policy.source_pr_draft
        and facts.head_sha == policy.source_head_sha
        and facts.commit_sha == policy.source_head_sha
        and facts.tree_sha == policy.source_tree_sha
        and facts.parent_shas == (policy.source_parent_sha,)
        and facts.github_verified is True
        and facts.github_verification_reason == "valid"
    )
    if not valid:
        raise BootstrapSourceAdmissionError(
            "source GitHub repository, PR, object, or verification binding changed"
        )


def _authenticate_live_github_source(
    policy: authority.BootstrapSourceAdmissionPolicy,
) -> None:
    """Assemble observation, pure normalization, and pure admission."""

    observation = _observe_github(policy)
    facts = _normalize_github_observation(observation)
    _admit_github_source(facts, policy)


def _observe_recovery_review_state(
    policy: authority.BootstrapSourceAdmissionPolicy,
) -> bytes:
    actions = _load_actions_helper()
    try:
        registry = actions.load_registry(actions.REGISTRY_PATH)
        entry = actions.select_repository(registry, policy.repository)
        gateway = actions.FastPathGateway(Path(__file__).resolve().parents[2], entry)
        observed = gateway.observe_stable_feedback(
            policy.repository, policy.pull_request
        )
        return authority.canonical_json_bytes(
            {
                "repository": policy.repository,
                "pull_request_number": policy.pull_request,
                **observed,
            }
        )
    except (
        AttributeError,
        OSError,
        TypeError,
        fast_path.RecoverableLocalError,
        fast_path.SecurityBlocker,
        fast_path.TransientReadFailure,
        actions.RegistryError,
    ) as exc:
        raise BootstrapSourceAdmissionError(
            "source recovery review authority is unavailable"
        ) from exc


def _normalize_recovery_review_state(raw: bytes) -> RecoveryReviewFacts:
    """Purely normalize the bounded recovery review representation."""

    try:
        document = _closed_json(raw, "source recovery review authority")
        expected_fields = {
            "repository",
            "pull_request_number",
            "head_sha",
            "base_ref",
            "base_sha",
            "pr_state",
            "review_decision",
            "feedback",
        }
        if set(document) != expected_fields:
            raise BootstrapSourceAdmissionError(
                "source recovery review authority is malformed"
            )
        reviewed = fast_path.StableFeedbackState.from_payload(document)
        review_decision = document["review_decision"]
        feedback = reviewed.feedback
        threads = feedback["threads"]
        facts = RecoveryReviewFacts(
            repository=reviewed.repository,
            pull_request=authority._require_positive_int(
                reviewed.pull_request_number, "source recovery pull request"
            ),
            head_sha=reviewed.head_sha,
            base_ref=reviewed.base_ref,
            state=reviewed.pr_state,
            review_decision="NONE" if review_decision is None else review_decision,
            feedback_inventory_digest=reviewed.feedback_digest,
            conversation_comment_count=len(feedback["conversation_comments"]),
            review_thread_count=len(threads),
            resolved_review_thread_count=sum(
                item["is_resolved"] is True for item in threads
            ),
        )
    except BootstrapSourceAdmissionError:
        raise
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        fast_path.SecurityBlocker,
        authority.LifecycleAuthorityError,
    ) as exc:
        raise BootstrapSourceAdmissionError(
            "source recovery review authority is malformed"
        ) from exc
    if (
        not isinstance(facts.review_decision, str)
        or not _DIGEST.fullmatch(facts.feedback_inventory_digest)
        or type(facts.conversation_comment_count) is not int
        or facts.conversation_comment_count < 0
        or type(facts.review_thread_count) is not int
        or facts.review_thread_count < 0
    ):
        raise BootstrapSourceAdmissionError(
            "source recovery review authority is malformed"
        )
    return facts


def _authenticate_live_recovery_review_state(
    policy: authority.BootstrapSourceAdmissionPolicy,
) -> None:
    recovery = policy.evidence_loss_recovery
    if recovery is None:
        raise BootstrapSourceAdmissionError(
            "accepted-main source evidence-loss recovery is absent"
        )
    facts = _normalize_recovery_review_state(
        _observe_recovery_review_state(policy)
    )
    gate = recovery.technical_security_gate
    if (
        facts.repository != policy.repository
        or facts.pull_request != policy.pull_request
        or facts.head_sha != policy.source_head_sha
        or facts.base_ref != policy.source_base_ref
        or facts.state != policy.source_pr_state
        or facts.review_decision != gate.review_decision
        or facts.feedback_inventory_digest != gate.feedback_inventory_digest
        or facts.conversation_comment_count != gate.conversation_comment_count
        or facts.review_thread_count != gate.resolved_review_thread_count
        or facts.resolved_review_thread_count
        != gate.resolved_review_thread_count
    ):
        raise BootstrapSourceAdmissionError(
            "source recovery review state changed or has an open finding"
        )


@contextmanager
def _isolated_source_repository(
    trust: authority.LifecycleTrustPolicy,
    policy: authority.BootstrapSourceAdmissionPolicy,
) -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="secpal-bootstrap-source-") as directory:
        root = Path(directory).resolve()
        root.chmod(0o700)
        _git(root, ["init", "--quiet"])
        _git(root, ["remote", "add", "origin", trust.publication_remote_url])
        _git(
            root,
            [
                "fetch", "--quiet", "--no-tags", "--depth=2", "origin",
                policy.source_head_sha,
            ],
        )
        fetched = _git_text(root, ["rev-parse", "FETCH_HEAD"]).strip()
        if fetched != policy.source_head_sha:
            raise BootstrapSourceAdmissionError("mutable source ref substitution detected")
        _git(root, ["checkout", "--quiet", "--detach", policy.source_head_sha])
        _verify_materialized_tree(root, policy)
        yield root


def _exact_trailer(root: Path, head: str) -> str:
    value = _git_text(
        root,
        [
            "show", "-s",
            "--format=%(trailers:key=SecPal-Validation-Receipt,valueonly,separator=%x00)",
            head,
        ],
    ).rstrip("\n")
    trailers = [item.strip() for item in value.split("\x00") if item.strip()]
    if len(trailers) != 1 or not _DIGEST.fullmatch(trailers[0]):
        raise BootstrapSourceAdmissionError(
            "source commit does not carry exactly one final receipt trailer"
        )
    return trailers[0]


def _lifecycle_execution_raise_sites(raw: bytes) -> frozenset[tuple[str, int]]:
    """Inventory exact explicit executor error sites without interpreting text."""

    try:
        tree = ast.parse(raw, filename=IMPLEMENTATION_PATH)
    except (SyntaxError, ValueError) as exc:
        raise BootstrapSourceAdmissionError(
            "admitted implementation is invalid Python"
        ) from exc
    parents: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    sites: set[tuple[str, int]] = set()
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Raise)
            and isinstance(node.exc, ast.Call)
            and isinstance(node.exc.func, ast.Name)
            and node.exc.func.id == "LifecycleExecutionError"
        ):
            continue
        parent: ast.AST | None = node
        while parent is not None and not isinstance(
            parent, (ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            parent = parents.get(parent)
        if parent is None:
            raise BootstrapSourceAdmissionError(
                "executor diagnostic raise site has no function identity"
            )
        site = (parent.name, node.lineno)
        if site in sites:
            raise BootstrapSourceAdmissionError(
                "executor diagnostic raise-site identity is ambiguous"
            )
        sites.add(site)
    return frozenset(sites)


def _verify_diagnostic_raise_site_agreement(
    raw: bytes, blob_oid: str
) -> frozenset[tuple[str, int]]:
    """Bind the closed diagnostic table to the exact admitted executor blob."""

    expected = dict(_DIAGNOSTIC_RAISE_SITES)
    if (
        blob_oid != _DIAGNOSTIC_EXECUTOR_BLOB_OID
        or len(expected) != len(_DIAGNOSTIC_RAISE_SITES)
        or not expected
        or not set(expected.values()).issubset(_EXECUTION_DIAGNOSTIC_IDENTITIES)
    ):
        raise BootstrapSourceAdmissionError(
            "executor diagnostic agreement is not exact"
        )
    observed = _lifecycle_execution_raise_sites(raw)
    if observed != frozenset(expected):
        raise BootstrapSourceAdmissionError(
            "executor diagnostic raise-site agreement changed"
        )
    return observed


def _implementation_blob(root: Path, policy: authority.BootstrapSourceAdmissionPolicy) -> str:
    record = _git_text(
        root,
        ["ls-tree", "-z", "--full-tree", policy.source_tree_sha, "--", f":(literal){policy.implementation_path}"],
    )
    if not record.endswith("\x00") or record.count("\x00") != 1:
        raise BootstrapSourceAdmissionError("admitted implementation path is unavailable")
    metadata, separator, path = record[:-1].partition("\t")
    fields = metadata.split()
    if (
        separator != "\t"
        or path != policy.implementation_path
        or len(fields) != 3
        or fields[0] not in {"100644", "100755"}
        or fields[1] != "blob"
        or not _OID.fullmatch(fields[2])
    ):
        raise BootstrapSourceAdmissionError("admitted implementation path is not a regular blob")
    if policy.subtype == EVIDENCE_HELPER_ADMISSION_SUBTYPE:
        if (
            policy.entrypoint is not None
            or policy.implementation_path != EVIDENCE_HELPER_IMPLEMENTATION_PATH
            or policy.policy_source != ACCEPTED_MAIN_POLICY_SOURCE
            or fields[2] != policy.implementation_blob_oid
        ):
            raise BootstrapSourceAdmissionError(
                "admitted byte-source path or blob differs from accepted-main policy"
            )
        return fields[2]
    if policy.subtype != ADMISSION_SUBTYPE or policy.implementation_blob_oid is not None:
        raise BootstrapSourceAdmissionError("source-admission subtype is not executable")
    raw = _git(root, ["cat-file", "blob", fields[2]]).stdout
    try:
        tree = ast.parse(raw, filename=policy.implementation_path)
    except (SyntaxError, ValueError) as exc:
        raise BootstrapSourceAdmissionError("admitted implementation is invalid Python") from exc
    definitions = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == policy.entrypoint
    ]
    if len(definitions) != 1:
        raise BootstrapSourceAdmissionError("admitted entrypoint is absent or ambiguous")
    _verify_diagnostic_raise_site_agreement(raw, fields[2])
    self_admission = _run_bootstrap_git(
        root,
        ["cat-file", "-e", f"{policy.source_tree_sha}:scripts/secpal_pr_review/bootstrap_source_admission.py"],
    )
    if self_admission.returncode == 0:
        raise BootstrapSourceAdmissionError("candidate-local verifier cannot self-admit")
    return fields[2]


def _authenticate_materialized_source(
    root: Path,
    trust: authority.LifecycleTrustPolicy,
    policy: authority.BootstrapSourceAdmissionPolicy,
    evidence_documents: tuple[dict[str, Any], ...],
) -> VerifiedBootstrapSource:
    head, tree, blob = _authenticate_exact_materialized_source(root, trust, policy)
    reviewed_raw, receipt, attestation = evidence_documents
    try:
        reviewed = fast_path.verify_reviewed_state_evidence(reviewed_raw)
        actions = _load_actions_helper()
        binding = actions._prior_delivery_registry_binding(root, head, policy.repository)
        expected_receipt = fast_path.create_validation_receipt(
            repository=policy.repository,
            head_sha=reviewed.head_sha,
            validated_tree_sha=tree,
            registry=binding,
            command_set=binding["validation"],
            successful_result=True,
            reviewed_state=reviewed,
            manual_gate_evidence=attestation.get("manual_gate_evidence"),
            eligibility_evidence_digest=attestation.get("eligibility_evidence_digest"),
            exceptional_recovery_evidence_digest=attestation.get(
                "exceptional_recovery_evidence_digest"
            ),
        )
        if receipt != expected_receipt:
            raise fast_path.SecurityBlocker("source validation receipt is stale")
        verified = fast_path.verify_validation_attestation(
            attestation,
            repository=policy.repository,
            head_sha=head,
            registry=binding,
            command_set=binding["validation"],
            reviewed_state=reviewed,
            commit_parent_sha=policy.source_parent_sha,
            commit_tree_sha=tree,
            commit_validation_receipt_digest=policy.validation_receipt_digest,
        )
    except (fast_path.SecurityBlocker, AttributeError, KeyError, TypeError) as exc:
        raise BootstrapSourceAdmissionError(
            "source validation receipt or final attestation is invalid"
        ) from exc
    if (
        reviewed.repository != policy.repository
        or reviewed.pull_request_number != policy.pull_request
        or receipt.get("receipt_digest") != policy.validation_receipt_digest
        or attestation.get("attestation_digest") != policy.final_attestation_digest
        or verified.validation_receipt_digest != policy.validation_receipt_digest
        or verified.final_attestation_digest != policy.final_attestation_digest
    ):
        raise BootstrapSourceAdmissionError(
            "source validation evidence does not match maintained admission"
        )
    return _verified_bootstrap_source(
        policy,
        head=head,
        tree=tree,
        blob=blob,
        historical_evidence_status=HISTORICAL_EVIDENCE_PRESENT,
    )


def _authenticate_exact_materialized_source(
    root: Path,
    trust: authority.LifecycleTrustPolicy,
    policy: authority.BootstrapSourceAdmissionPolicy,
) -> tuple[str, str, str]:
    """Authenticate immutable provenance shared by both evidence modes."""

    head = _git_text(root, ["rev-parse", "HEAD"]).strip()
    tree = _git_text(root, ["rev-parse", f"{head}^{{tree}}"]).strip()
    parents = _git_text(root, ["rev-list", "--parents", "-n", "1", head]).split()
    if (
        head != policy.source_head_sha
        or tree != policy.source_tree_sha
        or parents != [policy.source_head_sha, policy.source_parent_sha]
    ):
        raise BootstrapSourceAdmissionError("source head, tree, or parent changed")
    _verify_commit_signature(root, trust, policy)
    trailer = _exact_trailer(root, head)
    if trailer != policy.validation_receipt_digest:
        raise BootstrapSourceAdmissionError(
            "source commit validation-receipt trailer changed"
        )
    blob = _implementation_blob(root, policy)
    return head, tree, blob


def _verified_bootstrap_source(
    policy: authority.BootstrapSourceAdmissionPolicy,
    *,
    head: str,
    tree: str,
    blob: str,
    historical_evidence_status: str,
    recovery: authority.BootstrapSourceEvidenceLossRecovery | None = None,
) -> VerifiedBootstrapSource:
    return VerifiedBootstrapSource(
        repository=policy.repository,
        delivery_issue=policy.delivery_issue,
        pull_request=policy.pull_request,
        head_sha=head,
        tree_sha=tree,
        parent_sha=policy.source_parent_sha,
        validation_receipt_digest=policy.validation_receipt_digest,
        final_attestation_digest=policy.final_attestation_digest,
        signer_identity=policy.source_signer_identity,
        implementation_path=policy.implementation_path,
        implementation_blob_oid=blob,
        entrypoint=policy.entrypoint,
        purpose=policy.purpose,
        policy_source=policy.policy_source,
        admission_digest=policy.admission_digest,
        historical_evidence_status=historical_evidence_status,
        recovery_authority_digest=(
            None if recovery is None else recovery.recovery_digest
        ),
        recovery_validation_digest=(
            None if recovery is None else recovery.recovery_validation.validation_digest
        ),
        recovery_technical_security_gate_digest=(
            None
            if recovery is None
            else recovery.technical_security_gate.gate_digest
        ),
        _verification_seal=_VERIFIED_SOURCE,
    )


def _authenticate_recovered_materialized_source(
    root: Path,
    trust: authority.LifecycleTrustPolicy,
    policy: authority.BootstrapSourceAdmissionPolicy,
) -> VerifiedBootstrapSource:
    """Authenticate one accepted recovery without reconstructing lost evidence."""

    head, tree, blob = _authenticate_exact_materialized_source(root, trust, policy)
    recovery = policy.evidence_loss_recovery
    if recovery is None:
        raise BootstrapSourceAdmissionError(
            "accepted-main source evidence-loss recovery is absent"
        )
    try:
        actions = _load_actions_helper()
        binding = actions._prior_delivery_registry_binding(root, head, policy.repository)
        command_set_digest = fast_path.digest_json(binding["validation"])
    except (AttributeError, KeyError, TypeError, fast_path.SecurityBlocker) as exc:
        raise BootstrapSourceAdmissionError(
            "exact source recovery validation policy is unavailable"
        ) from exc
    if (
        recovery.historical_evidence_status != HISTORICAL_EVIDENCE_RECOVERY
        or recovery.source_admission_digest != policy.admission_digest
        or recovery.recovery_validation.source_head_sha != head
        or recovery.recovery_validation.source_tree_sha != tree
        or recovery.recovery_validation.command_set_digest != command_set_digest
        or recovery.recovery_validation.result != "PASSED"
        or recovery.technical_security_gate.source_head_sha != head
        or recovery.technical_security_gate.source_tree_sha != tree
        or recovery.technical_security_gate.result
        != "NO_OPEN_TECHNICAL_OR_SECURITY_FINDINGS"
    ):
        raise BootstrapSourceAdmissionError(
            "accepted-main source evidence-loss recovery is invalid"
        )
    return _verified_bootstrap_source(
        policy,
        head=head,
        tree=tree,
        blob=blob,
        historical_evidence_status=HISTORICAL_EVIDENCE_RECOVERY,
        recovery=recovery,
    )


def verify_first_ready_executor_source(
    repository: str,
    delivery_issue: int,
    *,
    source_evidence_directory: Path | str | None = None,
) -> VerifiedBootstrapSource:
    """Authenticate the exact source without authorizing or performing mutation."""

    trust, policy = _select_policy(repository, delivery_issue)
    evidence = (
        None
        if source_evidence_directory is None
        else _read_evidence(source_evidence_directory)
    )
    _authenticate_live_github_source(policy)
    if evidence is None:
        _authenticate_live_recovery_review_state(policy)
    with _isolated_source_repository(trust, policy) as root:
        verified = (
            _authenticate_recovered_materialized_source(root, trust, policy)
            if evidence is None
            else _authenticate_materialized_source(root, trust, policy, evidence)
        )
        _verify_materialized_tree(root, policy)
        return verified


def verify_pr_review_evidence_helper_source(
    repository: str,
    delivery_issue: int,
    *,
    source_evidence_directory: Path | str,
) -> VerifiedBootstrapSource:
    """Authenticate the exact admitted PR-review helper bytes without execution."""

    trust, policy = _select_evidence_helper_policy(repository, delivery_issue)
    evidence = _read_evidence(source_evidence_directory)
    _authenticate_live_github_source(policy)
    with _isolated_source_repository(trust, policy) as root:
        verified = _authenticate_materialized_source(root, trust, policy, evidence)
        _verify_materialized_tree(root, policy)
        return verified


def _trusted_python() -> str:
    helper = authority._load_trusted_command_helper()
    for directory in helper.TRUSTED_COMMAND_DIRECTORIES:
        candidate = directory / "python3"
        try:
            resolved = candidate.resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        if resolved.is_file() and os.access(resolved, os.X_OK):
            return str(resolved)
    raise BootstrapSourceAdmissionError("trusted Python executable is unavailable")


def _closed_launcher_environment(helper: Any) -> dict[str, str]:
    """Build the child environment before loader or Python startup can run.

    Python isolation flags and launcher provenance checks begin only after the
    operating-system loader has accepted this mapping, so this must begin from
    an empty dictionary rather than filtering inherited process state.
    """

    base = helper.command_environment("gh")
    if not isinstance(base, Mapping):
        raise BootstrapSourceAdmissionError("trusted launcher environment is invalid")
    environment = {
        "PATH": helper.TRUSTED_COMMAND_PATH,
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PAGER": "cat",
        "GH_PAGER": "cat",
        "GH_HOST": "github.com",
    }
    for key in ("HOME", "GH_CONFIG_DIR", "GH_TOKEN", "GITHUB_TOKEN"):
        value = base.get(key)
        if value is not None:
            if not isinstance(value, str):
                raise BootstrapSourceAdmissionError(
                    "trusted launcher environment value is invalid"
                )
            environment[key] = value
    return environment


def _execute_entrypoint(root: Path, serialized_authorization: bytes | str) -> Mapping[str, Any]:
    authorization = (
        serialized_authorization.encode("utf-8")
        if isinstance(serialized_authorization, str)
        else serialized_authorization
    )
    if not isinstance(authorization, bytes) or not authorization:
        raise BootstrapSourceAdmissionError(
            "lifecycle authorization is required: AUTHORIZATION_ORCHESTRATION_FAILURE",
            diagnostic_identity="AUTHORIZATION_ORCHESTRATION_FAILURE",
        )
    helper = authority._load_trusted_command_helper()
    environment = _closed_launcher_environment(helper)
    try:
        result = subprocess.run(
            [_trusted_python(), "-I", "-S", "-c", _LAUNCHER, str(root)],
            cwd=root,
            input=authorization,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=120,
            env=environment,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise BootstrapSourceAdmissionError(
            "admitted entrypoint execution failed: UNEXPECTED_CLOSED_CHILD_FAILURE",
            diagnostic_identity="UNEXPECTED_CLOSED_CHILD_FAILURE",
        ) from exc
    if result.returncode != 0:
        identity = "UNEXPECTED_CLOSED_CHILD_FAILURE"
        try:
            failure = _closed_json(result.stdout, "admitted executor failure")
            if (
                set(failure) == {"diagnostic_identity", "status"}
                and failure["status"] == "REJECTED"
                and failure["diagnostic_identity"] in _EXECUTION_DIAGNOSTIC_IDENTITIES
            ):
                identity = failure["diagnostic_identity"]
        except BootstrapSourceAdmissionError:
            pass
        raise BootstrapSourceAdmissionError(
            f"admitted lifecycle executor failed: {identity}",
            diagnostic_identity=identity,
        )
    try:
        payload = json.loads(result.stdout, object_pairs_hook=publication._reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BootstrapSourceAdmissionError(
            "admitted executor result is malformed: UNEXPECTED_CLOSED_CHILD_FAILURE",
            diagnostic_identity="UNEXPECTED_CLOSED_CHILD_FAILURE",
        ) from exc
    if not isinstance(payload, dict):
        raise BootstrapSourceAdmissionError(
            "admitted executor result is malformed: UNEXPECTED_CLOSED_CHILD_FAILURE",
            diagnostic_identity="UNEXPECTED_CLOSED_CHILD_FAILURE",
        )
    return copy.deepcopy(payload)


def execute_first_ready_executor_bootstrap(
    repository: str,
    delivery_issue: int,
    serialized_authorization: bytes | str,
    *,
    source_evidence_directory: Path | str | None = None,
) -> Mapping[str, Any]:
    """Call only the admitted #812 entrypoint after independent source checks."""

    trust, policy = _select_policy(repository, delivery_issue)
    evidence = (
        None
        if source_evidence_directory is None
        else _read_evidence(source_evidence_directory)
    )
    _authenticate_live_github_source(policy)
    if evidence is None:
        _authenticate_live_recovery_review_state(policy)
    with _isolated_source_repository(trust, policy) as root:
        verified = (
            _authenticate_recovered_materialized_source(root, trust, policy)
            if evidence is None
            else _authenticate_materialized_source(root, trust, policy, evidence)
        )
        if not is_verified_bootstrap_source(verified):
            raise BootstrapSourceAdmissionError("source admission verification was not retained")
        _verify_materialized_tree(root, policy)
        return _execute_entrypoint(root, serialized_authorization)
