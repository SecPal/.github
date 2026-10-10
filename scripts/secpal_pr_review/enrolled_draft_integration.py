# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Closed initial-Draft source and current-main operations using maintained authority.

Preparation creates and authorizes a single immutable signed candidate after
Complete Validation. Execution cannot create a commit: it consumes that exact
authorization once in the protected publication journal, pushes only its bound
PR branch, and publishes HEAD_ADVANCED. Explicit reconciliation never pushes.
"""

from __future__ import annotations

import copy
from pathlib import Path
import subprocess
import tempfile
import time
from typing import Any
from urllib.parse import quote

from . import fast_path, lifecycle_authority as authority
from . import lifecycle_execution as execution, lifecycle_publication as publication
from . import pre_enrollment_integration as draft
from . import bootstrap_source_admission

KIND = "ENROLLED_DRAFT_CURRENT_MAIN_INTEGRATION"
SOURCE_KIND = "ENROLLED_DRAFT_SOURCE_ADVANCEMENT"
MAXIMUM_SOURCE_AUTHORIZATION_SECONDS = 900
AUTHORIZATION_KIND = KIND + "_AUTHORIZATION"
AUTHORIZATION_DOMAIN = "secpal.enrolled-draft-current-main-integration-authorization/v1"
PREPARATION_AUTHORIZATION_KIND = KIND + "_PREPARATION_AUTHORIZATION"
PREPARATION_AUTHORIZATION_DOMAIN = "secpal.enrolled-draft-current-main-integration-preparation/v1"
POLICY = {
    "schema_version": "1.0", "command": "integrate-enrolled-draft",
    "topology_kind": KIND, "allowed_mutation": "NON_FORCE_PUSH_EXACT_PR_BRANCH",
    "maximum_candidates": 1, "maximum_pushes": 1, "force_push": False,
    "automatic_retry": False, "merge_pull_request": False,
}
SOURCE_POLICY = {
    **POLICY, "command": "advance-enrolled-draft-source",
    "topology_kind": SOURCE_KIND,
    "maximum_authorization_age_seconds": MAXIMUM_SOURCE_AUTHORIZATION_SECONDS,
}
EVIDENCE_FIELDS = frozenset({
    "schema_version", "kind", "repository", "delivery_issue", "pull_request",
    "lifecycle_id", "initialization_evidence_digest", "current_publication_oid",
    "current_publication_digest", "predecessor_authority_digest", "draft_head_sha",
    "current_main", "ordered_parent_shas", "validated_tree_sha", "tree_evidence",
    "head_ref", "work_graph_digest", "registry_digest", "command_set_digest",
    "expected_signer",
    "manual_gate_evidence",
})
AUTHORIZATION_FIELDS = frozenset({
    "schema_version", "kind", "authorization_id", "evidence", "validation_receipt",
    "final_attestation", "signer_identity", "signature", "authorization_digest",
    "preparation_authorization_digest",
})
PREPARATION_AUTHORIZATION_FIELDS = AUTHORIZATION_FIELDS - {"final_attestation", "preparation_authorization_digest"}
TRAILERS = ("SecPal-Enrolled-Draft-Integration", "SecPal-Enrolled-Draft-Validation-Receipt")


def authorization_kind(kind, *, preparation=False):
    if not isinstance(kind, str) or kind not in {KIND, SOURCE_KIND}:
        raise fast_path.SecurityBlocker("unsupported enrolled Draft operation")
    return kind + ("_PREPARATION_AUTHORIZATION" if preparation else "_AUTHORIZATION")


def authorization_domain(kind, *, preparation=False):
    authorization_kind(kind, preparation=preparation)
    if kind == KIND:
        return PREPARATION_AUTHORIZATION_DOMAIN if preparation else AUTHORIZATION_DOMAIN
    return "secpal.enrolled-draft-source-advancement-" + ("preparation/v1" if preparation else "authorization/v1")


def validation_trailers(evidence):
    authorization_kind(evidence["kind"])
    return ("SecPal-Enrolled-Draft-Source", "SecPal-Validation-Receipt") if evidence["kind"] == SOURCE_KIND else TRAILERS


def require_fresh_source_authorization(evidence):
    """Observe time only at mutation admission; reconciliation grants no push."""
    if evidence["kind"] == SOURCE_KIND:
        bounds = evidence["user_authorization"]
        if not bounds["issued_at"] <= time.time() < bounds["expires_at"]:
            raise fast_path.SecurityBlocker("source authorization is stale or not yet valid")


def require_initial_native_draft(current: publication.VerifiedLifecyclePublication) -> None:
    lifecycle = current.lifecycle
    if (
        lifecycle.historical_proof_mode != authority.NATIVE_PROOF_MODE
        or fast_path.canonical_json_bytes(lifecycle.state)
        != fast_path.canonical_json_bytes(authority.initial_state())
        or current.serialized_lifecycle_evidence is None
    ):
        raise fast_path.SecurityBlocker("integration requires authenticated initial native Draft CURRENT")
    bundle = publication._native_bundle(authority.loads_closed_json(current.serialized_lifecycle_evidence))
    initialization = bundle.get("delivery_initialization")
    events = bundle.get("transition_authorizations")
    if (not isinstance(initialization, dict) or initialization.get("pull_request") != lifecycle.pull_request
            or not isinstance(events, list) or not events
            or events[0].get("transition_kind") != "INITIALIZED_DRAFT"
            or any(event.get("transition_kind") != "HEAD_ADVANCED" for event in events[1:])):
        raise fast_path.SecurityBlocker("integration excludes review, correction, exceptional and replacement histories")


def current_binding(current: publication.VerifiedLifecyclePublication) -> dict[str, Any]:
    require_initial_native_draft(current)
    lifecycle = current.lifecycle
    return {
        "repository": lifecycle.repository, "delivery_issue": lifecycle.delivery_issue,
        "pull_request": lifecycle.pull_request, "lifecycle_id": lifecycle.lifecycle_id,
        "initialization_evidence_digest": lifecycle.initialization_evidence_digest,
        "current_publication_oid": current.publication_oid,
        "current_publication_digest": current.publication_digest,
        "predecessor_authority_digest": lifecycle.authority_digest,
        "draft_head_sha": lifecycle.head_sha,
    }


def normalize_evidence(value: Any) -> dict[str, Any]:
    source = isinstance(value, dict) and value.get("kind") == SOURCE_KIND
    fields = (EVIDENCE_FIELDS - {"current_main", "tree_evidence"}) | {"user_authorization"} if source else EVIDENCE_FIELDS
    item = draft._closed(value, fields, "enrolled Draft source/integration evidence")
    if item["kind"] not in {KIND, SOURCE_KIND} or item["schema_version"] != "1.0":
        raise fast_path.SecurityBlocker("enrolled Draft operation kind/version is unsupported")
    draft._repository(item["repository"])
    for key in ("delivery_issue", "pull_request"):
        draft._positive(item[key], key)
    for key in ("lifecycle_id", "head_ref", "expected_signer"):
        draft._identity(item[key], key)
    for key in ("initialization_evidence_digest", "current_publication_digest",
                "predecessor_authority_digest", "work_graph_digest", "registry_digest",
                "command_set_digest"):
        draft._digest(item[key], key)
    for key in ("current_publication_oid", "draft_head_sha", "validated_tree_sha"):
        draft._oid(item[key], key)
    if source:
        bounds = draft._closed(item["user_authorization"], frozenset({"issued_at", "expires_at"}), "source authorization bounds")
        if any(type(bounds[key]) is not int or bounds[key] <= 0 for key in bounds) or not 0 < bounds["expires_at"] - bounds["issued_at"] <= MAXIMUM_SOURCE_AUTHORIZATION_SECONDS:
            raise fast_path.SecurityBlocker("source authorization freshness bounds are invalid")
        if item["ordered_parent_shas"] != [item["draft_head_sha"]]:
            raise fast_path.SecurityBlocker("source advancement requires the sole CURRENT parent")
        if item["head_ref"] == "main" or item["head_ref"].startswith("refs/"):
            raise fast_path.SecurityBlocker("source branch identity is invalid")
        return copy.deepcopy(item)
    main = draft._closed(item["current_main"], frozenset({"ref", "sha"}), "current main")
    if main["ref"] != "main" or item["head_ref"] == main["ref"]:
        raise fast_path.SecurityBlocker("integration branch identity is invalid")
    draft._oid(main["sha"], "current main")
    if item["ordered_parent_shas"] != [item["draft_head_sha"], main["sha"]] or item["draft_head_sha"] == main["sha"]:
        raise fast_path.SecurityBlocker("integration requires exact ordered CURRENT/main parents")
    tree = draft._closed(item["tree_evidence"], frozenset({
        "mechanical_merge_tree_sha", "mechanical_conflict_paths",
        "manual_conflict_resolution_delta", "path_classifications",
    }), "integration tree evidence")
    draft._oid(tree["mechanical_merge_tree_sha"], "mechanical tree")
    draft._paths(tree["mechanical_conflict_paths"])
    draft._delta(tree["manual_conflict_resolution_delta"])
    classifications = tree["path_classifications"]
    delta_paths = [item["path"] for item in tree["manual_conflict_resolution_delta"]]
    if not isinstance(classifications, list) or any(
        not isinstance(item, dict) or set(item) != {"path", "classification"}
        or item["classification"] not in {"CONFLICT_RESOLUTION", "EXACT_PARENT2_PRESERVATION"}
        for item in classifications
    ) or [item["path"] for item in classifications] != delta_paths:
        raise fast_path.SecurityBlocker("integration path classifications are not closed")
    return copy.deepcopy(item)


def normalize_authorization(value: Any, *, allow_preparation: bool = False) -> dict[str, Any]:
    kind = value.get("evidence", {}).get("kind") if isinstance(value, dict) and isinstance(value.get("evidence"), dict) else None
    expected_preparation = authorization_kind(kind, preparation=True)
    preparation = allow_preparation and value.get("kind") == expected_preparation
    item = draft._closed(value, PREPARATION_AUTHORIZATION_FIELDS if preparation else AUTHORIZATION_FIELDS, "enrolled Draft authorization")
    expected_kind = authorization_kind(kind, preparation=preparation)
    domain = authorization_domain(kind, preparation=preparation)
    if item["schema_version"] != "1.0" or item["kind"] != expected_kind:
        raise fast_path.SecurityBlocker("enrolled Draft authorization kind/version is unsupported")
    draft._identity(item["authorization_id"], "authorization identity")
    evidence = normalize_evidence(item["evidence"])
    signer = draft._identity(item["signer_identity"], "authorization signer")
    if signer != evidence["expected_signer"]:
        raise fast_path.SecurityBlocker("authorization signer differs from maintained integration signer")
    signature = draft._signature(item["signature"], signer)
    if signature["format"] != "ssh":
        raise fast_path.SecurityBlocker("new integration authorization requires SSH")
    unsigned = {key: copy.deepcopy(val) for key, val in item.items() if key not in {"signature", "authorization_digest"}}
    signed = {**unsigned, "signature": signature}
    if item["authorization_digest"] != fast_path.digest_json(signed):
        raise fast_path.SecurityBlocker("integration authorization digest mismatch")
    receipt = fast_path.create_enrolled_draft_validation_receipt(evidence)
    if item["validation_receipt"] != receipt:
        raise fast_path.SecurityBlocker("integration validation receipt/tree mismatch")
    if not preparation:
        draft._digest(item["preparation_authorization_digest"], "preparation authorization")
        attestation = item["final_attestation"]
        if not isinstance(attestation, dict):
            raise fast_path.SecurityBlocker("integration final attestation is malformed")
        expected = fast_path.create_enrolled_draft_final_attestation(
            evidence, receipt, candidate_head_sha=attestation.get("candidate_head_sha"),
            signature_fingerprint=attestation.get("signature_fingerprint"),
        )
        if attestation != expected:
            raise fast_path.SecurityBlocker("integration final attestation mismatch")
    policy = authority._load_lifecycle_trust_policy(evidence["repository"])
    authority._verify_signature(
        fast_path.canonical_json_bytes(unsigned), signature, signer,
        domain, policy.transition_signer_identities,
        authority._policy_signature_verifier(policy),
    )
    return copy.deepcopy(item)


def require_predecessor(current, evidence) -> None:
    bound = current_binding(current)
    if bound != {key: evidence[key] for key in bound}:
        raise fast_path.SecurityBlocker("enrolled Draft CURRENT predecessor is stale or substituted")


def _trusted_source(actions, repository):
    main = actions._require_accepted_main_bridge_source(repository)
    expected = actions.REPOSITORY_ROOT / "scripts/secpal_pr_review/enrolled_draft_integration.py"
    if Path(__file__).resolve() != expected.resolve() or Path(__spec__.origin).resolve() != expected.resolve():
        raise fast_path.SecurityBlocker("enrolled Draft integration import provenance changed")
    actions._require_exact_accepted_main_blob(actions.REPOSITORY_ROOT, main, str(expected.relative_to(actions.REPOSITORY_ROOT)))
    modules = {"authority": authority, "execution": execution, "publication": publication, "draft": draft, "fast_path": fast_path, "bootstrap": bootstrap_source_admission}
    actions._require_bridge_import_provenance(
        {name: (module.__file__, module.__spec__.origin) for name, module in modules.items()},
        {"authority": actions.REPOSITORY_ROOT / "scripts/secpal_pr_review/lifecycle_authority.py",
         "execution": actions.REPOSITORY_ROOT / "scripts/secpal_pr_review/lifecycle_execution.py",
         "publication": actions.REPOSITORY_ROOT / "scripts/secpal_pr_review/lifecycle_publication.py",
         "draft": actions.REPOSITORY_ROOT / "scripts/secpal_pr_review/pre_enrollment_integration.py",
         "fast_path": actions.REPOSITORY_ROOT / "scripts/secpal_pr_review/fast_path.py",
         "bootstrap": actions.REPOSITORY_ROOT / "scripts/secpal_pr_review/bootstrap_source_admission.py"},
    )
    return main


def _entry(actions, repository, kind=KIND):
    entry = actions.select_repository(actions.load_registry(), repository)
    binding = actions._fast_registry_binding(entry)
    authorization_kind(kind)
    key, policy = ("enrolled_draft_source_advancement_policy", SOURCE_POLICY) if kind == SOURCE_KIND else ("enrolled_draft_integration_policy", POLICY)
    if fast_path.canonical_json_bytes(binding.get(key)) != fast_path.canonical_json_bytes(policy):
        raise fast_path.SecurityBlocker("repository has no closed enrolled Draft operation policy")
    return entry, binding


def _work_graph(actions, repository, issue):
    try:
        result = actions._run_pre_enrollment_work_graph(actions.REPOSITORY_ROOT, [
            str(actions.REPOSITORY_ROOT / "scripts/secpal-work-graph.py"),
            "validate-issue", f"{repository}#{issue}",
        ])
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise fast_path.RecoverableLocalError("work graph observation is unavailable") from exc
    value = draft.loads_closed_json(result.stdout)
    if result.returncode != 0:
        raise fast_path.SecurityBlocker("work graph does not authorize enrolled Draft integration")
    digest = fast_path.digest_json(value)
    actions._verify_pre_enrollment_work_graph_result(value, repository=repository, delivery_issue=issue, expected_digest=digest)
    return value


def _graph(actions, repository, issue):
    return fast_path.digest_json(_work_graph(actions, repository, issue))


def _live(actions, repository, issue, pr, head, main, head_ref=None):
    live = actions.LiveGitHub().observe_ready_integration_authority(repository, pr)
    if (
        live.get("repository") != repository or live.get("head_repository") != repository
        or live.get("base_repository") != repository or live.get("pull_request_number") != pr
        or live.get("state") != "OPEN" or live.get("draft") is not True
        or live.get("head_sha") != head or live.get("base_ref") != "main"
        or live.get("base_sha") != main or live.get("closing_issues_complete") is not True
        or live.get("closing_issues") != [{"repository": repository, "number": issue, "state": "OPEN"}]
        or not isinstance(live.get("head_ref"), str) or not live["head_ref"]
        or live["head_ref"] == "main" or (head_ref is not None and live["head_ref"] != head_ref)
    ):
        raise fast_path.SecurityBlocker("exact open same-repository Draft PR identity drifted")
    # The canonical graph reader supplies the complete native primary-PR claim
    # inventory. A second open PR must not gain branch authority via closing text.
    graph = _work_graph(actions, repository, issue)
    claims = graph.get("issue", {}).get("claims")
    if not isinstance(claims, list) or len(claims) != 1:
        raise fast_path.SecurityBlocker("delivery does not have exactly one primary PR")
    claim = claims[0]
    if claim.get("pull_request") != f"{repository}#{pr}":
        raise fast_path.SecurityBlocker("delivery primary PR differs from CURRENT")
    checked = actions._run_attestation_git(actions.REPOSITORY_ROOT, ["check-ref-format", f'refs/heads/{live["head_ref"]}'], allow_failure=True)
    if checked.returncode != 0:
        raise fast_path.SecurityBlocker("integration PR branch is unsafe")
    return live["head_ref"]


def _tree(actions, root, evidence):
    if evidence["kind"] == SOURCE_KIND:
        before = actions._run_attestation_git(root, ["rev-parse", evidence["draft_head_sha"] + "^{tree}"])
        if before.returncode != 0 or before.stdout.strip() == evidence["validated_tree_sha"]:
            raise fast_path.SecurityBlocker("source successor has no authenticated source delta")
        return
    observed = fast_path.derive_ready_integration_tree_evidence(
        root, evidence["ordered_parent_shas"], evidence["validated_tree_sha"],
        schema_version="1.0", kind=KIND, run_git=actions._run_attestation_git,
    )
    if observed != evidence["tree_evidence"]:
        raise fast_path.SecurityBlocker("candidate-local integration evidence differs from mechanical derivation")


def _commit(actions, root, evidence, head):
    policy = authority._load_lifecycle_trust_policy(evidence["repository"])
    verified = fast_path.authenticate_integration_commit(
        repository_root=root, repository=evidence["repository"], head_sha=head,
        expected_signer={"kind": "SSH_PRINCIPAL", "identity": evidence["expected_signer"]},
        signature_policy=execution._source_signature_policy(policy),
    )
    signer = policy.signers.get(evidence["expected_signer"])
    if (
        signer is None or verified.signer_kind != "SSH_PRINCIPAL"
        or verified.signature_fingerprint not in {execution._ssh_public_key_fingerprint(key) for key in signer.ssh_public_keys}
        or verified.tree_sha != evidence["validated_tree_sha"]
        or list(verified.parent_shas) != evidence["ordered_parent_shas"]
    ):
        raise fast_path.SecurityBlocker("candidate topology, tree or maintained signer changed")
    return verified


def prepare(actions, arguments, *, kind=KIND) -> int:
    """Validate, create one signed candidate, then sign its exact authorization."""
    if not arguments.apply:
        raise fast_path.SecurityBlocker("candidate preparation requires --apply")
    _trusted_source(actions, arguments.repo)
    entry, binding = _entry(actions, arguments.repo, kind)
    root = Path(arguments.repo_root).resolve(strict=True)
    actions._require_distinct_candidate_repository_root(root)
    current = publication.verify_current_lifecycle_authority(arguments.repo, arguments.delivery_issue)
    bound = current_binding(current)
    if bound["pull_request"] != arguments.pr:
        raise fast_path.SecurityBlocker("PR differs from authenticated CURRENT")
    main = actions._authenticate_protected_bridge_main(arguments.repo)
    graph = _graph(actions, arguments.repo, arguments.delivery_issue)
    head_ref = _live(actions, arguments.repo, arguments.delivery_issue, arguments.pr, bound["draft_head_sha"], main)
    head, status = actions._attestation_local_state(root, arguments.repo)
    if head != bound["draft_head_sha"]:
        raise fast_path.SecurityBlocker("local delivery head differs from CURRENT")
    if kind == KIND:
        necessary = actions._run_attestation_git(root, ["merge-base", "--is-ancestor", main, head], allow_failure=True)
        if necessary.returncode != 1:
            raise fast_path.SecurityBlocker("current-main reconciliation is unnecessary or ancestry unavailable")
    tree = actions._staged_tree(root, status)
    policy = authority._load_lifecycle_trust_policy(arguments.repo)
    signer_id = execution._single_role_identity(policy.transition_signer_identities, "integration signer")
    signers = execution._production_signing_authorities(arguments.repo, signer_id)
    if kind == SOURCE_KIND:
        if (arguments.expected_predecessor, arguments.authorized_tree, arguments.expected_signer) != (head, tree, signer_id):
            raise fast_path.SecurityBlocker("explicit user source authorization differs from exact predecessor, tree or signer")
        operation_evidence = {
            "ordered_parent_shas": [head],
            "user_authorization": {"issued_at": int(time.time()), "expires_at": arguments.expires_at},
        }
    else:
        operation_evidence = {
            "current_main": {"ref": binding["default_branch"], "sha": main},
            "ordered_parent_shas": [head, main],
            "tree_evidence": fast_path.derive_ready_integration_tree_evidence(root, [head, main], tree, schema_version="1.0", kind=KIND, run_git=actions._run_attestation_git),
        }
    evidence = normalize_evidence({
        "schema_version": "1.0", "kind": kind, **bound, **operation_evidence,
        "validated_tree_sha": tree,
        "head_ref": head_ref, "work_graph_digest": graph,
        "registry_digest": fast_path.digest_json(binding),
        "command_set_digest": fast_path.digest_json(binding["validation"]),
        "expected_signer": signer_id,
        "manual_gate_evidence": fast_path.validate_manual_gate_evidence(
            actions._read_pre_enrollment_json(arguments.manual_gate_evidence, "manual gate evidence"),
            binding["manual_gates"],
        ),
    })
    if kind == SOURCE_KIND:
        _tree(actions, root, evidence)
    require_fresh_source_authorization(evidence)
    directory = Path(arguments.operation_directory)
    directory.mkdir(mode=0o700, parents=False, exist_ok=False)
    # Exclusive preparation directory is diagnostic evidence, never authority.
    # A crash here cannot authorize execution or reconstruct another candidate.
    if not actions._run_registered_validations(entry, root):
        raise fast_path.SecurityBlocker("Complete Validation failed for integrated tree")
    if actions._attestation_local_state(root, arguments.repo) != (head, status) or actions._staged_tree(root, status) != tree:
        raise fast_path.SecurityBlocker("candidate changed during Complete Validation")
    _trusted_source(actions, arguments.repo)
    require_predecessor(publication.verify_current_lifecycle_authority(arguments.repo, arguments.delivery_issue), evidence)
    if (kind == KIND and actions._authenticate_protected_bridge_main(arguments.repo) != main) or _graph(actions, arguments.repo, arguments.delivery_issue) != graph:
        raise fast_path.SecurityBlocker("main or work graph changed during validation")
    _live(actions, arguments.repo, arguments.delivery_issue, arguments.pr, head, main if kind == KIND else actions._authenticate_protected_bridge_main(arguments.repo), head_ref)
    require_fresh_source_authorization(evidence)
    receipt = fast_path.create_enrolled_draft_validation_receipt(evidence)
    preparation_fields = {
        "schema_version": "1.0", "kind": authorization_kind(kind, preparation=True),
        "authorization_id": arguments.authorization_id, "evidence": evidence,
        "validation_receipt": receipt, "signer_identity": signer_id,
    }
    preparation_signed = {**preparation_fields, "signature": dict(signers.transition_signer(fast_path.canonical_json_bytes(preparation_fields), authorization_domain(kind, preparation=True)))}
    preparation = normalize_authorization({**preparation_signed, "authorization_digest": fast_path.digest_json(preparation_signed)}, allow_preparation=True)
    actions._write_fast_report(str(directory / "preparation.json"), preparation)
    # The predecessor-scoped protected reservation is acquired before the sole
    # commit-tree call. Other directories, IDs, processes or clones cannot mint
    # a second candidate. A lost reservation response never grants ownership.
    publication.claim_enrolled_draft_integration(preparation, signer_identity=signers.publication_identity, signer=signers.publication_signer)
    trailers = dict(zip(validation_trailers(evidence), (fast_path.digest_json(evidence), receipt["receipt_digest"])))
    subject = "Advance enrolled Draft delivery source" if kind == SOURCE_KIND else "Integrate protected main into enrolled Draft delivery"
    message = subject + "\n\n" + "".join(f"{key}: {value}\n" for key, value in trailers.items())
    require_fresh_source_authorization(evidence)
    commit_arguments = ["commit-tree", "-S", tree]
    for parent in evidence["ordered_parent_shas"]:
        commit_arguments.extend(["-p", parent])
    try:
        created = actions._create_signed_pre_enrollment_commit(root, commit_arguments, message)
    except (actions.evidence.CommandPolicyError, OSError, subprocess.TimeoutExpired) as exc:
        raise fast_path.SecurityBlocker("signed enrolled Draft candidate creation unavailable; no retry") from exc
    candidate = created.stdout.strip()
    if created.returncode != 0:
        raise fast_path.SecurityBlocker("signed enrolled Draft candidate creation failed; no retry")
    verified = _commit(actions, root, evidence, candidate)
    attestation = fast_path.create_enrolled_draft_final_attestation(evidence, receipt, candidate_head_sha=candidate, signature_fingerprint=verified.signature_fingerprint)
    fields = {
        "schema_version": "1.0", "kind": authorization_kind(kind),
        "authorization_id": arguments.authorization_id, "evidence": evidence,
        "validation_receipt": receipt, "final_attestation": attestation,
        "preparation_authorization_digest": preparation["authorization_digest"],
        "signer_identity": signer_id,
    }
    signed = {**fields, "signature": dict(signers.transition_signer(fast_path.canonical_json_bytes(fields), authorization_domain(kind)))}
    authorization = normalize_authorization({**signed, "authorization_digest": fast_path.digest_json(signed)})
    actions._write_fast_report(str(directory / "authorization.json"), authorization)
    return 0


def _verify_candidate_package(actions, root, authorization):
    evidence = authorization["evidence"]
    head = authorization["final_attestation"]["candidate_head_sha"]
    verified = _commit(actions, root, evidence, head)
    if verified.signature_fingerprint != authorization["final_attestation"]["signature_fingerprint"]:
        raise fast_path.SecurityBlocker("candidate signer substitution")
    _tree(actions, root, evidence)
    for name, expected in zip(validation_trailers(evidence), (fast_path.digest_json(evidence), authorization["validation_receipt"]["receipt_digest"])):
        if actions._commit_trailer_digest(root, head, name) != expected:
            raise fast_path.SecurityBlocker("signed candidate does not bind integration validation")
    return head


def _successor(current, authorization, signers, root):
    head = authorization["final_attestation"]["candidate_head_sha"]
    validation = fast_path.verify_enrolled_draft_validation_evidence(
        authorization, repository_root=root
    )
    return execution._append_successor_evidence(
        current, {"operation": "HEAD_ADVANCED", "authorization_digest": authorization["authorization_digest"]},
        signers, resulting_head_sha=head, current_head_evidence=validation,
    )


def _push_exact(actions, root, evidence, head):
    """Git's advertised old OID plus server CAS enforces a non-force exact push."""
    origin = actions._run_attestation_git(root, ["remote", "get-url", "--push", "--all", "origin"], allow_failure=True)
    urls = origin.stdout.splitlines()
    if origin.returncode != 0 or len(urls) != 1 or fast_path._repository_from_remote(urls[0]) != evidence["repository"]:
        raise fast_path.SecurityBlocker("integration push destination differs from authorized repository")
    packed = actions._run_attestation_git(root, ["pack-objects", "--stdout", "--revs"], raw_output=True, input_data=(head + "\n").encode("ascii"))
    if packed.returncode != 0 or not isinstance(packed.stdout, bytes):
        raise fast_path.SecurityBlocker("exact integration object closure is unavailable")
    policy = authority._load_lifecycle_trust_policy(evidence["repository"])
    with publication._isolated_repository(policy, write=True) as (transport, credentials), tempfile.TemporaryDirectory(prefix="secpal-enrolled-draft-push-") as temporary:
        imported = publication._run_git(transport, ["index-pack", "--stdin"], input_bytes=packed.stdout)
        observed = publication._run_git(transport, ["cat-file", "commit", head])
        if imported.returncode != 0 or observed.returncode != 0 or fast_path._commit_topology(observed.stdout.decode("utf-8")) != (evidence["validated_tree_sha"], tuple(evidence["ordered_parent_shas"])):
            raise fast_path.SecurityBlocker("isolated integration object identity changed")
        hooks = Path(temporary)
        hook = hooks / "pre-push"
        ref = "refs/heads/" + evidence["head_ref"]
        # All inserted values were closed-normalized and check-ref-format was
        # authenticated before this boundary. JSON data is passed as argv,
        # never interpolated into shell source.
        python = bootstrap_source_admission._trusted_python()
        hook.write_text(f"#!{python} -I\nimport sys\nexpected = " + repr((head, ref, evidence["draft_head_sha"])) + "\nrows = [row.split() for row in sys.stdin]\nsys.exit(0 if len(rows) == 1 and len(rows[0]) == 4 and tuple(rows[0][1:]) == expected else 1)\n")
        hook.chmod(0o700)
        # The maintained transport has a fresh bare config and excludes global,
        # system and inherited Git configuration. An already expanded origin
        # URL is never reprocessed under candidate-controlled rewrite rules.
        destination = f'https://github.com/{evidence["repository"]}.git'
        result = publication._run_git(transport, ["-c", f"core.hooksPath={hooks}", "push", "--porcelain", destination, f"{head}:{ref}"], extra_environment=credentials)
    if result.returncode != 0:
        raise fast_path.SecurityBlocker("authorized push failed or is uncertain; reconcile exact read-back only")


