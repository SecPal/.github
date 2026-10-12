# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""One terminal disposition for the never-enrolled #705 / PR #706 delivery.

Native provider observations remain evidence of a violation, never lifecycle
events. No successor creation, enrollment or assessment is executable here.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
import re
import time
from typing import Any

from . import bootstrap_source_admission as transport
from . import fast_path, lifecycle_authority as authority
from . import lifecycle_execution as execution, lifecycle_publication as publication
from . import provider_acquisition

REPOSITORY = "SecPal/.github"
ISSUE = 705
PR = 706
IMPLEMENTATION_ISSUE = 1183
HEAD = "4760603b6f23bbd652432e82d1c6dc193c93c467"
TREE = "c4c750238cfc4338d20d240f9bfec6e481ac5587"
PARENT = "d56bd229c11848ac9231023cd49f1e968486c94e"
CREATED_AT = "2026-08-22T21:53:28Z"
REVIEWS = {
    "PRR_kwDOQFR1MM8AAAABKhc_ug": "copilot-pull-request-reviewer[bot]",
    "PRR_kwDOQFR1MM8AAAABKhdOcQ": "chatgpt-codex-connector[bot]",
}
THREADS = frozenset({"PRRT_kwDOQFR1MM6bbkqN", "PRRT_kwDOQFR1MM6bbkqP"})
COMMENTS = frozenset({"IC_kwDOQFR1MM8AAAABQNbrNw", "IC_kwDOQFR1MM8AAAABQNbsGQ"})
SECURITY_FAILURE = "IC_kwDOQFR1MM8AAAABQNbsGQ"
SECURITY_FAILURE_BODY = (
    "You have reached your Codex usage limits for security reviews. Please try again later."
)
KIND = "SECPAL_HISTORICAL_RETIREMENT_AUTHORIZATION"
DOMAIN = "secpal.historical-retirement-authorization/v1"
CLAIM_KIND = "SECPAL_HISTORICAL_RETIREMENT_CLAIM"
CLAIM_DOMAIN = "secpal.historical-retirement-claim/v1"
INTENT = "RETIRE_UNMERGED_SECPAL_GITHUB_705_PR_706_WITHOUT_SUCCESSOR_OR_REVIEW"
SUCCESSOR_BLOCKER = "NO_AUTHENTICATED_NON_RESETTING_FIRST_READY_AUTHORITY"
MAXIMUM_BYTES = 1024 * 1024
MAXIMUM_AUTHORIZATION_SECONDS = 900
_VERIFIED = object()
HISTORY_FIELDS = frozenset({"pr", "commit", "commits", "timeline", "reviews", "comments", "threads", "provider_timeline"})
PROOF_FIELDS = frozenset({"accepted_main", "history", "facts", "source_signature", "issue_contract_digest", "work_graph", "journal_tip", "absence_digest"})
AUTHORIZATION_FIELDS = frozenset({"schema_version", "kind", "domain", "authorization_id", "intent", "issued_at", "expires_at", "proof", "signer_identity", "signature", "authorization_digest"})
CLAIM_FIELDS = frozenset({"schema_version", "kind", "domain", "authorization", "publication_branch", "journal_predecessor_oid", "signer_identity", "signature", "publication_digest"})
SOURCE_SIGNATURE_FIELDS = frozenset({"repository", "head_sha", "tree_sha", "parent_shas", "signer_kind", "signer_identity", "signature_fingerprint", "signature_classification", "signature_policy_digest"})


class RetirementError(ValueError):
    """The exact terminal disposition is unavailable or unauthorized."""


class RetirementAttemptStopped(RetirementError):
    """A known attempted reservation permits observation only."""

    def __init__(self, claim_oid: str, stage: str):
        super().__init__("retirement attempt stopped; reconcile exact claim only")
        self.claim_oid = claim_oid
        self.stage = stage


def require_normal_initialization(repository: str, issue: int) -> None:
    """Absence and a different PR number cannot erase this delivery's history."""
    if repository == REPOSITORY and issue == ISSUE:
        raise RetirementError(SUCCESSOR_BLOCKER)


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise RetirementError(reason)


def _closed(value: Any, fields: frozenset[str], label: str) -> dict:
    _require(isinstance(value, dict) and set(value) == fields, label + " schema changed")
    _require(len(fast_path.canonical_json_bytes(value)) <= MAXIMUM_BYTES, label + " exceeds bound")
    return value


