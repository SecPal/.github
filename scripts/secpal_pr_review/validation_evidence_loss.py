# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""One protected-main, migration-signed pre-enrollment source admission."""

from __future__ import annotations

import copy
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
from typing import Any, Iterator, Mapping

from . import bootstrap_source_admission as transport
from . import fast_path
from . import lifecycle_authority as authority
from . import lifecycle_execution as execution
from . import lifecycle_publication as publication


KIND = "SECPAL_PRE_ENROLLMENT_VALIDATION_EVIDENCE_LOSS_ADMISSION"
DOMAIN = "secpal.pre-enrollment-validation-evidence-loss-admission/v1"
ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = "policies/pre-enrollment-validation-evidence-loss.json"
_VERIFIED = object()
_UNSUPPLIED = object()
FIELDS = frozenset({
    "schema_version", "kind", "domain", "repository", "delivery_issue",
    "pull_request", "head_sha", "tree_sha", "parent_sha", "pull_request_state",
    "draft", "source_signer_identity", "commit_signature_evidence_digest",
    "historical_validation_receipt_digest", "historical_package_status",
    "historical_final_attestation_digest", "historical_bytes_reconstructed",
    "loss_proof_policy_digest", "accepted_main_sha", "current_safety",
    "observed_pre_enrollment_history", "intended_state", "adoption_timestamp",
    "admission_id", "bounded_uses", "signer_identity", "signature", "admission_digest",
})
SAFETY_FIELDS = frozenset({
    "receipt_digest", "validated_tree_sha", "validation_policy_digest",
    "command_set_digest", "feedback_digest", "technical_decisions", "successful_result",
})
DECISION_FIELDS = frozenset({
    "source_id", "source_digest", "disposition", "evidence_digest",
})
RECORD_FIELDS = frozenset({
    "repository", "delivery_issue", "pull_request", "head_sha", "tree_sha",
    "parent_sha", "source_signer_identity", "historical_validation_receipt_digest",
    "historical_package_status", "historical_final_attestation_digest",
    "historical_bytes_reconstructed", "observed_pre_enrollment_history",
    "feedback_digest", "technical_decisions",
})


@dataclass(frozen=True)
class VerifiedPreEnrollmentValidationEvidenceLossAdmission:
    canonical_admission: dict[str, Any]
    _verification_seal: object


@dataclass(frozen=True)
class PullRequestFacts:
    number: int
    state: str
    draft: bool
    merged: bool
    head_sha: str
    head_repository: str
    base_repository: str
    base_ref: str
    created_at: str


@dataclass(frozen=True)
class IssueFacts:
    number: int
    state: str


@dataclass(frozen=True)
class CommitFacts:
    head_sha: str
    parent_shas: tuple[str, ...]
    committed_at: str


@dataclass(frozen=True)
class SourceCommitFacts:
    head_sha: str
    tree_sha: str
    parent_shas: tuple[str, ...]
    signature_verified: bool


@dataclass(frozen=True)
class NormalizedProviderFacts:
    pull_request: PullRequestFacts
    issue: IssueFacts
    commits: tuple[CommitFacts, ...]
    timeline_events: tuple[str | None, ...]
    source_commit: SourceCommitFacts


def _intended_state() -> dict[str, Any]:
    state = authority.initial_state()
    state.update(unrestricted_review_count=1, remediation_cycle_count=2)
    return state


