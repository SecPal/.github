# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""One exact enrolled initial-Draft integration, using maintained authorities.

Preparation creates and authorizes a single immutable signed candidate after
Complete Validation. Execution cannot create a commit: it consumes that exact
authorization once in the protected publication journal, pushes only its bound
PR branch, and publishes HEAD_ADVANCED. Explicit reconciliation never pushes.
"""

from __future__ import annotations

import copy
from pathlib import Path
import tempfile
from typing import Any, Mapping

from . import fast_path, lifecycle_authority as authority
from . import lifecycle_execution as execution, lifecycle_publication as publication
from . import pre_enrollment_integration as draft
from . import bootstrap_source_admission

KIND = "ENROLLED_DRAFT_CURRENT_MAIN_INTEGRATION"
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
    item = draft._closed(value, EVIDENCE_FIELDS, "enrolled Draft integration evidence")
    if item["kind"] != KIND or item["schema_version"] != "1.0":
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
    preparation = allow_preparation and isinstance(value, dict) and value.get("kind") == PREPARATION_AUTHORIZATION_KIND
    item = draft._closed(value, PREPARATION_AUTHORIZATION_FIELDS if preparation else AUTHORIZATION_FIELDS, "enrolled Draft authorization")
    expected_kind = PREPARATION_AUTHORIZATION_KIND if preparation else AUTHORIZATION_KIND
    domain = PREPARATION_AUTHORIZATION_DOMAIN if preparation else AUTHORIZATION_DOMAIN
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


def _entry(actions, repository):
    entry = actions.select_repository(actions.load_registry(), repository)
    binding = actions._fast_registry_binding(entry)
    if fast_path.canonical_json_bytes(binding.get("enrolled_draft_integration_policy")) != fast_path.canonical_json_bytes(POLICY):
        raise fast_path.SecurityBlocker("repository has no closed enrolled Draft integration policy")
    return entry, binding


def _graph(actions, repository, issue):
    result = actions._run_pre_enrollment_work_graph(actions.REPOSITORY_ROOT, [
        str(actions.REPOSITORY_ROOT / "scripts/secpal-work-graph.py"),
        "validate-issue", f"{repository}#{issue}",
    ])
    value = draft.loads_closed_json(result.stdout)
    if result.returncode != 0:
        raise fast_path.SecurityBlocker("work graph does not authorize enrolled Draft integration")
    digest = fast_path.digest_json(value)
    actions._verify_pre_enrollment_work_graph_result(value, repository=repository, delivery_issue=issue, expected_digest=digest)
    return digest


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
    result = actions._run_pre_enrollment_work_graph(actions.REPOSITORY_ROOT, [
        str(actions.REPOSITORY_ROOT / "scripts/secpal-work-graph.py"),
        "validate-issue", f"{repository}#{issue}",
    ])
    graph = draft.loads_closed_json(result.stdout)
    claims = graph.get("issue", {}).get("claims")
    if result.returncode != 0 or not isinstance(claims, list) or len(claims) != 1:
        raise fast_path.SecurityBlocker("delivery does not have exactly one primary PR")
    actions._verify_pre_enrollment_work_graph_result(graph, repository=repository, delivery_issue=issue, expected_digest=fast_path.digest_json(graph))
    claim = claims[0]
    if claim.get("pull_request") != f"{repository}#{pr}":
        raise fast_path.SecurityBlocker("delivery primary PR differs from CURRENT")
    checked = actions._run_attestation_git(actions.REPOSITORY_ROOT, ["check-ref-format", f'refs/heads/{live["head_ref"]}'], allow_failure=True)
    if checked.returncode != 0:
        raise fast_path.SecurityBlocker("integration PR branch is unsafe")
    return live["head_ref"]


def _tree(actions, root, evidence):
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


def prepare(actions, arguments) -> int:
    """Validate, create one signed candidate, then sign its exact authorization."""
    if not arguments.apply:
        raise fast_path.SecurityBlocker("candidate preparation requires --apply")
    _trusted_source(actions, arguments.repo)
    entry, binding = _entry(actions, arguments.repo)
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
    necessary = actions._run_attestation_git(root, ["merge-base", "--is-ancestor", main, head], allow_failure=True)
    if necessary.returncode != 1:
        raise fast_path.SecurityBlocker("current-main reconciliation is unnecessary or ancestry unavailable")
    tree = actions._staged_tree(root, status)
    policy = authority._load_lifecycle_trust_policy(arguments.repo)
    signer_id = execution._single_role_identity(policy.transition_signer_identities, "integration signer")
    signers = execution._production_signing_authorities(arguments.repo, signer_id)
    evidence = normalize_evidence({
        "schema_version": "1.0", "kind": KIND, **bound,
        "current_main": {"ref": binding["default_branch"], "sha": main},
        "ordered_parent_shas": [head, main], "validated_tree_sha": tree,
        "tree_evidence": fast_path.derive_ready_integration_tree_evidence(root, [head, main], tree, schema_version="1.0", kind=KIND, run_git=actions._run_attestation_git),
        "head_ref": head_ref, "work_graph_digest": graph,
        "registry_digest": fast_path.digest_json(binding),
        "command_set_digest": fast_path.digest_json(binding["validation"]),
        "expected_signer": signer_id,
        "manual_gate_evidence": fast_path.validate_manual_gate_evidence(
            draft.loads_closed_json(Path(arguments.manual_gate_evidence).read_bytes()),
            binding["manual_gates"],
        ),
    })
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
    if actions._authenticate_protected_bridge_main(arguments.repo) != main or _graph(actions, arguments.repo, arguments.delivery_issue) != graph:
        raise fast_path.SecurityBlocker("main or work graph changed during validation")
    _live(actions, arguments.repo, arguments.delivery_issue, arguments.pr, head, main, head_ref)
    receipt = fast_path.create_enrolled_draft_validation_receipt(evidence)
    preparation_fields = {
        "schema_version": "1.0", "kind": PREPARATION_AUTHORIZATION_KIND,
        "authorization_id": arguments.authorization_id, "evidence": evidence,
        "validation_receipt": receipt, "signer_identity": signer_id,
    }
    preparation_signed = {**preparation_fields, "signature": dict(signers.transition_signer(fast_path.canonical_json_bytes(preparation_fields), PREPARATION_AUTHORIZATION_DOMAIN))}
    preparation = normalize_authorization({**preparation_signed, "authorization_digest": fast_path.digest_json(preparation_signed)}, allow_preparation=True)
    actions._write_fast_report(str(directory / "preparation.json"), preparation)
    # The predecessor-scoped protected reservation is acquired before the sole
    # commit-tree call. Other directories, IDs, processes or clones cannot mint
    # a second candidate. A lost reservation response never grants ownership.
    publication.claim_enrolled_draft_integration(preparation, signer_identity=signers.publication_identity, signer=signers.publication_signer)
    trailers = dict(zip(TRAILERS, (fast_path.digest_json(evidence), receipt["receipt_digest"])))
    message = "Integrate protected main into enrolled Draft delivery\n\n" + "".join(f"{key}: {value}\n" for key, value in trailers.items())
    created = actions._create_signed_pre_enrollment_commit(root, ["commit-tree", "-S", tree, "-p", head, "-p", main], message)
    candidate = created.stdout.strip()
    if created.returncode != 0:
        raise fast_path.SecurityBlocker("signed enrolled Draft candidate creation failed; no retry")
    verified = _commit(actions, root, evidence, candidate)
    attestation = fast_path.create_enrolled_draft_final_attestation(evidence, receipt, candidate_head_sha=candidate, signature_fingerprint=verified.signature_fingerprint)
    fields = {
        "schema_version": "1.0", "kind": AUTHORIZATION_KIND,
        "authorization_id": arguments.authorization_id, "evidence": evidence,
        "validation_receipt": receipt, "final_attestation": attestation,
        "preparation_authorization_digest": preparation["authorization_digest"],
        "signer_identity": signer_id,
    }
    signed = {**fields, "signature": dict(signers.transition_signer(fast_path.canonical_json_bytes(fields), AUTHORIZATION_DOMAIN))}
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
    for name, expected in zip(TRAILERS, (fast_path.digest_json(evidence), authorization["validation_receipt"]["receipt_digest"])):
        if actions._commit_trailer_digest(root, head, name) != expected:
            raise fast_path.SecurityBlocker("signed candidate does not bind integration validation")
    return head


def _successor(current, authorization, signers, root):
    evidence = authorization["evidence"]
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
        current.lifecycle.head_sha != head or current.lifecycle.lifecycle_id != evidence["lifecycle_id"]
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


def integrate(actions, arguments) -> int:
    """One push/publication attempt, or explicit exact read-back reconciliation."""
    if not arguments.apply:
        raise fast_path.SecurityBlocker("enrolled Draft integration requires --apply")
    _trusted_source(actions, arguments.repo)
    _, binding = _entry(actions, arguments.repo)
    root = Path(arguments.repo_root).resolve(strict=True)
    actions._require_distinct_candidate_repository_root(root)
    authorization = normalize_authorization(draft.loads_closed_json(Path(arguments.authorization).read_bytes()))
    evidence = authorization["evidence"]
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
        _live(actions, arguments.repo, arguments.delivery_issue, arguments.pr, head, actions._authenticate_protected_bridge_main(arguments.repo), evidence["head_ref"])
        execution._verify_live_github_commit_signature(arguments.repo, head)
        if current.lifecycle.head_sha == head:
            _require_exact_published(authorization, current)
            return 0
        require_predecessor(current, evidence)
    else:
        require_predecessor(current, evidence)
        if actions._authenticate_protected_bridge_main(arguments.repo) != evidence["current_main"]["sha"] or _graph(actions, arguments.repo, arguments.delivery_issue) != evidence["work_graph_digest"]:
            raise fast_path.SecurityBlocker("protected main or work graph is stale")
        _live(actions, arguments.repo, arguments.delivery_issue, arguments.pr, evidence["draft_head_sha"], evidence["current_main"]["sha"], evidence["head_ref"])
        # This signed ancillary record in the EXISTING protected journal consumes
        # push authority even if the process crashes before dispatch. Observing
        # it later never authorizes a push, including on an unchanged branch.
        publication.claim_enrolled_draft_integration(authorization, signer_identity=signers.publication_identity, signer=signers.publication_signer)
        require_predecessor(publication.verify_current_lifecycle_authority(arguments.repo, arguments.delivery_issue), evidence)
        _live(actions, arguments.repo, arguments.delivery_issue, arguments.pr, evidence["draft_head_sha"], evidence["current_main"]["sha"], evidence["head_ref"])
        _push_exact(actions, root, evidence, head)
        _live(actions, arguments.repo, arguments.delivery_issue, arguments.pr, head, evidence["current_main"]["sha"], evidence["head_ref"])
        execution._verify_live_github_commit_signature(arguments.repo, head)
    # Both paths have authenticated predecessor CURRENT, the exact claimed
    # authorization and the already live signed candidate. No commit is created.
    successor = _successor(current, authorization, signers, root)
    publication.advance_current_terminal(successor, signer_identity=signers.publication_identity, signer=signers.publication_signer)
    _require_exact_published(authorization, publication.verify_current_lifecycle_authority(arguments.repo, arguments.delivery_issue))
    return 0