def _page(value: Any, label: str) -> list:
    # Exactly one native Link-paginated page, strictly below its full-page bound.
    _require(isinstance(value, list) and len(value) == 1 and isinstance(value[0], list), label + " pagination incomplete")
    _require(len(value[0]) < 100 and all(isinstance(v, dict) for v in value[0]), label + " exceeds native bound")
    return value[0]


def normalize_history(value: Any) -> dict:
    """Pure admission of the complete native representation, including failure."""
    history = _closed(value, HISTORY_FIELDS, "historical source")
    try:
        pr, commit = history["pr"], history["commit"]
        _require(pr["repository"] == REPOSITORY and pr["head_repository"] == REPOSITORY and pr["number"] == PR and type(pr["number"]) is int, "wrong historical identity")
        _require(pr["head_sha"] == HEAD and pr["base_ref"] == "main" and pr["created_at"] == CREATED_AT, "historical PR source/creation drift")
        _require(pr["draft"] is False and pr["merged"] is False and pr["merged_at"] is None and pr["state"] in {"open", "closed"}, "historical PR disposition drift")
        _require(commit["sha"] == HEAD and commit["commit"]["tree"]["sha"] == TREE and [p["sha"] for p in commit["parents"]] == [PARENT], "historical source topology drift")
        _require(commit["commit"]["verification"]["verified"] is True, "historical provider signature is unverified")
        commits = _page(history["commits"], "source commits")
        _require(len(commits) == 1 and commits[0]["sha"] == HEAD and [p["sha"] for p in commits[0]["parents"]] == [PARENT], "hidden or substituted source history")
        _require("SecPal-Validation-Receipt:" not in commit["commit"]["message"], "historical receipt substitution")
        timeline = _page(history["timeline"], "native timeline")
        _require(not any(e.get("event") == "closed" for e in timeline) if pr["state"] == "open" else sum(e.get("event") == "closed" for e in timeline) == 1, "historical closure chronology changed")
        _require(not any(e.get("event") in {"ready_for_review", "convert_to_draft", "head_ref_force_pushed", "reopened"} for e in timeline), "fabricated or changed Draft/Ready/source history")
        reviews = _page(history["reviews"], "provider reviews")
        _require(len(reviews) == len(REVIEWS) and {r["node_id"] for r in reviews} == set(REVIEWS), "hidden or substituted provider reviews")
        for review in reviews:
            _require(review["commit_id"] == HEAD and review["user"]["login"] == REVIEWS[review["node_id"]] and review["state"] == "COMMENTED", "provider review identity/head/state drift")
        _require([e.get("node_id") for e in timeline if e.get("event") == "reviewed"] == [r["node_id"] for r in reviews], "provider chronology incomplete")
        _require([e.get("sha") for e in timeline if e.get("event") == "committed"] == [HEAD], "native source chronology incomplete")
        comments = _page(history["comments"], "provider comments")
        _require(len(comments) == len(COMMENTS) and {c["node_id"] for c in comments} == COMMENTS, "hidden or substituted acquisition history")
        failure = next(c for c in comments if c["node_id"] == SECURITY_FAILURE)
        _require(failure["body"] == SECURITY_FAILURE_BODY and failure["user"]["login"] == "chatgpt-codex-connector[bot]", "Security failure misrepresented")
        _require([e.get("node_id") for e in timeline if e.get("event") == "commented"] == [c["node_id"] for c in comments], "acquisition chronology incomplete")
        providers = provider_acquisition._normalize_observation(history["provider_timeline"])
        _require(providers["repository"] == REPOSITORY and providers["pull_request"] == PR and providers["head"] == HEAD and providers["draft"] is False and providers["state"] == pr["state"].upper(), "independent provider chronology identity drift")
        _require([e["head"] for e in providers["events"] if e["kind"] == "COMMIT"] == [HEAD], "independent source chronology incomplete")
        _require(not any(e["kind"] in {"ReadyForReviewEvent", "ConvertToDraftEvent", "HeadRefForcePushedEvent", "HeadRefDeletedEvent", "HeadRefRestoredEvent"} for e in providers["events"]), "independent lifecycle chronology changed")
        for category, kind in ((comments, "IssueComment"), (reviews, "PullRequestReview")):
            native = [e for e in providers["events"] if e["kind"] == kind]
            _require([e["node_id"] for e in native] == [c["node_id"] for c in category], "provider source inventory incomplete")
            for event, source in zip(native, category):
                actor = source["user"]
                _require(event["body"] == source["body"] and event["database_id"] == source["id"] and event["actor"][1:] == (actor["node_id"], actor["id"]), "provider actor/body substitution")
                if kind == "IssueComment":
                    _require(event["created_at"] == source["created_at"] and event["updated_at"] == source["updated_at"], "provider edit chronology substituted")
                else:
                    _require(event["head"] == HEAD and event["created_at"] == source["submitted_at"] and event["state"] == source["state"], "provider review chronology substituted")
        graph = history["threads"]
        _require(not graph.get("errors"), "native thread observation incomplete")
        repo = graph["data"]["repository"]
        _require(repo["nameWithOwner"] == REPOSITORY and repo["pullRequest"]["number"] == PR and repo["pullRequest"]["id"] == pr["node_id"], "thread repository/PR substitution")
        connection = repo["pullRequest"]["reviewThreads"]
        _require(connection["totalCount"] == 2 and connection["pageInfo"]["hasNextPage"] is False and len(connection["nodes"]) == 2 and {t["id"] for t in connection["nodes"]} == THREADS, "hidden or substituted review threads")
        for thread in connection["nodes"]:
            _require(thread["isResolved"] is False and thread["isOutdated"] is False, "historical thread state changed")
            comments_connection = thread["comments"]
            _require(comments_connection["pageInfo"]["hasNextPage"] is False and comments_connection["totalCount"] == len(comments_connection["nodes"]) and 0 < len(comments_connection["nodes"]) < 100, "thread comment history incomplete")
            _require(all(c["originalCommit"]["oid"] == HEAD for c in comments_connection["nodes"]), "thread source head changed")
        return {
            "repository": REPOSITORY, "delivery_issue": ISSUE, "pull_request": PR,
            "head_sha": HEAD, "tree_sha": TREE, "ordered_parent_shas": [PARENT],
            "creation_disposition": "DRAFT_FIRST_VIOLATION", "actual_ready_transition_count": 0,
            "provider_review_object_count": 2, "canonical_review_consumption": "PROVENANCE_UNAVAILABLE",
            "conservative_reserved_review_count": authority.MAX_UNRESTRICTED_REVIEWS,
            "security_disposition": "FAILED_USAGE_LIMIT_NO_SUCCESS",
            "historical_receipt_disposition": "ISSUANCE_UNKNOWN",
            "native_history_digest": fast_path.digest_json(history),
        }
    except (KeyError, TypeError, StopIteration) as exc:
        raise RetirementError("historical native representation incomplete") from exc