def _require_exact_published(authorization, current):
    evidence = authorization["evidence"]
    head = authorization["final_attestation"]["candidate_head_sha"]
    require_initial_native_draft(current)
    if (
        current.lifecycle.repository != evidence["repository"]
        or current.lifecycle.delivery_issue != evidence["delivery_issue"]
        or current.lifecycle.initialization_evidence_digest != evidence["initialization_evidence_digest"]
        or current.lifecycle.head_sha != head or current.lifecycle.lifecycle_id != evidence["lifecycle_id"]
        or current.lifecycle.pull_request != evidence["pull_request"]
        or current.predecessor_publication_oid != evidence["current_publication_oid"]
        or current.lifecycle.tree_sha != evidence["validated_tree_sha"]
        or current.lifecycle.validation_receipt_digest != authorization["validation_receipt"]["receipt_digest"]
        or current.lifecycle.source_validation_evidence_digest != fast_path.digest_json(evidence)
        or current.lifecycle.adoption_source_evidence_digest != authorization["final_attestation"]["attestation_digest"]
    ):
        raise fast_path.SecurityBlocker("publication selected another integration head or lifecycle")
    transition = publication._verify_historical_lifecycle_transition(
        evidence["repository"], evidence["delivery_issue"], evidence["current_publication_oid"],
        expected_current_publication_oid=current.publication_oid,
    )
    if transition.event_id != "authorization:" + authorization["authorization_digest"] or transition.transition_kind != "HEAD_ADVANCED":
        raise fast_path.SecurityBlocker("publication is not the exact authorized HEAD_ADVANCED")


