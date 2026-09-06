# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""One protected-main, migration-signed pre-enrollment source admission."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
from typing import Any, Mapping

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


def _observe(record: Mapping[str, Any], entry: Any, trust: Any) -> tuple[dict[str, Any], Any]:
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
    return _admit_observation(record, target, issue_state, commits, timeline, reviewed, source_commit)


def _admit_observation(
    record: Mapping[str, Any], target: Any, issue_state: Any, commits: Any,
    timeline: Any, reviewed: Any, source_commit: Any,
) -> tuple[dict[str, Any], Any]:
    repository = record["repository"]
    issue = record["delivery_issue"]
    pr = record["pull_request"]
    if (
        target["number"] != pr or target["state"] != "open" or target["draft"] is not True
        or target["merged_at"] is not None or target["head"]["sha"] != record["head_sha"]
        or target["head"]["repo"]["full_name"] != repository
        or target["base"]["repo"]["full_name"] != repository or target["base"]["ref"] != "main"
        or issue_state["number"] != issue or issue_state["state"] != "open"
    ):
        raise authority.LifecycleAuthorityError("loss source is not the exact open unenrolled Draft")
    if not isinstance(commits, list) or not commits or len(commits) >= 100:
        raise authority.LifecycleAuthorityError("loss source history is incomplete")
    observations = record["observed_pre_enrollment_history"]
    if [item["sha"] for item in commits] != [item["head_sha"] for item in observations]:
        raise authority.LifecycleAuthorityError("loss source observed history changed")
    for index, item in enumerate(commits):
        if len(item["parents"]) != 1 or (index and item["parents"][0]["sha"] != commits[index - 1]["sha"]):
            raise authority.LifecycleAuthorityError("loss source history parent topology changed")
        timestamp = target["created_at"] if index == 0 else item["commit"]["committer"]["date"]
        if observations[index]["observed_at"] != timestamp:
            raise authority.LifecycleAuthorityError("loss source history timestamp changed")
    if not isinstance(timeline, list) or len(timeline) >= 100 or any(
        event.get("event") in {"ready_for_review", "convert_to_draft"} for event in timeline
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
        source_commit["sha"] != record["head_sha"]
        or source_commit["commit"]["tree"]["sha"] != record["tree_sha"]
        or [item["sha"] for item in source_commit["parents"]] != [record["parent_sha"]]
        or source_commit["commit"]["verification"]["verified"] is not True
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
            _prepare_dependencies(root, helper)
            _verify_source_bytes(root, record["tree_sha"], expected_listing=source_listing)
            result = helper._run_registered_validations(entry, root)
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
    trust = authority._load_lifecycle_trust_policy(repository)
    identity = execution._single_role_identity(trust.legacy_adoption_signer_identities, "migration/adoption signer")
    fields = {
        "schema_version": "1.0", "kind": KIND, "domain": DOMAIN, **acquired,
        "admission_id": f"pre-enrollment-validation-loss:{authority.digest_json(acquired)}",
        "adoption_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "bounded_uses": 1, "signer_identity": identity,
    }
    signature = execution._local_signer(identity)(authority.canonical_json_bytes(fields), DOMAIN)
    signed = {**fields, "signature": signature}
    return _verify_document({**signed, "admission_digest": authority.digest_json(signed)})