def successor_eligibility(facts: dict) -> dict:
    """Truthful accounting disposition, without minting a lifecycle or budget."""
    _require(facts.get("repository") == REPOSITORY and facts.get("delivery_issue") == ISSUE and facts.get("pull_request") == PR and facts.get("creation_disposition") == "DRAFT_FIRST_VIOLATION" and type(facts.get("actual_ready_transition_count")) is int and facts.get("actual_ready_transition_count") == 0 and type(facts.get("conservative_reserved_review_count")) is int and facts.get("conservative_reserved_review_count") == authority.MAX_UNRESTRICTED_REVIEWS and facts.get("canonical_review_consumption") == "PROVENANCE_UNAVAILABLE", "successor accounting substitution or reset")
    return {
        "eligible": False, "maximum_successors": 1, "authorized_successors": 0,
        "review_authorized": False, "enrollment_authorized": False,
        "blocker": SUCCESSOR_BLOCKER,
        "required_order": ["AUTHENTICATED_TERMINAL_RETIREMENT", "AUTHENTICATED_NON_RESETTING_ACCOUNTING_AND_FIRST_READY_AUTHORITY", "SEPARATE_EXACT_HUMAN_SUCCESSOR_AUTHORIZATION", "ONE_GENUINE_DRAFT_SUCCESSOR", "EXACT_SOURCE_VALIDATION_AND_NATIVE_ADMISSION", "SEPARATE_EXACT_HUMAN_ASSESSMENT_AUTHORIZATION"],
    }


@dataclass(frozen=True)
class VerifiedHistoricalCase:
    proof: dict
    _seal: object


def _require_accepted_main(expected: str | None = None) -> tuple[Any, str]:
    actions = transport._load_actions_helper()
    main = actions._require_accepted_main_bridge_source(REPOSITORY, expected_main=expected)
    return actions, main


