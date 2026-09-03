# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Authenticate and execute the exact first Ready-executor implementation.

This boundary admits implementation bytes only.  Lifecycle orchestration and
the signed one-use transition authorization remain the sole mutation authority.
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
import subprocess
import sys
import tempfile
from typing import Any, Iterator, Mapping

from . import fast_path
from . import lifecycle_authority as authority
from . import lifecycle_publication as publication


ADMISSION_KIND = "BOOTSTRAP_SOURCE_ADMISSION"
ADMISSION_SUBTYPE = "FIRST_READY_EXECUTOR_BOOTSTRAP_SOURCE"
PURPOSE = "FIRST_READY_EXECUTOR_BOOTSTRAP"
IMPLEMENTATION_PATH = "scripts/secpal_pr_review/lifecycle_execution.py"
ENTRYPOINT = "execute_lifecycle_transition"
_ADMISSION_HELPER = Path(__file__).resolve().parents[1] / "secpal-pr-review-actions.py"
_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
_DIGEST = re.compile(r"[0-9a-f]{64}")
_VERIFIED_SOURCE = object()
_LAUNCHER = r"""
import dataclasses
import json
from pathlib import Path
import sys

source_root = Path(sys.argv[1]).resolve(strict=True)
stdlib = [value for value in sys.path if value and "site-packages" not in value]
sys.path[:] = [str(source_root), *stdlib]
from scripts.secpal_pr_review import lifecycle_execution

expected = source_root / "scripts/secpal_pr_review/lifecycle_execution.py"
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
payload = dataclasses.asdict(result) if dataclasses.is_dataclass(result) else result
sys.stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
"""


class BootstrapSourceAdmissionError(ValueError):
    """The exact maintained implementation source cannot be authenticated."""


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
    entrypoint: str
    purpose: str
    admission_digest: str
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


def _select_policy(
    repository: str, delivery_issue: int
) -> tuple[authority.LifecycleTrustPolicy, authority.BootstrapSourceAdmissionPolicy]:
    try:
        repository = authority._require_repository(repository)
        delivery_issue = authority._require_positive_int(
            delivery_issue, "bootstrap delivery issue"
        )
        trust = authority._load_lifecycle_trust_policy(repository)
    except authority.LifecycleAuthorityError as exc:
        raise BootstrapSourceAdmissionError(str(exc)) from exc
    matches = [
        item
        for item in trust.bootstrap_source_admissions
        if item.repository == repository
        and item.delivery_issue == delivery_issue
        and item.purpose == PURPOSE
    ]
    if len(matches) != 1:
        raise BootstrapSourceAdmissionError(
            "bootstrap source admission is not uniquely maintained"
        )
    return trust, matches[0]


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
        path = root / filename
        try:
            if path.is_symlink() or not path.is_file():
                raise OSError
            raw = path.read_bytes()
        except OSError as exc:
            raise BootstrapSourceAdmissionError(f"{label} is unavailable") from exc
        values.append(_closed_json(raw, label))
    return tuple(values)


def _git(
    root: Path,
    arguments: list[str],
    *,
    input_bytes: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    result = publication._run_git(root, arguments, input_bytes=input_bytes)
    if result.returncode != 0:
        raise BootstrapSourceAdmissionError("immutable source Git operation failed")
    return result


def _git_text(root: Path, arguments: list[str]) -> str:
    try:
        return _git(root, arguments).stdout.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise BootstrapSourceAdmissionError("immutable source Git output is malformed") from exc


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
    result = publication._run_git(
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


def _observe_github(policy: authority.BootstrapSourceAdmissionPolicy) -> None:
    pr_result = publication._run_gh(
        ["api", "--hostname", "github.com", f"repos/{policy.repository}/pulls/{policy.pull_request}"]
    )
    commit_result = publication._run_gh(
        ["api", "--hostname", "github.com", f"repos/{policy.repository}/commits/{policy.source_head_sha}"]
    )
    if pr_result.returncode != 0 or commit_result.returncode != 0:
        raise BootstrapSourceAdmissionError("source GitHub authority is unavailable")
    try:
        pull = json.loads(pr_result.stdout, object_pairs_hook=publication._reject_duplicate_pairs)
        commit = json.loads(commit_result.stdout, object_pairs_hook=publication._reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BootstrapSourceAdmissionError("source GitHub authority is malformed") from exc
    try:
        valid = (
            pull["base"]["repo"]["full_name"] == policy.repository
            and pull["head"]["repo"]["full_name"] == policy.repository
            and pull["number"] == policy.pull_request
            and pull["state"].upper() == policy.source_pr_state
            and pull["draft"] is policy.source_pr_draft
            and pull["head"]["sha"] == policy.source_head_sha
            and commit["sha"] == policy.source_head_sha
            and commit["commit"]["tree"]["sha"] == policy.source_tree_sha
            and [item["sha"] for item in commit["parents"]]
            == [policy.source_parent_sha]
            and commit["commit"]["verification"]["verified"] is True
            and commit["commit"]["verification"]["reason"] == "valid"
        )
    except (AttributeError, KeyError, TypeError):
        valid = False
    if not valid:
        raise BootstrapSourceAdmissionError(
            "source GitHub repository, PR, object, or verification binding changed"
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
    self_admission = publication._run_git(
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
            commit_validation_receipt_digest=trailer,
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
    blob = _implementation_blob(root, policy)
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
        admission_digest=policy.admission_digest,
        _verification_seal=_VERIFIED_SOURCE,
    )


def verify_first_ready_executor_source(
    repository: str,
    delivery_issue: int,
    *,
    source_evidence_directory: Path | str,
) -> VerifiedBootstrapSource:
    """Authenticate the exact source without authorizing or performing mutation."""

    trust, policy = _select_policy(repository, delivery_issue)
    evidence = _read_evidence(source_evidence_directory)
    _observe_github(policy)
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
        raise BootstrapSourceAdmissionError("lifecycle authorization is required")
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
        raise BootstrapSourceAdmissionError("admitted entrypoint execution failed") from exc
    if result.returncode != 0:
        raise BootstrapSourceAdmissionError("admitted lifecycle executor rejected the operation")
    try:
        payload = json.loads(result.stdout, object_pairs_hook=publication._reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BootstrapSourceAdmissionError("admitted executor result is malformed") from exc
    if not isinstance(payload, dict):
        raise BootstrapSourceAdmissionError("admitted executor result is malformed")
    return copy.deepcopy(payload)


def execute_first_ready_executor_bootstrap(
    repository: str,
    delivery_issue: int,
    serialized_authorization: bytes | str,
    *,
    source_evidence_directory: Path | str,
) -> Mapping[str, Any]:
    """Call only the admitted #812 entrypoint after independent source checks."""

    trust, policy = _select_policy(repository, delivery_issue)
    evidence = _read_evidence(source_evidence_directory)
    _observe_github(policy)
    with _isolated_source_repository(trust, policy) as root:
        verified = _authenticate_materialized_source(root, trust, policy, evidence)
        if not is_verified_bootstrap_source(verified):
            raise BootstrapSourceAdmissionError("source admission verification was not retained")
        _verify_materialized_tree(root, policy)
        return _execute_entrypoint(root, serialized_authorization)