def integrate(actions, arguments, *, kind=KIND) -> int:
    """One push/publication attempt, or explicit exact read-back reconciliation."""
    if not arguments.apply:
        raise fast_path.SecurityBlocker("enrolled Draft operation requires --apply")
    _trusted_source(actions, arguments.repo)
    _, binding = _entry(actions, arguments.repo, kind)
    root = Path(arguments.repo_root).resolve(strict=True)
    actions._require_distinct_candidate_repository_root(root)
    authorization = normalize_authorization(actions._read_pre_enrollment_json(arguments.authorization, "integration authorization"))
    evidence = authorization["evidence"]
    if evidence["kind"] != kind:
        raise fast_path.SecurityBlocker("authorization belongs to another enrolled Draft operation")
    if (evidence["repository"], evidence["delivery_issue"], evidence["pull_request"]) != (arguments.repo, arguments.delivery_issue, arguments.pr):
        raise fast_path.SecurityBlocker("explicit integration delivery identity differs from authorization")
    # Initial dispatch consumes the currently registered validation policy.
    # Recovery has no branch-write authority: its protected claims authenticate
    # the exact historical receipt, even after validation requirements evolve.
    if not arguments.reconcile and (
        evidence["registry_digest"] != fast_path.digest_json(binding)
        or evidence["command_set_digest"] != fast_path.digest_json(binding["validation"])
    ):
        raise fast_path.SecurityBlocker("integration validation policy changed")
    head = _verify_candidate_package(actions, root, authorization)
    current = publication.verify_current_lifecycle_authority(arguments.repo, arguments.delivery_issue)
    signers = execution._production_signing_authorities(arguments.repo, authorization["signer_identity"])
    if arguments.reconcile:
        publication.verify_enrolled_draft_integration_claim(authorization)
        _live(actions, arguments.repo, arguments.delivery_issue, arguments.pr, head, evidence["current_main"]["sha"] if kind == KIND else actions._authenticate_protected_bridge_main(arguments.repo), evidence["head_ref"])
        execution._verify_live_github_commit_signature(arguments.repo, head)
        if current.lifecycle.head_sha == head:
            _require_exact_published(authorization, current)
            _live(actions, arguments.repo, arguments.delivery_issue, arguments.pr, head, evidence["current_main"]["sha"] if kind == KIND else actions._authenticate_protected_bridge_main(arguments.repo), evidence["head_ref"])
            return 0
        require_predecessor(current, evidence)
    else:
        require_fresh_source_authorization(evidence)
        require_predecessor(current, evidence)
        main = actions._authenticate_protected_bridge_main(arguments.repo)
        if (kind == KIND and main != evidence["current_main"]["sha"]) or _graph(actions, arguments.repo, arguments.delivery_issue) != evidence["work_graph_digest"]:
            raise fast_path.SecurityBlocker("protected main or work graph is stale")
        _live(actions, arguments.repo, arguments.delivery_issue, arguments.pr, evidence["draft_head_sha"], main, evidence["head_ref"])
        # This signed ancillary record in the EXISTING protected journal consumes
        # push authority even if the process crashes before dispatch. Observing
        # it later never authorizes a push, including on an unchanged branch.
        publication.claim_enrolled_draft_integration(authorization, signer_identity=signers.publication_identity, signer=signers.publication_signer)
        require_predecessor(publication.verify_current_lifecycle_authority(arguments.repo, arguments.delivery_issue), evidence)
        main = actions._authenticate_protected_bridge_main(arguments.repo)
        if kind == KIND and main != evidence["current_main"]["sha"]:
            raise fast_path.SecurityBlocker("protected main changed after push claim")
        _live(actions, arguments.repo, arguments.delivery_issue, arguments.pr, evidence["draft_head_sha"], main, evidence["head_ref"])
        if _graph(actions, arguments.repo, arguments.delivery_issue) != evidence["work_graph_digest"]:
            raise fast_path.SecurityBlocker("work graph changed after push claim; no retry")
        require_fresh_source_authorization(evidence)
        _push_exact(actions, root, evidence, head)
        _live(actions, arguments.repo, arguments.delivery_issue, arguments.pr, head, evidence["current_main"]["sha"] if kind == KIND else actions._authenticate_protected_bridge_main(arguments.repo), evidence["head_ref"])
        execution._verify_live_github_commit_signature(arguments.repo, head)
    # Both paths have authenticated predecessor CURRENT, the exact claimed
    # authorization and the already live signed candidate. No commit is created.
    successor = _successor(current, authorization, signers, root)
    _live(actions, arguments.repo, arguments.delivery_issue, arguments.pr, head, evidence["current_main"]["sha"] if kind == KIND else actions._authenticate_protected_bridge_main(arguments.repo), evidence["head_ref"])
    publication.advance_current_terminal(successor, signer_identity=signers.publication_identity, signer=signers.publication_signer)
    _require_exact_published(authorization, publication.verify_current_lifecycle_authority(arguments.repo, arguments.delivery_issue))
    _live(actions, arguments.repo, arguments.delivery_issue, arguments.pr, head, evidence["current_main"]["sha"] if kind == KIND else actions._authenticate_protected_bridge_main(arguments.repo), evidence["head_ref"])
    return 0