def _get(arguments: list[str]) -> Any:
    result = publication._run_gh(["api", "--hostname", "github.com", *arguments])
    _require(result.returncode == 0, "historical GitHub observation unavailable")
    _require(len(result.stdout) <= MAXIMUM_BYTES, "historical GitHub observation exceeds bound")
    return authority.loads_closed_json(result.stdout)


_THREAD_QUERY = '''query{repository(owner:"SecPal",name:".github"){nameWithOwner pullRequest(number:706){id number reviewThreads(first:100){totalCount pageInfo{hasNextPage} nodes{id isResolved isOutdated comments(first:100){totalCount pageInfo{hasNextPage} nodes{id databaseId body createdAt updatedAt originalCommit{oid} author{login} replyTo{id}}}}}}}}'''


def _observe_history() -> dict:
    pr = _get([f"repos/{REPOSITORY}/pulls/{PR}"])
    try:
        projected = {k: pr[k] for k in ("id", "node_id", "number", "state", "draft", "merged", "created_at", "closed_at", "merged_at")}
        projected.update(repository=pr["base"]["repo"]["full_name"], head_repository=pr["head"]["repo"]["full_name"], head_sha=pr["head"]["sha"], base_ref=pr["base"]["ref"])
    except (KeyError, TypeError) as exc:
        raise RetirementError("native historical PR observation incomplete") from exc
    result = {"pr": projected, "commit": _get([f"repos/{REPOSITORY}/commits/{HEAD}"]), "threads": _get(["graphql", "-f", "query=" + _THREAD_QUERY])}
    result["provider_timeline"] = _get(["graphql", "-f", "query=" + provider_acquisition._QUERY, "-f", "owner=SecPal", "-f", "name=.github", "-F", "number=706"])
    for name, endpoint in (("timeline", f"issues/{PR}/timeline"), ("reviews", f"pulls/{PR}/reviews"), ("comments", f"issues/{PR}/comments"), ("commits", f"pulls/{PR}/commits")):
        result[name] = _get([f"repos/{REPOSITORY}/{endpoint}?per_page=100", "--paginate", "--slurp"])
    return result


def _graph(actions: Any, number: int) -> dict:
    result = actions._run_pre_enrollment_work_graph(actions.REPOSITORY_ROOT, [str(actions.REPOSITORY_ROOT / "scripts/secpal-work-graph.py"), "validate-issue", f"{REPOSITORY}#{number}"])
    value = authority.loads_closed_json(result.stdout)
    # #676's pre-existing body-mirror advisory is not an identity/edge failure.
    _require(value.get("complete") is True and value.get("status") == "resolved" and value["issue"]["key"] == f"{REPOSITORY}#{number}" and value["issue"]["malformed"] is False, "native work graph incomplete")
    allowed = {"code": "body_relationship_mirror", "detail": "parent", "node": f"{REPOSITORY}#676"}
    _require(result.returncode == 0 or (number == 676 and result.returncode == 1 and value.get("findings") == [allowed]), "native work graph admission failed")
    return value