def _decisions(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise authority.LifecycleAuthorityError("loss admission technical decisions are missing")
    seen: set[str] = set()
    for raw in value:
        item = authority._require_closed(raw, DECISION_FIELDS, "loss technical decision")
        identity = authority._require_identity(item["source_id"], "technical source")
        if identity in seen or item["disposition"] not in {
            "CORRECTED_AND_VERIFIED", "DISPROVEN_WITH_EVIDENCE", "NON_ACTIONABLE",
        }:
            raise authority.LifecycleAuthorityError("blocking or ambiguous loss technical decision")
        seen.add(identity)
        authority._require_digest(item["source_digest"], "technical source digest")
        authority._require_digest(item["evidence_digest"], "technical proof digest")
    return copy.deepcopy(value)


def _verify_document(value: Any) -> dict[str, Any]:
    """Verify immutable enrollment provenance without consulting a later CURRENT."""

    doc = copy.deepcopy(authority._require_closed(value, FIELDS, "validation-evidence-loss admission"))
    if (
        doc["schema_version"] != "1.0" or doc["kind"] != KIND or doc["domain"] != DOMAIN
        or doc["pull_request_state"] != "OPEN" or doc["draft"] is not True
        or doc["historical_package_status"] != "UNAVAILABLE"
        or doc["historical_final_attestation_digest"] is not None
        or doc["historical_bytes_reconstructed"] is not False
        or type(doc["bounded_uses"]) is not int or doc["bounded_uses"] != 1
    ):
        raise authority.LifecycleAuthorityError("loss admission cannot reconstruct history or authorize Ready")
    authority._require_repository(doc["repository"])
    for field in ("delivery_issue", "pull_request"):
        authority._require_positive_int(doc[field], field)
    for field in ("head_sha", "tree_sha", "parent_sha", "accepted_main_sha"):
        authority._require_oid(doc[field], field)
    if doc["head_sha"] == doc["parent_sha"]:
        raise authority.LifecycleAuthorityError("loss admission parent topology is invalid")
    for field in (
        "commit_signature_evidence_digest", "historical_validation_receipt_digest",
        "loss_proof_policy_digest", "admission_digest",
    ):
        authority._require_digest(doc[field], field)
    for field in ("source_signer_identity", "signer_identity", "admission_id"):
        authority._require_identity(doc[field], field)
    state = authority._validate_state(doc["intended_state"], allow_adopted_observations=True)
    if state != _intended_state():
        raise authority.LifecycleAuthorityError("loss admission must preserve exhausted Draft counters")
    history = authority._normalize_observed_pre_enrollment_history(
        doc["observed_pre_enrollment_history"], expected_head=doc["head_sha"],
        intended_state=state, review_budget_consumption_admitted=True,
    )
    timestamp = authority._parse_adoption_timestamp(doc["adoption_timestamp"], "loss admission time")
    if timestamp < authority._parse_adoption_timestamp(history[-1]["observed_at"], "last observation"):
        raise authority.LifecycleAuthorityError("loss admission cannot be backdated")
    safety = authority._require_closed(doc["current_safety"], SAFETY_FIELDS, "current safety evidence")
    if safety["successful_result"] is not True or safety["validated_tree_sha"] != doc["tree_sha"]:
        raise authority.LifecycleAuthorityError("loss admission requires exact successful current validation")
    for field in ("receipt_digest", "validation_policy_digest", "command_set_digest", "feedback_digest"):
        authority._require_digest(safety[field], field)
    if safety["receipt_digest"] == doc["historical_validation_receipt_digest"]:
        raise authority.LifecycleAuthorityError("loss admission requires divergent current safety evidence")
    _decisions(safety["technical_decisions"])
    signed = {key: item for key, item in doc.items() if key != "admission_digest"}
    if authority.digest_json(signed) != doc["admission_digest"]:
        raise authority.LifecycleAuthorityError("loss admission digest changed")
    trust = authority._load_lifecycle_trust_policy(doc["repository"])
    authority._verify_signature(
        authority.canonical_json_bytes(authority._unsigned(doc, "admission_digest", "signature")),
        doc["signature"], doc["signer_identity"], DOMAIN,
        trust.legacy_adoption_signer_identities, authority._policy_signature_verifier(trust),
    )
    return doc


def _verified_document(value: Any) -> dict[str, Any]:
    if type(value) is not VerifiedPreEnrollmentValidationEvidenceLossAdmission or value._verification_seal is not _VERIFIED:
        raise authority.LifecycleAuthorityError("loss source requires verifier-sealed admission")
    return _verify_document(value.canonical_admission)


def verify(serialized: bytes | str) -> VerifiedPreEnrollmentValidationEvidenceLossAdmission:
    doc = _verify_document(authority.loads_closed_json(serialized))
    _reauthenticate(doc)
    return VerifiedPreEnrollmentValidationEvidenceLossAdmission(copy.deepcopy(doc), _VERIFIED)


def _gh_json(endpoint: str) -> Any:
    result = transport._run_bootstrap_gh(["api", "--hostname", "github.com", endpoint])
    if result.returncode != 0:
        raise authority.LifecycleAuthorityError("loss admission provider acquisition failed")
    return authority.loads_closed_json(result.stdout)


def _accepted_policy(repository: str, issue: int) -> tuple[str, dict[str, Any], Any, Any]:
    if repository != "SecPal/.github":
        raise authority.LifecycleAuthorityError("loss admission repository is not maintained")
    authority._require_positive_int(issue, "loss issue")
    branch = _gh_json("repos/SecPal/.github/branches/main")
    main = authority._require_oid(branch["commit"]["sha"], "protected main")
    commit = _gh_json(f"repos/SecPal/.github/commits/{main}")
    if branch["protected"] is not True or commit["sha"] != main or commit["commit"]["verification"]["verified"] is not True:
        raise authority.LifecycleAuthorityError("loss policy requires authenticated protected main")
    if (
        transport._git_text(ROOT, ["rev-parse", "HEAD"]).strip() != main
        or transport._git_text(ROOT, ["status", "--porcelain=v2", "--untracked-files=all"])
    ):
        raise authority.LifecycleAuthorityError("candidate-local loss self-admission is forbidden")
    trusted_paths = [
        *sorted((ROOT / "scripts/secpal_pr_review").glob("*.py")),
        ROOT / "scripts/secpal-pr-review.py", ROOT / "scripts/secpal-pr-review-actions.py",
        ROOT / ".agents/skills/secpal-pr-review/references/repositories.json",
        ROOT / ".agents/skills/secpal-pr-review/references/repositories.schema.json",
        ROOT / POLICY_PATH,
    ]
    for path in trusted_paths:
        relative = str(path.relative_to(ROOT))
        actual = transport._git_text(ROOT, ["hash-object", "--no-filters", relative]).strip()
        expected = transport._git_text(ROOT, ["rev-parse", f"{main}:{relative}"]).strip()
        if actual != expected:
            raise authority.LifecycleAuthorityError("accepted-main loss code or policy bytes changed")
    policy = authority.loads_closed_json((ROOT / POLICY_PATH).read_bytes())
    if set(policy) != {"schema_version", "admissions"} or policy["schema_version"] != "1.0" or not isinstance(policy["admissions"], list):
        raise authority.LifecycleAuthorityError("loss policy is malformed")
    if any(not isinstance(item, dict) for item in policy["admissions"]):
        raise authority.LifecycleAuthorityError("loss policy records are malformed")
    records = [item for item in policy["admissions"] if item.get("repository") == repository and item.get("delivery_issue") == issue]
    if len(records) != 1:
        raise authority.LifecycleAuthorityError("no unique accepted-main evidence-loss proof")
    record = copy.deepcopy(authority._require_closed(records[0], RECORD_FIELDS, "loss proof policy"))
    authority._require_positive_int(record["pull_request"], "loss policy pull request")
    for field in ("head_sha", "tree_sha", "parent_sha"):
        authority._require_oid(record[field], field)
    for field in ("historical_validation_receipt_digest", "feedback_digest"):
        authority._require_digest(record[field], field)
    authority._require_identity(record["source_signer_identity"], "loss source signer")
    authority._normalize_observed_pre_enrollment_history(
        record["observed_pre_enrollment_history"], expected_head=record["head_sha"],
        intended_state=_intended_state(), review_budget_consumption_admitted=True,
    )
    _decisions(record["technical_decisions"])
    if (
        record["historical_package_status"] != "UNAVAILABLE"
        or record["historical_final_attestation_digest"] is not None
        or record["historical_bytes_reconstructed"] is not False
    ):
        raise authority.LifecycleAuthorityError("loss proof cannot reconstruct historical artifacts")
    helper = transport._load_actions_helper()
    entry = helper.select_repository(helper.load_registry(), repository)
    trust = authority._load_lifecycle_trust_policy(repository)
    return main, record, entry, trust


def _provider_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise authority.LifecycleAuthorityError(f"{label} provider representation is malformed")
    return value


def _provider_value(value: Any, path: tuple[str, ...], label: str) -> Any:
    current = value
    try:
        for field in path:
            current = _provider_mapping(current, label)[field]
    except KeyError as exc:
        raise authority.LifecycleAuthorityError(f"{label} provider representation is malformed") from exc
    return current


def _normalize_provider_representations(
    target: Any,
    issue_state: Any,
    commits: Any,
    timeline: Any,
    source_commit: Any,
) -> NormalizedProviderFacts:
    """Purely convert bounded provider representations into canonical facts."""

    target = _provider_mapping(target, "pull request")
    issue_state = _provider_mapping(issue_state, "issue")
    source_commit = _provider_mapping(source_commit, "source commit")
    if not isinstance(commits, list) or len(commits) > 100:
        raise authority.LifecycleAuthorityError("commit provider representation is malformed")
    if not isinstance(timeline, list) or len(timeline) > 100:
        raise authority.LifecycleAuthorityError("timeline provider representation is malformed")
    try:
        normalized_commits = tuple(
            CommitFacts(
                head_sha=_provider_value(item, ("sha",), "commit"),
                parent_shas=tuple(
                    _provider_value(parent, ("sha",), "commit parent")
                    for parent in _provider_value(item, ("parents",), "commit")
                ),
                committed_at=_provider_value(item, ("commit", "committer", "date"), "commit"),
            )
            for item in commits
        )
        timeline_events = tuple(
            _provider_mapping(item, "timeline event").get("event") for item in timeline
        )
        merged_at = _provider_value(target, ("merged_at",), "pull request")
        if merged_at is not None and not isinstance(merged_at, str):
            raise authority.LifecycleAuthorityError("pull request provider representation is malformed")
        return NormalizedProviderFacts(
            pull_request=PullRequestFacts(
                number=_provider_value(target, ("number",), "pull request"),
                state=str(_provider_value(target, ("state",), "pull request")).upper(),
                draft=_provider_value(target, ("draft",), "pull request"),
                merged=merged_at is not None,
                head_sha=_provider_value(target, ("head", "sha"), "pull request"),
                head_repository=_provider_value(target, ("head", "repo", "full_name"), "pull request"),
                base_repository=_provider_value(target, ("base", "repo", "full_name"), "pull request"),
                base_ref=_provider_value(target, ("base", "ref"), "pull request"),
                created_at=_provider_value(target, ("created_at",), "pull request"),
            ),
            issue=IssueFacts(
                number=_provider_value(issue_state, ("number",), "issue"),
                state=str(_provider_value(issue_state, ("state",), "issue")).upper(),
            ),
            commits=normalized_commits,
            timeline_events=timeline_events,
            source_commit=SourceCommitFacts(
                head_sha=_provider_value(source_commit, ("sha",), "source commit"),
                tree_sha=_provider_value(source_commit, ("commit", "tree", "sha"), "source commit"),
                parent_shas=tuple(
                    _provider_value(parent, ("sha",), "source commit parent")
                    for parent in _provider_value(source_commit, ("parents",), "source commit")
                ),
                signature_verified=_provider_value(
                    source_commit, ("commit", "verification", "verified"), "source commit"
                ),
            ),
        )
    except (TypeError, ValueError) as exc:
        raise authority.LifecycleAuthorityError("provider representation is malformed") from exc


def _observe(record: Mapping[str, Any], entry: Any, trust: Any) -> tuple[SourceCommitFacts, Any]:
    repository = record["repository"]
    issue = record["delivery_issue"]
    pr = record["pull_request"]
    publication.require_unenrolled_delivery(repository, issue)
    target = _gh_json(f"repos/{repository}/pulls/{pr}")
    issue_state = _gh_json(f"repos/{repository}/issues/{issue}")
    commits = _gh_json(f"repos/{repository}/pulls/{pr}/commits?per_page=100")
    timeline = _gh_json(f"repos/{repository}/issues/{pr}/timeline?per_page=100")
    helper = transport._load_actions_helper()
    reviewed = helper.FastPathGateway(ROOT, entry).capture_stable_feedback(repository, pr)
    source_commit = _gh_json(f"repos/{repository}/commits/{record['head_sha']}")
    normalized = _normalize_provider_representations(
        target, issue_state, commits, timeline, source_commit,
    )
    return _admit_observation(record, normalized, reviewed)


def _admit_observation(
    record: Mapping[str, Any], provider: NormalizedProviderFacts, reviewed: Any,
) -> tuple[SourceCommitFacts, Any]:
    if type(provider) is not NormalizedProviderFacts:
        raise authority.LifecycleAuthorityError("loss admission requires normalized provider facts")
    repository = record["repository"]
    issue = record["delivery_issue"]
    pr = record["pull_request"]
    target = provider.pull_request
    issue_state = provider.issue
    commits = provider.commits
    timeline = provider.timeline_events
    source_commit = provider.source_commit
    if (
        target.number != pr or target.state != "OPEN" or target.draft is not True
        or target.merged or target.head_sha != record["head_sha"]
        or target.head_repository != repository
        or target.base_repository != repository or target.base_ref != "main"
        or issue_state.number != issue or issue_state.state != "OPEN"
    ):
        raise authority.LifecycleAuthorityError("loss source is not the exact open unenrolled Draft")
    if not commits or len(commits) >= 100:
        raise authority.LifecycleAuthorityError("loss source history is incomplete")
    observations = record["observed_pre_enrollment_history"]
    if [item.head_sha for item in commits] != [item["head_sha"] for item in observations]:
        raise authority.LifecycleAuthorityError("loss source observed history changed")
    for index, item in enumerate(commits):
        if len(item.parent_shas) != 1 or (index and item.parent_shas[0] != commits[index - 1].head_sha):
            raise authority.LifecycleAuthorityError("loss source history parent topology changed")
        timestamp = target.created_at if index == 0 else item.committed_at
        if observations[index]["observed_at"] != timestamp:
            raise authority.LifecycleAuthorityError("loss source history timestamp changed")
    if len(timeline) >= 100 or any(
        event in {"ready_for_review", "convert_to_draft"} for event in timeline
    ):
        raise authority.LifecycleAuthorityError("loss source has Ready history or incomplete chronology")
    if reviewed.head_sha != record["head_sha"] or reviewed.pr_state != "OPEN" or reviewed.feedback_digest != record["feedback_digest"]:
        raise authority.LifecycleAuthorityError("loss source stable feedback changed")
    sources = fast_path._classified_feedback_sources(reviewed, include_resolved=True)
    decisions = _decisions(record["technical_decisions"])
    expected = {f"{kind}:{identity}": facts[0] for (kind, identity), facts in sources.items()}
    if {item["source_id"]: item["source_digest"] for item in decisions} != expected:
        raise authority.LifecycleAuthorityError("loss source technical decisions are not source-complete")
    if (
        source_commit.head_sha != record["head_sha"]
        or source_commit.tree_sha != record["tree_sha"]
        or list(source_commit.parent_shas) != [record["parent_sha"]]
        or source_commit.signature_verified is not True
    ):
        raise authority.LifecycleAuthorityError("loss source immutable identity or signature changed")
    return source_commit, reviewed


def _source_signature(root: Path, record: Mapping[str, Any], trust: Any) -> str:
    allowed = transport._allowed_signers(root, trust, record["source_signer_identity"])
    result = transport._run_bootstrap_git(root, [
        "-c", f"gpg.ssh.allowedSignersFile={allowed}", "verify-commit", "--raw", record["head_sha"],
    ])
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    principals = re.findall(r'(?m)^Good "git" signature for ([^\r\n]+) with ', output)
    if result.returncode != 0 or principals != [record["source_signer_identity"]]:
        raise authority.LifecycleAuthorityError("loss source signer is not authenticated")
    evidence = {
        "oid": record["head_sha"], "source": "USER", "signer_identity": record["source_signer_identity"],
        "local_signature": {"verified": True, "state": "valid", "format": "ssh"},
        "github_verification": {"verified": True, "reason": "valid"},
    }
    return authority.digest_json(fast_path.verify_commit_signatures(
        [evidence], authority._load_delivery_signature_policy(record["repository"]),
    )[0])


def _verify_source_bytes(root: Path, tree: str, *, expected_listing: str | None = None) -> str:
    listing = (
        transport._git_text(root, ["ls-tree", "-rz", "--full-tree", tree])
        if expected_listing is None else expected_listing
    )
    for entry in listing.rstrip("\0").split("\0"):
        metadata, separator, name = entry.partition("\t")
        fields = metadata.split()
        path = root / name
        if (
            not separator or len(fields) != 3 or fields[1] != "blob"
            or fields[0] not in {"100644", "100755"} or not name
            or Path(name).is_absolute() or ".." in Path(name).parts
        ):
            raise authority.LifecycleAuthorityError("loss source requires regular immutable source bytes")
        for parent in (path, *path.parents):
            if parent == root:
                break
            if parent.is_symlink():
                raise authority.LifecycleAuthorityError("loss source bytes contain a symlink")
        try:
            mode = path.stat().st_mode
            matches = (
                stat.S_ISREG(mode) and bool(mode & stat.S_IXUSR) == (fields[0] == "100755")
                and transport._git_text(root, ["hash-object", "--no-filters", "--", name]).strip() == fields[2]
            )
        except OSError as exc:
            raise authority.LifecycleAuthorityError("loss source bytes are unavailable") from exc
        if not matches:
            raise authority.LifecycleAuthorityError("validation mutated immutable source bytes")
    return listing


def _prepare_dependencies(root: Path, helper: Any) -> None:
    executable = helper._validation_executable({"argv": ["npm"]}, root, root)
    with tempfile.TemporaryDirectory(prefix="secpal-loss-dependencies-") as home:
        user_config = Path(home) / "user.npmrc"
        global_config = Path(home) / "global.npmrc"
        user_config.touch(mode=0o600)
        global_config.touch(mode=0o600)
        environment = {
            "HOME": home,
            "PATH": os.pathsep.join(str(path) for path in helper.LOCAL_VALIDATION_COMMAND_DIRECTORIES),
            "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
            "NPM_CONFIG_USERCONFIG": str(user_config), "NPM_CONFIG_GLOBALCONFIG": str(global_config),
        }
        try:
            result = subprocess.run(
                [executable, "ci", "--ignore-scripts", "--no-audit", "--no-fund"],
                cwd=root, env=environment, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=600, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise authority.LifecycleAuthorityError("current safety dependency preparation failed") from exc
        if result.returncode != 0:
            raise authority.LifecycleAuthorityError("current safety locked dependency installation failed")


def _current_validation_harness_paths(main: str, helper: Any, entry: Any) -> tuple[str, ...]:
    commands = helper._complete_validation_commands(entry)
    paths: set[str] = set()
    includes_tests = False
    for command in commands:
        arguments = command["argv"]
        if (
            arguments[:3] == ["python3", "-m", "unittest"]
            and len(arguments) > 3
            and all(path.startswith("tests/") for path in arguments[3:])
        ) or (len(arguments) == 1 and arguments[0].startswith("./tests/")):
            includes_tests = True
        elif arguments == ["./scripts/preflight.sh", "--reuse-tracked-only"]:
            paths.add("scripts/preflight.sh")
        elif arguments == ["npm", "run", "lint:markdown"]:
            paths.update({"package.json", "package-lock.json", ".markdownlint.json"})
        else:
            raise authority.LifecycleAuthorityError(
                "current validation command lacks an accepted harness-source boundary"
            )
    if includes_tests:
        try:
            tracked_tests = transport._git(ROOT, ["ls-tree", "-rz", "--name-only", main, "tests"]).stdout.decode(
                "utf-8", "strict"
            )
        except UnicodeDecodeError as exc:
            raise authority.LifecycleAuthorityError("current validation harness listing is malformed") from exc
        paths.update(path for path in tracked_tests.rstrip("\0").split("\0") if path)
    if not paths:
        raise authority.LifecycleAuthorityError("current validation harness has no maintained paths")
    return tuple(sorted(paths))


def _copy_current_harness_file(main: str, relative: str, destination_root: Path) -> None:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or not relative:
        raise authority.LifecycleAuthorityError("current validation harness path is unsafe")
    source = ROOT / path
    if source.is_symlink() or not source.is_file():
        raise authority.LifecycleAuthorityError("current validation harness file is unavailable")
    try:
        payload = source.read_bytes()
    except OSError as exc:
        raise authority.LifecycleAuthorityError("current validation harness file is unavailable") from exc
    actual = transport._git(ROOT, ["hash-object", "--stdin"], input_bytes=payload).stdout.decode(
        "ascii", "strict"
    ).strip()
    expected = transport._git_text(ROOT, ["rev-parse", f"{main}:{relative}"]).strip()
    if actual != expected:
        raise authority.LifecycleAuthorityError("current validation harness bytes are not accepted main")
    tree_entry = transport._git_text(ROOT, ["ls-tree", main, "--", relative]).split()
    if len(tree_entry) < 3 or tree_entry[0] not in {"100644", "100755"} or tree_entry[1] != "blob":
        raise authority.LifecycleAuthorityError("current validation harness mode is invalid")
    destination = destination_root / path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    destination.chmod(0o755 if tree_entry[0] == "100755" else 0o644)


@contextmanager
def _current_policy_validation_root(
    main: str,
    *,
    source_root: Path,
    helper: Any,
    entry: Any,
) -> Iterator[Path]:
    """Build a disposable target tree with only accepted-main harness bytes overlaid."""

    source_root = source_root.resolve(strict=True)
    if not source_root.is_dir():
        raise authority.LifecycleAuthorityError("immutable validation source root is unavailable")
    harness_paths = _current_validation_harness_paths(main, helper, entry)
    with tempfile.TemporaryDirectory(prefix="secpal-current-policy-validation-") as directory:
        execution_root = Path(directory) / "source"
        try:
            shutil.copytree(source_root, execution_root, symlinks=True)
            tests_root = execution_root / "tests"
            if tests_root.exists():
                shutil.rmtree(tests_root)
            for relative in harness_paths:
                _copy_current_harness_file(main, relative, execution_root)
        except OSError as exc:
            raise authority.LifecycleAuthorityError("current validation harness preparation failed") from exc
        yield execution_root


def _acquire(repository: str, issue: int, *, execute_validation: bool) -> dict[str, Any]:
    main, record, entry, trust = _accepted_policy(repository, issue)
    _, before = _observe(record, entry, trust)
    helper = transport._load_actions_helper()
    binding = helper._fast_registry_binding(entry)
    with tempfile.TemporaryDirectory(prefix="secpal-pre-enrollment-safety-") as directory:
        root = Path(directory)
        root.chmod(0o700)
        transport._git(root, ["init", "--quiet"])
        transport._git(root, ["remote", "add", "origin", trust.publication_remote_url])
        transport._git(root, ["fetch", "--quiet", "--no-tags", "--depth=64", "origin", record["head_sha"]])
        if transport._git_text(root, ["rev-parse", "FETCH_HEAD"]).strip() != record["head_sha"]:
            raise authority.LifecycleAuthorityError("loss source fetch changed identity")
        transport._git(root, ["checkout", "--quiet", "--detach", record["head_sha"]])
        if transport._git_text(root, ["rev-parse", "HEAD^{tree}"]).strip() != record["tree_sha"]:
            raise authority.LifecycleAuthorityError("loss source tree changed")
        if transport._git_text(root, ["rev-list", "--parents", "-n", "1", "HEAD"]).split() != [record["head_sha"], record["parent_sha"]]:
            raise authority.LifecycleAuthorityError("loss source sole parent changed")
        signature_digest = _source_signature(root, record, trust)
        if transport._exact_trailer(root, record["head_sha"]) != record["historical_validation_receipt_digest"]:
            raise authority.LifecycleAuthorityError("loss source historical signed receipt changed")
        source_listing = _verify_source_bytes(root, record["tree_sha"])
        if execute_validation:
            with _current_policy_validation_root(
                main, source_root=root, helper=helper, entry=entry,
            ) as validation_root:
                _prepare_dependencies(validation_root, helper)
                result = helper._run_registered_validations(entry, validation_root)
            if not result:
                raise authority.LifecycleAuthorityError(
                    f"current registered safety validation failed: {result.failure_report()}"
                )
        _verify_source_bytes(root, record["tree_sha"], expected_listing=source_listing)
        if (
            transport._git_text(root, ["rev-parse", "HEAD"]).strip() != record["head_sha"]
            or transport._git_text(root, ["diff", "--name-only", "HEAD"])
        ):
            raise authority.LifecycleAuthorityError("validation mutated the immutable source")
    _, after = _observe(record, entry, trust)
    if before.state_digest != after.state_digest:
        raise authority.LifecycleAuthorityError("current safety feedback is not stable")
    if _accepted_policy(repository, issue)[0] != main:
        raise authority.LifecycleAuthorityError("accepted-main authority changed during admission")
    return _assemble_source_facts(main, record, binding, helper._complete_validation_commands(entry), after, signature_digest)


def _assemble_source_facts(
    main: str, record: Mapping[str, Any], binding: Any, commands: Any,
    reviewed: Any, signature_digest: str,
) -> dict[str, Any]:
    current_safety_identity = authority.digest_json({
        "domain": "secpal.pre-enrollment-current-safety/v1",
        "repository": record["repository"], "head_sha": record["head_sha"],
        "tree_sha": record["tree_sha"], "validation_policy": binding,
        "commands": commands,
        "reviewed_state_digest": reviewed.state_digest, "successful_result": True,
    })
    return {
        **{field: copy.deepcopy(record[field]) for field in RECORD_FIELDS - {"feedback_digest", "technical_decisions"}},
        "pull_request_state": "OPEN", "draft": True,
        "commit_signature_evidence_digest": signature_digest,
        "loss_proof_policy_digest": authority.digest_json(record),
        "accepted_main_sha": main,
        "intended_state": _intended_state(),
        "current_safety": {
            "receipt_digest": current_safety_identity, "validated_tree_sha": record["tree_sha"],
            "validation_policy_digest": authority.digest_json(binding),
            "command_set_digest": authority.digest_json(commands),
            "feedback_digest": reviewed.feedback_digest,
            "technical_decisions": copy.deepcopy(record["technical_decisions"]),
            "successful_result": True,
        },
    }


def _reauthenticate(doc: Mapping[str, Any]) -> None:
    current = _acquire(doc["repository"], doc["delivery_issue"], execute_validation=False)
    if any(doc[field] != expected for field, expected in current.items()):
        raise authority.LifecycleAuthorityError("loss admission is stale or cross-context")


def issue(repository: str, delivery_issue: int, *, historical_package: Any = _UNSUPPLIED) -> dict[str, Any]:
    if historical_package is not _UNSUPPLIED:
        raise authority.LifecycleAuthorityError("supplied historical evidence cannot downgrade to loss admission")
    acquired = _acquire(repository, delivery_issue, execute_validation=True)
    identity, signer = execution._production_legacy_adoption_signer(repository)
    fields = {
        "schema_version": "1.0", "kind": KIND, "domain": DOMAIN, **acquired,
        "admission_id": f"pre-enrollment-validation-loss:{authority.digest_json(acquired)}",
        "adoption_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "bounded_uses": 1, "signer_identity": identity,
    }
    signature = signer(authority.canonical_json_bytes(fields), DOMAIN)
    signed = {**fields, "signature": signature}
    return _verify_document({**signed, "admission_digest": authority.digest_json(signed)})