# A capability within the registered source family, not another lifecycle kind.
REACQUISITION_KIND = SOURCE_KIND + "_PUSH_REACQUISITION_AUTHORIZATION"
REACQUISITION_DOMAIN = "secpal.enrolled-draft-source-push-reacquisition/v1"
REACQUISITION_POLICY = {
    "schema_version": "1.0", "maximum_replacements": 1,
    "candidate_creation": False, "automatic_retry": False,
    "historical_validation": "EXACT_CURRENT_REGISTRY_AND_COMMAND_SET",
    "original_authorization": "EXPIRED", "branch_history": "COMPLETE_NO_REWRITE",
}
REACQUISITION_FIELDS = frozenset({
    "schema_version", "kind", "operation_id", "binding", "issued_at",
    "expires_at", "signer_identity", "signature", "authorization_digest",
})
REACQUISITION_CLAIM_BINDINGS = frozenset({
    "preparation_claim_digest", "original_push_claim_digest",
    "accepted_main_sha", "policy_digest", "work_graph_digest",
})
_BRANCH_HISTORY_QUERY = """query($owner:String!, $name:String!, $number:Int!) {
  repository(owner:$owner, name:$name) {
    nameWithOwner
    pullRequest(number:$number) {
      number state isDraft headRefName headRefOid
      timelineItems(first:100, itemTypes:[PULL_REQUEST_COMMIT,
        HEAD_REF_FORCE_PUSHED_EVENT,HEAD_REF_DELETED_EVENT,HEAD_REF_RESTORED_EVENT]) {
        nodes { __typename
          ... on PullRequestCommit { id commit { oid } }
          ... on HeadRefForcePushedEvent { id }
          ... on HeadRefDeletedEvent { id }
          ... on HeadRefRestoredEvent { id }
        }
        pageInfo { hasNextPage }
      }
    }
  }
}"""