def authenticate_case() -> VerifiedHistoricalCase:
    """Accepted-main only; independently read every authority and race invalidator."""
    actions, main = _require_accepted_main()
    history = _observe_history()
    facts = normalize_history(history)
    _require(history["pr"]["state"] == "open" and history["pr"]["closed_at"] is None, "predecessor is not OPEN")
    graphs = {str(n): _graph(actions, n) for n in (ISSUE, 676, IMPLEMENTATION_ISSUE)}
    implementation = graphs[str(IMPLEMENTATION_ISSUE)]["issue"]
    _require(implementation["leaf"] is True and implementation["parent"] == f"{REPOSITORY}#1032", "implementation ownership changed")
    delivery = graphs[str(ISSUE)]["issue"]
    _require(delivery["parent"] is None and graphs["676"]["issue"]["parent"] == f"{REPOSITORY}#667", "native target parent changed")
    _require(delivery["open"] is True and delivery["leaf"] is True and delivery["claims"] and [c["pull_request"] for c in delivery["claims"]] == [f"{REPOSITORY}#{PR}"] and set(delivery["blocked_by"]) <= {f"{REPOSITORY}#{IMPLEMENTATION_ISSUE}"}, "delivery ownership or prerequisites changed")
    _require(f"{REPOSITORY}#{ISSUE}" in graphs["676"]["issue"]["blocked_by"], "downstream prerequisite changed")
    issue = _get([f"repos/{REPOSITORY}/issues/{ISSUE}"])
    _require(issue["number"] == ISSUE and issue["state"] == "open" and "pull_request" not in issue, "delivery issue changed")
    absence = publication.verify_pre_enrollment_absence(REPOSITORY, ISSUE)
    policy = authority._load_lifecycle_trust_policy(REPOSITORY)
    identity = execution._single_role_identity(policy.transition_signer_identities, "historical source signer")
    # The isolated journal transport fetches the exact source without executing it.
    with publication._isolated_repository(policy, write=False) as (root, credentials):
        fetched = publication._run_git(root, ["fetch", "--no-tags", policy.publication_remote_url, HEAD], extra_environment=credentials)
        _require(fetched.returncode == 0, "historical signed source unavailable")
        signed = execution._authenticate_source_commit(REPOSITORY, HEAD, identity, repository_root=root)
        signature = fast_path._integration_commit_authentication_binding(signed)
        _require(signature["tree_sha"] == TREE and signature["parent_shas"] == [PARENT] and signature["signer_kind"] == "SSH_PRINCIPAL", "independent source signature/topology changed")
    proof = {"accepted_main": main, "history": history, "facts": facts, "source_signature": signature, "issue_contract_digest": fast_path.digest_json({"number": ISSUE, "body": issue["body"]}), "work_graph": graphs, "journal_tip": absence.observed_tip_oid, "absence_digest": absence.evidence_digest}
    _require(_observe_history() == history, "historical evidence raced")
    _require(_get([f"repos/{REPOSITORY}/issues/{ISSUE}"])["body"] == issue["body"], "delivery contract raced")
    _require({str(n): _graph(actions, n) for n in (ISSUE, 676, IMPLEMENTATION_ISSUE)} == graphs, "work graph raced")
    _require(publication.verify_pre_enrollment_absence(REPOSITORY, ISSUE) == absence, "enrollment or journal raced")
    _require_accepted_main(main)
    return VerifiedHistoricalCase(proof, _VERIFIED)


def verify_authorization(value: Any) -> dict:
    """Verify signed intent offline; live equality and expiry belong to execution."""
    document = _closed(value, AUTHORIZATION_FIELDS, "retirement authorization")
    proof = _closed(document["proof"], PROOF_FIELDS, "retirement proof")
    _require(document["schema_version"] == "1.0" and document["kind"] == KIND and document["domain"] == DOMAIN and document["intent"] == INTENT, "retirement authority kind/intent changed")
    authority._require_identity(document["authorization_id"], "retirement authorization ID")
    authority._require_oid(proof["accepted_main"], "accepted main")
    authority._require_oid(proof["journal_tip"], "journal tip")
    for key in ("absence_digest", "issue_contract_digest"):
        authority._require_digest(proof[key], key)
    _require(type(document["issued_at"]) is int and type(document["expires_at"]) is int and 0 < document["expires_at"] - document["issued_at"] <= MAXIMUM_AUTHORIZATION_SECONDS, "retirement authorization bounds invalid")
    _require(normalize_history(proof["history"]) == proof["facts"] and proof["history"]["pr"]["state"] == "open" and proof["history"]["pr"]["closed_at"] is None, "signed historical facts substituted")
    source = _closed(proof["source_signature"], SOURCE_SIGNATURE_FIELDS, "source signature")
    _require(source["repository"] == REPOSITORY and source["head_sha"] == HEAD and source["tree_sha"] == TREE and source["parent_shas"] == [PARENT] and source["signer_kind"] == "SSH_PRINCIPAL", "signed source binding changed")
    policy = authority._load_lifecycle_trust_policy(REPOSITORY)
    _require(source["signer_identity"] in policy.transition_signer_identities, "historical source signer changed")
    authority._require_digest(source["signature_policy_digest"], "historical signature policy")
    _require_retirement_graph(proof)
    unsigned = {k: v for k, v in document.items() if k not in {"signature", "authorization_digest"}}
    authority._verify_signature(fast_path.canonical_json_bytes(unsigned), document["signature"], document["signer_identity"], DOMAIN, policy.transition_signer_identities, authority._policy_signature_verifier(policy))
    _require(document["authorization_digest"] == fast_path.digest_json({**unsigned, "signature": document["signature"]}), "retirement authority digest mismatch")
    return copy.deepcopy(document)


