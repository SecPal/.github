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
import subprocess
import sys
import tempfile
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
_ADMISSION_HELPER = Path(__file__).resolve().parents[1] / "secpal-pr-review-actions.py"
_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
_DIGEST = re.compile(r"[0-9a-f]{64}")
_VERIFIED_SOURCE = object()
MAXIMUM_EVIDENCE_BYTES = late_disposition.MAXIMUM_ARTIFACT_BYTES
SOURCE_ADMISSION_FAILURE = "SOURCE_ADMISSION_FAILURE"
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
    repository: str,
    delivery_issue: int,
    *,
    subtype: str = ADMISSION_SUBTYPE,
    purpose: str = PURPOSE,
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
        and item.subtype == subtype
        and item.purpose == purpose
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
        try:
            raw = late_disposition._read_bounded_regular_file(
                root / filename, label, MAXIMUM_EVIDENCE_BYTES
            )
        except late_disposition.LateDispositionError as exc:
            raise BootstrapSourceAdmissionError(str(exc)) from exc
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


def _observe_github(
    policy: authority.BootstrapSourceAdmissionPolicy,
) -> GitHubSourceObservation:
    """Capture the exact provider representations without admitting them."""

    pr_result = publication._run_gh(
        ["api", "--hostname", "github.com", f"repos/{policy.repository}/pulls/{policy.pull_request}"]
    )
    commit_result = publication._run_gh(
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
        policy_source=policy.policy_source,
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
    _authenticate_live_github_source(policy)
    with _isolated_source_repository(trust, policy) as root:
        verified = _authenticate_materialized_source(root, trust, policy, evidence)
        _verify_materialized_tree(root, policy)
        return verified


def verify_pr_review_evidence_helper_source(
    repository: str,
    delivery_issue: int,
    *,
    source_evidence_directory: Path | str,
) -> VerifiedBootstrapSource:
    """Authenticate the exact admitted PR-review helper bytes without execution."""

    trust, policy = _select_policy(
        repository,
        delivery_issue,
        subtype=EVIDENCE_HELPER_ADMISSION_SUBTYPE,
        purpose=EVIDENCE_HELPER_PURPOSE,
    )
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
    source_evidence_directory: Path | str,
) -> Mapping[str, Any]:
    """Call only the admitted #812 entrypoint after independent source checks."""

    trust, policy = _select_policy(repository, delivery_issue)
    evidence = _read_evidence(source_evidence_directory)
    _authenticate_live_github_source(policy)
    with _isolated_source_repository(trust, policy) as root:
        verified = _authenticate_materialized_source(root, trust, policy, evidence)
        if not is_verified_bootstrap_source(verified):
            raise BootstrapSourceAdmissionError("source admission verification was not retained")
        _verify_materialized_tree(root, policy)
        return _execute_entrypoint(root, serialized_authorization)