def _original_reacquisition_binding(authorization):
    """Pure projection of identities independently authenticated by the package."""
    if authorization["evidence"]["kind"] != SOURCE_KIND:
        raise fast_path.SecurityBlocker("reacquisition requires the original source family")
    evidence = authorization["evidence"]
    attestation = authorization["final_attestation"]
    keys = ("repository", "delivery_issue", "pull_request", "lifecycle_id",
            "initialization_evidence_digest", "current_publication_oid",
            "current_publication_digest", "predecessor_authority_digest",
            "draft_head_sha", "validated_tree_sha", "ordered_parent_shas",
            "head_ref", "expected_signer", "registry_digest", "command_set_digest")
    return {
        **{key: copy.deepcopy(evidence[key]) for key in keys},
        "candidate_head_sha": attestation["candidate_head_sha"],
        "signature_fingerprint": attestation["signature_fingerprint"],
        "original_authorization_id": authorization["authorization_id"],
        "original_source_authorization_digest": authorization["authorization_digest"],
        "original_preparation_authorization_digest": authorization["preparation_authorization_digest"],
        "validation_receipt_digest": authorization["validation_receipt"]["receipt_digest"],
        "final_attestation_digest": attestation["attestation_digest"],
    }


def normalize_reacquisition_authorization(value, original):
    """Authenticate new explicit exact authority without reinterpreting validation."""
    item = draft._closed(value, REACQUISITION_FIELDS, "source push reacquisition authorization")
    if item["schema_version"] != "1.0" or item["kind"] != REACQUISITION_KIND:
        raise fast_path.SecurityBlocker("source push reacquisition kind/version is unsupported")
    draft._identity(item["operation_id"], "reacquisition operation")
    expected = _original_reacquisition_binding(original)
    binding = draft._closed(item["binding"], frozenset(expected) | REACQUISITION_CLAIM_BINDINGS, "reacquisition binding")
    if any(binding[key] != val for key, val in expected.items()):
        raise fast_path.SecurityBlocker("fresh source reauthorization substitutes the original candidate/package")
    for key in REACQUISITION_CLAIM_BINDINGS - {"accepted_main_sha"}:
        draft._digest(binding[key], key)
    draft._oid(binding["accepted_main_sha"], "accepted recovery authority")
    if binding["policy_digest"] != fast_path.digest_json(REACQUISITION_POLICY):
        raise fast_path.SecurityBlocker("source reacquisition policy identity changed")
    if (any(type(item[key]) is not int or item[key] <= 0 for key in ("issued_at", "expires_at"))
            or not 0 < item["expires_at"] - item["issued_at"] <= MAXIMUM_SOURCE_AUTHORIZATION_SECONDS):
        raise fast_path.SecurityBlocker("source reacquisition freshness bounds are invalid")
    signer = draft._identity(item["signer_identity"], "reacquisition signer")
    if signer != original["signer_identity"]:
        raise fast_path.SecurityBlocker("source reacquisition signer changed")
    signature = draft._signature(item["signature"], signer)
    if signature["format"] != "ssh":
        raise fast_path.SecurityBlocker("source reacquisition requires SSH")
    fields = {key: val for key, val in item.items() if key not in {"signature", "authorization_digest"}}
    if item["authorization_digest"] != fast_path.digest_json({**fields, "signature": signature}):
        raise fast_path.SecurityBlocker("source reacquisition authorization digest mismatch")
    policy = authority._load_lifecycle_trust_policy(expected["repository"])
    authority._verify_signature(fast_path.canonical_json_bytes(fields), signature, signer,
        REACQUISITION_DOMAIN, policy.transition_signer_identities,
        authority._policy_signature_verifier(policy))
    return copy.deepcopy(item)