def issue_authorization(case: VerifiedHistoricalCase, *, authorization_id: str) -> dict:
    """A separately invoked exact human intent; never called by qualification."""
    _require(isinstance(case, VerifiedHistoricalCase) and case._seal is _VERIFIED, "retirement observation is not verifier-owned")
    fresh = authenticate_case()
    _require(fresh.proof == case.proof, "retirement issuance proof changed")
    case = fresh
    _require_retirement_graph(case.proof)
    _require_accepted_main(case.proof["accepted_main"])
    policy = authority._load_lifecycle_trust_policy(REPOSITORY)
    identity, signer = execution._policy_role_signer(policy, policy.transition_signer_identities, "retirement intent", allow_routine_default=True)
    now = int(time.time())
    fields = {"schema_version": "1.0", "kind": KIND, "domain": DOMAIN, "authorization_id": authority._require_identity(authorization_id, "retirement authorization ID"), "intent": INTENT, "issued_at": now, "expires_at": now + MAXIMUM_AUTHORIZATION_SECONDS, "proof": copy.deepcopy(case.proof), "signer_identity": identity}
    signed = {**fields, "signature": signer(fast_path.canonical_json_bytes(fields), DOMAIN)}
    document = {**signed, "authorization_digest": fast_path.digest_json(signed)}
    return verify_authorization(document)


def verify_claim(raw: bytes, *, branch: str, parent: str | None) -> dict:
    document = _closed(authority.loads_closed_json(raw), CLAIM_FIELDS, "retirement claim")
    _require(document["schema_version"] == "1.0" and document["kind"] == CLAIM_KIND and document["domain"] == CLAIM_DOMAIN, "retirement claim kind changed")
    authorization = verify_authorization(document["authorization"])
    policy = authority._load_lifecycle_trust_policy(REPOSITORY)
    _require(document["publication_branch"] == branch == policy.publication_branch and document["journal_predecessor_oid"] == parent == authorization["proof"]["journal_tip"], "retirement claim ancestry drift")
    absence = {
        "schema_version": "1.0", "kind": "VERIFIED_PRE_ENROLLMENT_LIFECYCLE_ABSENCE",
        "repository": REPOSITORY, "delivery_issue": ISSUE,
        "publication_branch": branch, "observed_tip_oid": parent,
        "current_publication": False, "native_genesis": False,
        "lifecycle_aware_head_advancement": False,
    }
    _require(authorization["proof"]["absence_digest"] == fast_path.digest_json(absence), "retirement absence evidence substituted")
    unsigned = {k: v for k, v in document.items() if k not in {"signature", "publication_digest"}}
    authority._verify_signature(fast_path.canonical_json_bytes(unsigned), document["signature"], document["signer_identity"], CLAIM_DOMAIN, policy.publication_signer_identities, authority._policy_signature_verifier(policy))
    _require(document["publication_digest"] == fast_path.digest_json({**unsigned, "signature": document["signature"]}), "retirement claim digest mismatch")
    return document


def verify_journal_claims(chronological: list, branch: str) -> dict | None:
    """One shared invariant owner for both maintained journal readers."""
    claim = None
    target_authority = False
    for oid, raw, parent in chronological:
        kind, candidate = publication._classify_journal_document(raw)
        if kind == CLAIM_KIND:
            _require(claim is None, "retirement replay or replacement chain")
            claim = verify_claim(raw, branch=branch, parent=parent)
            claim = {**claim, "object_oid": oid}
        elif candidate.get("repository") == REPOSITORY and candidate.get("delivery_issue") == ISSUE:
            target_authority = True
    _require(not (claim is not None and target_authority), "retirement conflicts with lifecycle admission/enrollment")
    return claim