def require_fresh_reacquisition_authorization(value):
    if not value["issued_at"] <= time.time() < value["expires_at"]:
        raise fast_path.SecurityBlocker("source reacquisition authorization is stale or not yet valid")


def require_reacquisition_claim_bindings(replacement, original, preparation, consumed):
    """Canonical claim owner calls this for both authenticated journal projections."""
    selected = normalize_reacquisition_authorization(replacement, original)
    binding = selected["binding"]
    old = preparation["authorization"]
    if (old["authorization_digest"] != original["preparation_authorization_digest"]
            or old["kind"] != authorization_kind(SOURCE_KIND, preparation=True)
            or any(old[key] != original[key] for key in ("authorization_id", "evidence", "validation_receipt", "signer_identity"))
            or consumed["authorization"] != original
            or consumed.get("reacquisition_authorization") is not None
            or binding["preparation_claim_digest"] != preparation["publication_digest"]
            or binding["original_push_claim_digest"] != consumed["publication_digest"]):
        raise publication.LifecyclePublicationError("source reacquisition original protected bindings changed")


def normalize_source_branch_history(raw):
    """Pure normalization of GitHub's bounded complete branch timeline."""
    try:
        if not isinstance(raw, dict) or raw.get("errors"):
            raise ValueError("incomplete response")
        repo = raw["data"]["repository"]
        pull = repo["pullRequest"]
        connection = pull["timelineItems"]
        nodes = connection["nodes"]
        if connection["pageInfo"]["hasNextPage"] is not False or not isinstance(nodes, list) or len(nodes) > 100:
            raise ValueError("incomplete history")
        events = []
        seen = set()
        for node in nodes:
            identity = draft._identity(node["id"], "branch history event")
            if identity in seen:
                raise ValueError("duplicate history event")
            seen.add(identity)
            kind = node["__typename"]
            if kind not in {"PullRequestCommit", "HeadRefForcePushedEvent", "HeadRefDeletedEvent", "HeadRefRestoredEvent"}:
                raise ValueError("unknown history event")
            head = draft._oid(node["commit"]["oid"], "historical commit") if kind == "PullRequestCommit" else None
            events.append((kind, head))
        return {"repository": draft._repository(repo["nameWithOwner"]),
                "pull_request": draft._positive(pull["number"], "historical PR"),
                "state": pull["state"], "draft": pull["isDraft"],
                "head_ref": draft._identity(pull["headRefName"], "historical branch"),
                "head_sha": draft._oid(pull["headRefOid"], "historical head"),
                "events": tuple(events)}
    except (KeyError, TypeError, ValueError) as exc:
        raise fast_path.SecurityBlocker("source branch history is unavailable, incomplete or malformed") from exc


def admit_unpublished_source_history(observed, original):
    """No rewritten branch can prove this candidate never persisted."""
    evidence = original["evidence"]
    head = original["final_attestation"]["candidate_head_sha"]
    if (any(observed[key] != evidence[key] for key in ("repository", "pull_request", "head_ref"))
            or observed["state"] != "OPEN" or observed["draft"] is not True
            or observed["head_sha"] != evidence["draft_head_sha"]
            or ("PullRequestCommit", evidence["draft_head_sha"]) not in observed["events"]
            or any(kind != "PullRequestCommit" or oid == head for kind, oid in observed["events"])):
        raise fast_path.SecurityBlocker("candidate was published or source branch history is ambiguous")


def _require_unpublished_source_history(original):
    evidence = original["evidence"]
    owner, name = evidence["repository"].split("/")
    result = publication._run_gh(["api", "--hostname", "github.com", "graphql",
        "-f", "query=" + _BRANCH_HISTORY_QUERY, "-f", "owner=" + owner,
        "-f", "name=" + name, "-F", "number=" + str(evidence["pull_request"])])
    if result.returncode != 0:
        raise fast_path.SecurityBlocker("source branch history observation is unavailable")
    admit_unpublished_source_history(normalize_source_branch_history(draft.loads_closed_json(result.stdout)), original)


def admit_exact_source_branch_ref(raw, *, ref, head):
    """Pure admission of the independent Git ref, not a cached PR pointer."""
    if (not isinstance(raw, dict) or raw.get("ref") != ref
            or not isinstance(raw.get("object"), dict)
            or raw["object"].get("type") != "commit"
            or raw["object"].get("sha") != head):
        raise fast_path.SecurityBlocker("exact source branch ref is missing or changed")


def _require_exact_source_branch_ref(original, head):
    evidence = original["evidence"]
    draft._oid(head, "exact source branch head")
    result = publication._run_gh(["api", "--hostname", "github.com",
        f'repos/{evidence["repository"]}/git/ref/heads/{quote(evidence["head_ref"], safe="")}'])
    if result.returncode != 0:
        raise fast_path.SecurityBlocker("exact source branch ref observation is unavailable")
    admit_exact_source_branch_ref(draft.loads_closed_json(result.stdout),
        ref="refs/heads/" + evidence["head_ref"], head=head)