def _claim_attempt(document: dict) -> str:
    """CAS ownership is one invocation's right to attempt closure, never reusable."""
    policy = authority._load_lifecycle_trust_policy(REPOSITORY)
    identity, signer = execution._policy_role_signer(policy, policy.publication_signer_identities, "retirement claim", allow_routine_default=True)
    publication._verify_live_protection(policy)
    with publication._isolated_repository(policy, write=True) as (root, credentials):
        tip = publication._observe_remote_current_once(root, policy.publication_remote_url, policy.publication_branch, credential_environment=credentials)
        _require(tip == document["proof"]["journal_tip"], "retirement journal raced")
        publication._walk_journal(root, tip, policy.publication_branch)
        fields = {"schema_version": "1.0", "kind": CLAIM_KIND, "domain": CLAIM_DOMAIN, "authorization": document, "publication_branch": policy.publication_branch, "journal_predecessor_oid": tip, "signer_identity": identity}
        signed = {**fields, "signature": signer(fast_path.canonical_json_bytes(fields), CLAIM_DOMAIN)}
        raw = fast_path.canonical_json_bytes({**signed, "publication_digest": fast_path.digest_json(signed)})
        oid = publication._write_publication_object(root, raw, tip)
        publication._walk_journal(root, oid, policy.publication_branch)
        # Any uncertain CAS stops before GitHub closure, even if later found.
        try:
            publication._cas_remote_ref(root, policy.publication_remote_url, policy.publication_branch, oid, tip, credential_environment=credentials)
        except publication.LifecyclePublicationError as exc:
            raise RetirementAttemptStopped(oid, "CLAIM_CAS_AMBIGUOUS") from exc
        try:
            observed = publication._observe_remote_current_once(root, policy.publication_remote_url, policy.publication_branch, credential_environment=credentials)
            _require(observed == oid, "retirement claim read-back ambiguous")
            publication._walk_journal(root, observed, policy.publication_branch)
        except ValueError as exc:
            raise RetirementAttemptStopped(oid, "CLAIM_READBACK_UNCERTAIN") from exc
    try:
        publication._verify_live_protection(policy)
    except ValueError as exc:
        raise RetirementAttemptStopped(oid, "CLAIM_PROTECTION_READBACK_FAILED") from exc
    return oid


def _close_once() -> str:
    # Exact endpoint and sole state field; no generic GitHub write capability.
    try:
        result = publication._run_gh(["api", "--hostname", "github.com", "--include", "--method", "PATCH", f"repos/{REPOSITORY}/pulls/{PR}", "-f", "state=closed"])
    except publication.LifecyclePublicationError:
        return "AMBIGUOUS"
    try:
        header, body = result.stdout.replace(b"\r\n", b"\n").split(b"\n\n", 1)
        status = re.fullmatch(rb"HTTP/[0-9.]+ ([0-9]{3})(?: [^\n]*)?", header.split(b"\n", 1)[0])
        if status is not None and int(status[1]) in {400, 401, 403, 404, 409, 410, 422}:
            return "REJECTED"
        if result.returncode != 0 or status is None or int(status[1]) != 200:
            return "AMBIGUOUS"
        response = authority.loads_closed_json(body)
        return "SUCCESS" if isinstance(response, dict) and response.get("number") == PR and response.get("state") == "closed" and response.get("merged") is False else "AMBIGUOUS"
    except ValueError:
        return "AMBIGUOUS"


def classify_close_result(write_result: str, *, closed_and_preserved: bool) -> str:
    _require(write_result in {"SUCCESS", "REJECTED", "AMBIGUOUS"} and type(closed_and_preserved) is bool, "unknown retirement mutation result")
    if closed_and_preserved:
        return "RETIRED_UNMERGED_VERIFIED"
    return "REJECTED_ATTEMPT_CONSUMED" if write_result == "REJECTED" else "RETIREMENT_INDETERMINATE_OBSERVATION_ONLY"


def _read_back(document: dict, claim_oid: str) -> bool:
    """One bounded independent read, preserving history except native closure."""
    observed = _observe_history()
    original = document["proof"]["history"]
    normalize_history(observed)
    if observed["pr"]["state"] != "closed" or observed["pr"]["closed_at"] is None:
        return False
    before = copy.deepcopy(original)
    after = copy.deepcopy(observed)
    after["pr"]["state"], after["pr"]["closed_at"] = before["pr"]["state"], before["pr"]["closed_at"]
    after["provider_timeline"]["data"]["repository"]["pullRequest"]["state"] = before["provider_timeline"]["data"]["repository"]["pullRequest"]["state"]
    old_timeline = _page(before["timeline"], "original timeline")
    new_timeline = _page(after["timeline"], "retired timeline")
    closures = [e for e in new_timeline if e.get("event") == "closed"]
    _require(len(closures) == 1 and closures[0]["actor"]["login"] == document["proof"]["work_graph"][str(ISSUE)]["issue"]["claims"][0]["executor"], "retirement closure actor/history ambiguous")
    after["timeline"] = [[e for e in new_timeline if e.get("event") != "closed"]]
    _require(after == before and len(new_timeline) == len(old_timeline) + 1, "historical evidence changed during retirement")
    actions, _ = _require_accepted_main(document["proof"]["accepted_main"])
    delivery = _graph(actions, ISSUE)["issue"]
    _require(delivery["open"] is True and delivery["claims"] == [] and f"{REPOSITORY}#{ISSUE}" in _graph(actions, 676)["issue"]["blocked_by"], "retirement did not release only original claim")
    issue = _get([f"repos/{REPOSITORY}/issues/{ISSUE}"])
    _require(fast_path.digest_json({"number": ISSUE, "body": issue["body"]}) == document["proof"]["issue_contract_digest"], "retirement changed delivery contract")
    policy = authority._load_lifecycle_trust_policy(REPOSITORY)
    publication._verify_live_protection(policy)
    with publication._isolated_repository(policy, write=False) as (root, credentials):
        tip = publication._observe_remote_current_once(root, policy.publication_remote_url, policy.publication_branch, credential_environment=credentials)
        publication._walk_journal(root, tip, policy.publication_branch)
        raw, parent = publication._read_publication_object(root, claim_oid)
        claim = verify_claim(raw, branch=policy.publication_branch, parent=parent)
        _require(claim["authorization"] == document, "retirement claim read-back changed")
        # A source commit merely present in the fetch is not reachable authority.
        reachable = publication._run_git(root, ["merge-base", "--is-ancestor", claim_oid, tip])
        _require(reachable.returncode == 0, "retirement claim is not protected ancestry")
    _require(_observe_history() == observed, "retirement read-back raced")
    return True


def retire(value: Any) -> dict:
    """One separately authorized operation; no blind retry at either boundary."""
    _require_accepted_main()
    document = verify_authorization(value)
    _require(document["issued_at"] <= time.time() < document["expires_at"], "retirement authorization expired")
    current = authenticate_case()
    _require(current.proof == document["proof"], "retirement authority stale or substituted")
    _require_retirement_graph(current.proof)
    claim_oid = _claim_attempt(document)
    # Fresh native equality after reserving the attempt. A race strands the
    # claim and authorizes observation only, rather than another claim/write.
    try:
        _verify_preclose(document)
    except (ValueError, fast_path.SecurityBlocker, RuntimeError) as exc:
        raise RetirementAttemptStopped(claim_oid, "POST_CLAIM_PRECONDITION_FAILED") from exc
    result = _close_once()
    try:
        persisted = _read_back(document, claim_oid)
    except (ValueError, fast_path.SecurityBlocker, execution.LifecycleExecutionError):
        persisted = False
    return {"status": classify_close_result(result, closed_and_preserved=persisted), "write_result": result, "claim_oid": claim_oid, "github_attempts": 1, "successor": successor_eligibility(document["proof"]["facts"])}


def _require_retirement_graph(proof: dict) -> None:
    try:
        graph = proof["work_graph"]
        _require(graph[str(ISSUE)]["issue"]["blocked"] is False and graph[str(IMPLEMENTATION_ISSUE)]["issue"]["done"] is True, "retirement prerequisites have not completed")
    except (KeyError, TypeError) as exc:
        raise RetirementError("retirement graph proof incomplete") from exc


def _verify_preclose(document: dict) -> None:
    actions, _ = _require_accepted_main(document["proof"]["accepted_main"])
    _require(_observe_history() == document["proof"]["history"], "retirement source/history raced after claim")
    _require({str(n): _graph(actions, n) for n in (ISSUE, 676, IMPLEMENTATION_ISSUE)} == document["proof"]["work_graph"], "retirement graph raced after claim")
    issue = _get([f"repos/{REPOSITORY}/issues/{ISSUE}"])
    _require(fast_path.digest_json({"number": ISSUE, "body": issue["body"]}) == document["proof"]["issue_contract_digest"], "delivery contract raced after claim")
    expected_actor = document["proof"]["work_graph"][str(ISSUE)]["issue"]["claims"][0]["executor"]
    _require(_get(["user"])["login"] == expected_actor, "retirement operator identity changed")
    _require(document["issued_at"] <= time.time() < document["expires_at"], "retirement authorization expired after claim")


def reconcile(value: Any, claim_oid: str) -> dict:
    """Observation only after any partial/uncertain attempt; no write path."""
    _require_accepted_main()
    document = verify_authorization(value)
    authority._require_oid(claim_oid, "retirement claim")
    persisted = _read_back(document, claim_oid)
    return {"status": classify_close_result("AMBIGUOUS", closed_and_preserved=persisted), "github_attempts": 0, "claim_oid": claim_oid, "successor": successor_eligibility(document["proof"]["facts"])}