def _qualify_source_reacquisition(actions, arguments, *, unused, owned=None):
    accepted_main = _trusted_source(actions, arguments.repo)
    _, binding = _entry(actions, arguments.repo, SOURCE_KIND)
    root = Path(arguments.repo_root).resolve(strict=True)
    actions._require_distinct_candidate_repository_root(root)
    original = normalize_authorization(actions._read_pre_enrollment_json(arguments.authorization, "original source authorization"))
    evidence = original["evidence"]
    if (evidence["repository"], evidence["delivery_issue"], evidence["pull_request"]) != (arguments.repo, arguments.delivery_issue, arguments.pr):
        raise fast_path.SecurityBlocker("source reacquisition delivery identity changed")
    _original_reacquisition_binding(original)
    head = _verify_candidate_package(actions, root, original)
    # Read-back of a live candidate has no mutation authority and keeps the
    # existing historical reconciliation policy, including after policy drift.
    live = actions.LiveGitHub().observe_ready_integration_authority(arguments.repo, arguments.pr)
    _require_exact_source_branch_ref(original, live.get("head_sha"))
    main = actions._authenticate_protected_bridge_main(arguments.repo)
    if live.get("head_sha") == head:
        _live(actions, arguments.repo, arguments.delivery_issue, arguments.pr, head, main, evidence["head_ref"])
        publication.verify_enrolled_draft_integration_claim(original)
        return root, original, None
    current = publication.verify_current_lifecycle_authority(arguments.repo, arguments.delivery_issue)
    require_predecessor(current, evidence)
    _live(actions, arguments.repo, arguments.delivery_issue, arguments.pr, evidence["draft_head_sha"], main, evidence["head_ref"])
    if (evidence["registry_digest"] != fast_path.digest_json(binding)
            or evidence["command_set_digest"] != fast_path.digest_json(binding["validation"])):
        raise fast_path.SecurityBlocker("historical source validation is incompatible with current pre-push policy")
    if time.time() < evidence["user_authorization"]["expires_at"]:
        raise fast_path.SecurityBlocker("original source authorization has not expired")
    preparation, consumed = publication.verify_enrolled_draft_source_claims(original, require_unused_reacquisition=unused, required_reacquisition=owned)
    _require_unpublished_source_history(original)
    graph = _graph(actions, arguments.repo, arguments.delivery_issue)
    exact = {**_original_reacquisition_binding(original),
        "preparation_claim_digest": preparation["publication_digest"],
        "original_push_claim_digest": consumed["publication_digest"],
        "accepted_main_sha": accepted_main,
        "policy_digest": fast_path.digest_json(REACQUISITION_POLICY), "work_graph_digest": graph}
    return root, original, exact


def qualify_source_reacquisition(actions, arguments):
    """Read-only retained-object qualification; never signs, claims or pushes."""
    _, _, binding = _qualify_source_reacquisition(actions, arguments, unused=True)
    actions._write_fast_report(arguments.output, {"status": "RECONCILE_ONLY" if binding is None else "ELIGIBLE",
        "binding": binding, "binding_digest": None if binding is None else fast_path.digest_json(binding)})
    return 0


def authorize_source_reacquisition(actions, arguments):
    """Sign one NEW user-approved exact binding; cannot create source evidence."""
    if not arguments.apply:
        raise fast_path.SecurityBlocker("source reauthorization requires --apply")
    _, original, binding = _qualify_source_reacquisition(actions, arguments, unused=True)
    if binding is None:
        raise fast_path.SecurityBlocker("candidate is already live; use existing exact reconciliation")
    if arguments.expected_binding_digest != fast_path.digest_json(binding):
        raise fast_path.SecurityBlocker("explicit user reauthorization differs from independently derived exact binding")
    signers = execution._production_signing_authorities(arguments.repo, original["signer_identity"])
    fields = {"schema_version": "1.0", "kind": REACQUISITION_KIND,
        "operation_id": arguments.operation_id, "binding": binding,
        "issued_at": int(time.time()), "expires_at": arguments.expires_at,
        "signer_identity": original["signer_identity"]}
    signed = {**fields, "signature": dict(signers.transition_signer(fast_path.canonical_json_bytes(fields), REACQUISITION_DOMAIN))}
    selected = normalize_reacquisition_authorization({**signed, "authorization_digest": fast_path.digest_json(signed)}, original)
    require_fresh_reacquisition_authorization(selected)
    actions._write_fast_report(arguments.output, selected)
    return 0


def _reconcile_source_reacquisition(actions, arguments):
    reconciled = copy.copy(arguments)
    reconciled.reconcile = True
    original = normalize_authorization(actions._read_pre_enrollment_json(arguments.authorization, "original source authorization"))
    head = original["final_attestation"]["candidate_head_sha"]
    _require_exact_source_branch_ref(original, head)
    result = integrate(actions, reconciled, kind=SOURCE_KIND)
    _require_exact_source_branch_ref(original, head)
    return result


def reacquire_source_push(actions, arguments):
    """One ephemeral CAS winner, one existing exact push, existing HEAD_ADVANCED."""
    if not arguments.apply:
        raise fast_path.SecurityBlocker("source push reacquisition requires --apply")
    root, original, binding = _qualify_source_reacquisition(actions, arguments, unused=True)
    if binding is None:
        return _reconcile_source_reacquisition(actions, arguments)
    selected = normalize_reacquisition_authorization(actions._read_pre_enrollment_json(arguments.reauthorization, "fresh exact reauthorization"), original)
    if selected["binding"] != binding:
        raise fast_path.SecurityBlocker("source reacquisition authority is stale or substituted")
    require_fresh_reacquisition_authorization(selected)
    signers = execution._production_signing_authorities(arguments.repo, original["signer_identity"])
    publication.claim_enrolled_draft_integration(original, signer_identity=signers.publication_identity,
        signer=signers.publication_signer, reacquisition_authorization=selected)
    # Claim consumption survives failure of any post-claim observation or
    # freshness check. Another invocation/ID/clone cannot receive ownership.
    _, final_original, final_binding = _qualify_source_reacquisition(actions, arguments, unused=False, owned=selected)
    if final_original != original:
        raise fast_path.SecurityBlocker("original source package changed after replacement claim")
    if final_binding is None:
        return _reconcile_source_reacquisition(actions, arguments)
    if final_binding != binding:
        raise fast_path.SecurityBlocker("source reacquisition eligibility changed after claim; no retry")
    require_fresh_reacquisition_authorization(selected)
    try:
        _push_exact(actions, root, original["evidence"], binding["candidate_head_sha"])
    except (fast_path.SecurityBlocker, publication.LifecyclePublicationError, OSError, subprocess.TimeoutExpired):
        # Uncertain persistence consumes the opportunity forever. Exactly-live
        # authoritative readback may only use the existing branch-read-only path.
        live = actions.LiveGitHub().observe_ready_integration_authority(arguments.repo, arguments.pr)
        if live.get("head_sha") != binding["candidate_head_sha"]:
            raise fast_path.SecurityBlocker("replacement persistence unproven; terminal stop, no further replacement")
    return _reconcile_source_reacquisition(actions, arguments)
