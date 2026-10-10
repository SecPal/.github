# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Hermetic admission cases for one persisted, unacknowledged fallback."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import unittest
from pathlib import Path

# Ready integration supplies the shared Actions fixture. The historical source
# still exercises the same consumer/CAS cases before that prerequisite arrives.
if Path(__file__).with_name("secpal_actions_fixture.py").is_file():
    from tests.secpal_actions_fixture import load_actions
    load_actions()

from scripts.secpal_pr_review import provider_fallback


HEAD = "b" * 40
OLD = "a" * 40
READY = "2026-09-30T12:32:06Z"
FALLBACK = "2026-09-30T17:27:44Z"
NOW = datetime(2026, 9, 30, 18, 1, tzinfo=timezone.utc)


def case() -> dict:
    value = {
        "repository": "SecPal/.github",
        "delivery_issue": 1031,
        "pull_request": 1035,
        "head_sha": HEAD,
        "pr_state": "OPEN",
        "is_draft": False,
        "lifecycle": {
            "repository": "SecPal/.github", "delivery_issue": 1031,
            "pull_request": 1035, "head_sha": HEAD,
            "lifecycle_id": "lifecycle:" + "c" * 64,
            "authority_digest": "d" * 64,
            "publication_oid": "e" * 40,
            "authority_chain": [
                {"transition_kind": "DRAFT_TO_READY", "head_sha": OLD},
                {"transition_kind": "REMEDIATION_COMPLETED", "head_sha": HEAD},
                {"transition_kind": "ADDITIONAL_REVIEW_AUTHORIZATION_CONSUMED",
                 "head_sha": HEAD},
            ],
            "state": {
                "ready": True, "ready_transition_count": 1,
                "unrestricted_review_count": 1,
                "remediation_cycle_count": 2,
                "cycle_3_absent": True,
                "exceptional_recovery_count": 0,
                "exceptional_continuation_count": 0,
            },
        },
        "actor": "aroviqen",
        "timeline": [
            {"event": "committed", "sha": OLD},
            {"event": "ready_for_review", "id": 32164767721,
             "created_at": READY},
            {"event": "committed", "sha": HEAD},
            {"event": "commented", "id": 5916314995,
             "created_at": FALLBACK},
        ],
        "comments": [
            {"id": "IC_F1", "databaseId": 5916314995,
             "body": "@codex security review", "createdAt": FALLBACK,
             "author": {"login": "aroviqen"},
             "reactions": {"nodes": [], "pageInfo": {"hasNextPage": False}}},
            {"id": "IC_SUMMARY", "databaseId": 5911365989,
             "body": (
                 "<!-- codex-pull-request-review-summary -->\n"
                 '<!-- codex-security-review:v1 {"headSha":"' + OLD + '",'
                 '"status":"completed","repository":"SecPal/.github",'
                 '"pullRequestNumber":1035} -->\n'
                 "| **Code Review** | ✅ **Completed** | `bbbbbbb` | Manual request |\n"
                 "| **Security Review** | ✅ **Completed** | `aaaaaaa` | Manual request |"
             ),
             "createdAt": READY,
             "author": {"login": "chatgpt-codex-connector", "id": "BOT_kgDOC98s_g", "databaseId": 199175422},
             "reactions": {"nodes": [], "pageInfo": {"hasNextPage": False}}},
            {"id": "IC_CODE", "databaseId": 5916340367,
             "body": "Codex Review: Didn't find any major issues.\n\n"
                     "**Reviewed commit:** `bbbbbbbbbb`",
             "createdAt": "2026-09-30T17:29:22Z",
             "author": {"login": "chatgpt-codex-connector", "id": "BOT_kgDOC98s_g", "databaseId": 199175422},
             "reactions": {"nodes": [], "pageInfo": {"hasNextPage": False}}},
        ],
        "reviews": [],
        "threads": [],
    }

    from scripts.secpal_pr_review import fast_path
    value["actor"] = {"login": "aroviqen", "node_id": "U_actor", "database_id": 42}
    value["head_publication"] = {"head": HEAD, "created_at": "2026-09-30T16:27:00Z"}
    lifecycle = value["lifecycle"]
    lifecycle["publication_digest"] = "f" * 64
    chain = lifecycle.pop("authority_chain")
    for index, snapshot in enumerate(chain):
        snapshot.update(pull_request=1035, authority_digest=str(index + 1) * 64)
    lifecycle["bundle"] = {
        "authority_chain": chain,
        "transition_authorizations": [
            {"transition_kind": x["transition_kind"], "resulting_head_sha": x["head_sha"], "pull_request": 1035}
            for x in chain
        ],
    }
    for comment in value["comments"]:
        actor = comment["author"]
        if actor["login"] == "aroviqen":
            actor.update(id="U_actor", databaseId=42)
        else:
            actor.update(id=fast_path.CODEX_REVIEW_PROVIDER["node_id"], databaseId=fast_path.CODEX_REVIEW_PROVIDER["database_id"])
        comment["updatedAt"] = comment["createdAt"]
    status = '✅ **Completed** <relative-time datetime="2026-09-30T17:29:22.000Z">2026-09-30T17:29:22.000Z</relative-time>'
    value["comments"][1]["body"] = value["comments"][1]["body"].replace("✅ **Completed**", status)
    return value


class ReplacementAdmissionTests(unittest.TestCase):
    def test_target_shaped_security_fallback_is_eligible(self):
        result = provider_fallback.classify(case(), "SECURITY", NOW)
        self.assertEqual(result.dispatch_key.original_fallback_comment_database_id, 5916314995)
        self.assertEqual(provider_fallback.TRIGGERS[result.dispatch_key.review_type], "@codex security review")
        self.assertEqual(result.dispatch_key.review_type, "SECURITY")

    def test_identity_and_authority_substitutions_fail_closed(self):
        changes = [
            lambda x: x.update(repository="Other/repo"),
            lambda x: x.update(pull_request=1036),
            lambda x: x.update(head_sha=OLD),
            lambda x: x.update(pr_state="CLOSED"),
            lambda x: x.update(is_draft=True),
            lambda x: x["lifecycle"]["state"].update(ready=False),
            lambda x: x["lifecycle"]["state"].update(unrestricted_review_count=0),
            lambda x: x["lifecycle"]["bundle"]["authority_chain"].pop(),
            lambda x: x["lifecycle"]["bundle"]["authority_chain"][-1].update(head_sha=OLD),
            lambda x: x["comments"][0]["author"].update(id="U_attacker", databaseId=43),
            lambda x: x["comments"][0].update(body="@codex review"),
            lambda x: x["comments"].pop(0),
            lambda x: x["timeline"].pop(3),
            lambda x: x["timeline"].append({"event": "committed", "sha": OLD}),
        ]
        for change in changes:
            with self.subTest(change=changes.index(change)):
                value = case()
                change(value)
                with self.assertRaises(provider_fallback.ReplacementBlocked):
                    provider_fallback.classify(value, "SECURITY", NOW)

    def test_acknowledgement_terminal_and_replay_fail_closed(self):
        variants = []
        reaction = case()
        reaction["comments"][0]["reactions"]["nodes"].append(
            {"id": "R1", "user": {"login": "chatgpt-codex-connector", "id": "BOT_kgDOC98s_g", "databaseId": 199175422}}
        )
        variants.append(reaction)
        processing = case()
        processing["comments"].append({
            "id": "IC_STATUS", "databaseId": 5916400001,
            "body": "Security review is running", "createdAt": FALLBACK,
            "author": {"login": "chatgpt-codex-connector", "id": "BOT_kgDOC98s_g", "databaseId": 199175422},
            "reactions": {"nodes": [], "pageInfo": {"hasNextPage": False}},
        })
        variants.append(processing)
        review = case()
        review["reviews"].append({
            "id": "PRR_SECURITY", "body": "### 🛡️ Codex Security Review",
            "commit": {"oid": HEAD},
            "author": {"login": "chatgpt-codex-connector", "id": "BOT_kgDOC98s_g", "databaseId": 199175422},
        })
        variants.append(review)
        terminal = case()
        terminal["comments"].append({
            "id": "IC_SECURITY", "databaseId": 5916400002,
            "body": "### 🛡️ Codex Security Review\n"
                    "No security issues were found in this pull request.\n"
                    "**Reviewed commit:** `bbbbbbbbbb`",
            "createdAt": FALLBACK,
            "author": {"login": "chatgpt-codex-connector", "id": "BOT_kgDOC98s_g", "databaseId": 199175422},
            "reactions": {"nodes": [], "pageInfo": {"hasNextPage": False}},
        })
        variants.append(terminal)
        replacement = case()
        replacement["comments"].append({
            **copy.deepcopy(replacement["comments"][0]),
            "id": "IC_F2", "databaseId": 5916400003,
            "createdAt": "2026-09-30T18:00:00Z",
        })
        replacement["timeline"].append({
            "event": "commented", "id": 5916400003,
            "created_at": "2026-09-30T18:00:00Z",
        })
        variants.append(replacement)
        for value in variants:
            with self.subTest(variant=variants.index(value)):
                with self.assertRaises(provider_fallback.ReplacementBlocked):
                    provider_fallback.classify(value, "SECURITY", NOW)

    def test_observation_window_and_review_type_are_bound(self):
        with self.assertRaises(provider_fallback.ReplacementBlocked):
            provider_fallback.classify(case(), "SECURITY", datetime(
                2026, 9, 30, 17, 57, tzinfo=timezone.utc))
        with self.assertRaises(provider_fallback.ReplacementBlocked):
            provider_fallback.classify(case(), "CODE", NOW)

    def test_normal_primary_and_first_fallback_completion_do_not_replace(self):
        primary = case()
        primary["comments"].pop(0)
        primary["timeline"].pop()
        primary["comments"].append({
            "id": "IC_SECURITY", "databaseId": 5916400002,
            "body": "### 🛡️ Codex Security Review\n"
                    "No security issues were found in this pull request.\n"
                    "**Reviewed commit:** `bbbbbbbbbb`",
            "createdAt": "2026-09-30T13:00:00Z",
            "author": {"login": "chatgpt-codex-connector", "id": "BOT_kgDOC98s_g", "databaseId": 199175422},
            "reactions": {"nodes": [], "pageInfo": {"hasNextPage": False}},
        })
        with self.assertRaises(provider_fallback.ReplacementBlocked):
            provider_fallback.classify(primary, "SECURITY", NOW)

        completed_fallback = case()
        completed_fallback["comments"].append(primary["comments"][-1])
        with self.assertRaises(provider_fallback.ReplacementBlocked):
            provider_fallback.classify(completed_fallback, "SECURITY", NOW)

    def test_two_prior_replacements_and_changed_assessment_fail_closed(self):
        replacement = case()
        for number in (5916400003, 5916400004):
            replacement["comments"].append({
                **copy.deepcopy(replacement["comments"][0]),
                "id": f"IC_{number}", "databaseId": number,
                "createdAt": "2026-09-30T18:00:00Z",
            })
            replacement["timeline"].append({
                "event": "commented", "id": number,
                "created_at": "2026-09-30T18:00:00Z",
            })
        with self.assertRaises(provider_fallback.ReplacementBlocked):
            provider_fallback.classify(replacement, "SECURITY", NOW)

        before = provider_fallback.classify(case(), "SECURITY", NOW)
        changed = case()
        changed["lifecycle"]["lifecycle_id"] = "lifecycle:" + "d" * 64
        with self.assertRaises(provider_fallback.ReplacementBlocked):
            provider_fallback._persisted_replacement(before.dispatch_key, changed, None)

    def test_one_write_and_ambiguous_result_reconciliation(self):
        before = case()
        after = case()
        after["comments"].append({
            **copy.deepcopy(before["comments"][0]),
            "id": "IC_F2", "databaseId": 5916400003,
            "createdAt": "2026-09-30T18:00:00Z",
        })
        after["timeline"].append({
            "event": "commented", "id": 5916400003,
            "created_at": "2026-09-30T18:00:00Z",
        })
        after["comments"][-1]["updatedAt"] = after["comments"][-1]["createdAt"]
        eligible = provider_fallback.classify(before, "SECURITY", NOW)
        result = provider_fallback._persisted_replacement(eligible.dispatch_key, after, None)
        self.assertEqual(result.replacement_count, 1)
        self.assertEqual(result.replacement_comment_database_id, 5916400003)
        self.assertEqual(before["lifecycle"]["state"]["unrestricted_review_count"], 1)
        self.assertEqual(len([x for x in before["lifecycle"]["bundle"]["authority_chain"]
                             if x["transition_kind"] == "ADDITIONAL_REVIEW_AUTHORIZATION_CONSUMED"]), 1)
        result = provider_fallback._persisted_replacement(eligible.dispatch_key, before, None)
        self.assertEqual(result.replacement_count, 0)
        duplicate = copy.deepcopy(after)
        duplicate["comments"].append(copy.deepcopy(after["comments"][-1]))
        with self.assertRaises(provider_fallback.ReplacementBlocked):
            provider_fallback._persisted_replacement(eligible.dispatch_key, duplicate, None)

    def test_late_original_ack_prevents_write(self):
        later = case()
        later["comments"][0]["reactions"]["nodes"].append(
            {"id": "R1", "user": {"login": "chatgpt-codex-connector", "id": "BOT_kgDOC98s_g", "databaseId": 199175422}}
        )
        with self.assertRaises(provider_fallback.ProviderAcknowledged):
            provider_fallback.classify(later, "SECURITY", NOW)


class ReviewedFindingRegressions(unittest.TestCase):
    def test_later_assessment_does_not_inherit_ready_elapsed_time(self):
        observed = case()
        observed["head_publication"] = {
            "head": HEAD, "created_at": "2026-09-30T17:27:00Z",
        }
        with self.assertRaises(provider_fallback.ReplacementBlocked):
            provider_fallback.classify(observed, "SECURITY", NOW)

    def test_reused_login_cannot_replace_stable_actor(self):
        observed = case()
        observed["actor"] = {"login": "aroviqen", "node_id": "U_EXPECTED", "database_id": 42}
        observed["comments"][0]["author"].update(id="U_OTHER", databaseId=43)
        with self.assertRaisesRegex(provider_fallback.ReplacementBlocked, "actor"):
            provider_fallback.classify(observed, "SECURITY", NOW)

    def test_plain_security_result_uses_canonical_classifier(self):
        from scripts.secpal_pr_review import fast_path
        body = fast_path.CODEX_NO_FINDING_TEXT["SECURITY"] + "\n**Reviewed commit:** `bbbbbbbbbb`"
        self.assertEqual(provider_fallback._type_from_provider_body(body), "SECURITY")

    def test_eligibility_projects_the_accepted_claim_key(self):
        from scripts.secpal_pr_review import lifecycle_publication
        eligible = provider_fallback.classify(case(), "SECURITY", NOW)
        self.assertIsInstance(eligible.dispatch_key, lifecycle_publication.ProviderDispatchKey)

    def test_same_stable_account_survives_a_login_rename(self):
        observed = case()
        observed["comments"][0]["author"]["login"] = "renamed-account"
        eligible = provider_fallback.classify(observed, "SECURITY", NOW)
        self.assertEqual(eligible.dispatch_key.original_fallback_actor_node_id, "U_actor")
        self.assertEqual(eligible.dispatch_key.original_fallback_actor_database_id, 42)

    def test_plain_security_completion_does_not_block_code_fallback(self):
        observed = case()
        observed["comments"][0]["body"] = "@codex review"
        observed["comments"][1]["body"] = observed["comments"][1]["body"].replace("`bbbbbbb`", "`aaaaaaa`")
        observed["comments"][2]["body"] = "No security issues were found in this pull request.\n**Reviewed commit:** `bbbbbbbbbb`"
        eligible = provider_fallback.classify(observed, "CODE", NOW)
        self.assertEqual(eligible.dispatch_key.review_type, "CODE")
        with self.assertRaises(provider_fallback.ReplacementBlocked):
            provider_fallback.classify(observed, "SECURITY", NOW)

    def test_edited_request_and_substituted_comment_identity_are_closed(self):
        before = provider_fallback.classify(case(), "SECURITY", NOW)
        for change in (
            lambda x: x["comments"][0].update(id="IC_SUBSTITUTE"),
            lambda x: x["comments"][0].update(updatedAt="2026-09-30T18:00:00Z"),
            lambda x: x["comments"][0].update(body="@codex security review "),
        ):
            observed = case()
            change(observed)
            with self.subTest(change=change), self.assertRaises(provider_fallback.ReplacementBlocked):
                provider_fallback._persisted_replacement(before.dispatch_key, observed, None)

        edited = case()
        edited["comments"].append({**copy.deepcopy(edited["comments"][0]),
            "id": "IC_F2", "databaseId": 1001, "body": "withdrawn request",
            "createdAt": "2026-09-30T18:00:00Z"})
        edited["timeline"].append({"event": "commented", "id": 1001,
            "created_at": "2026-09-30T18:00:00Z",
            "canonical_trigger_history": ("@codex security review",)})
        with self.assertRaises(provider_fallback.ReplacementBlocked):
            provider_fallback._persisted_replacement(before.dispatch_key, edited, None)

    def test_writer_rejects_substituted_runtime_class(self):
        from types import SimpleNamespace
        from unittest import mock
        key = provider_fallback.classify(case(), "SECURITY", NOW).dispatch_key
        writes = []
        forged = lambda *_: SimpleNamespace(write=lambda body: writes.append(body))
        with mock.patch.object(provider_fallback, "LiveProviderObservation", forged):
            with self.assertRaises(provider_fallback.ReplacementBlocked):
                provider_fallback.write_claimed_replacement(
                    key.repository, key.delivery_issue, key.review_type,
                    key, provider_fallback.TRIGGERS[key.review_type])
        self.assertEqual(writes, [])

    def test_writer_rejects_substituted_runtime_method(self):
        from unittest import mock
        key = provider_fallback.classify(case(), "SECURITY", NOW).dispatch_key
        writes = []
        with mock.patch.object(provider_fallback.LiveProviderObservation, "write",
                               lambda _, body: writes.extend((body, body))):
            with self.assertRaises(provider_fallback.ReplacementBlocked):
                provider_fallback.write_claimed_replacement(
                    key.repository, key.delivery_issue, key.review_type,
                    key, provider_fallback.TRIGGERS[key.review_type])
        self.assertEqual(writes, [])

    def test_dispatch_rejects_candidate_local_source_before_claim(self):
        from types import SimpleNamespace
        from unittest import mock
        source_check = mock.Mock(side_effect=provider_fallback.fast_path.SecurityBlocker("unaccepted source"))
        actions = SimpleNamespace(_require_accepted_main_bridge_source=source_check)
        with mock.patch.object(provider_fallback.bootstrap_source_admission, "_load_actions_helper", return_value=actions), \
             mock.patch.object(provider_fallback.lifecycle_authority, "_load_lifecycle_trust_policy") as trust, \
             mock.patch.object(provider_fallback.lifecycle_execution, "_policy_role_signer", return_value=("signer", object())), \
             mock.patch.object(provider_fallback.publication, "execute_provider_dispatch_with_claim") as claim:
            with self.assertRaises(provider_fallback.fast_path.SecurityBlocker):
                provider_fallback.dispatch("SecPal/.github", 1031, 1035, "SECURITY")
            trust.assert_not_called()
            claim.assert_not_called()
        source_check.assert_called_once_with("SecPal/.github")

    def test_documented_cli_is_executable(self):
        import subprocess
        from pathlib import Path
        script = Path(__file__).resolve().parents[1] / "scripts/secpal-provider-fallback.py"
        result = subprocess.run([str(script), "--help"], capture_output=True)
        self.assertEqual(result.returncode, 0)

    def test_read_only_inspection_requires_an_available_exact_claim(self):
        from types import SimpleNamespace
        from unittest import mock
        from scripts.secpal_pr_review import lifecycle_publication as publication
        observed = case()
        eligible = provider_fallback.classify(observed, "SECURITY", NOW)
        key = eligible.dispatch_key
        current = SimpleNamespace(publication_oid=key.current_publication_oid,
                                  publication_digest=key.current_publication_digest)
        runtime = SimpleNamespace(observe=lambda: observed)
        for claims in ((), (SimpleNamespace(key=key),)):
            with mock.patch.object(publication, "verify_provider_dispatch_claims", return_value=(current, claims)):
                if claims:
                    with self.assertRaisesRegex(provider_fallback.ReplacementBlocked, "claim already exists"):
                        provider_fallback.inspect(runtime, "SECURITY")
                else:
                    self.assertEqual(provider_fallback.inspect(runtime, "SECURITY"), eligible)


class LiveObservationTests(unittest.TestCase):
    def setUp(self):
        import json
        from types import SimpleNamespace
        from unittest import mock
        from scripts.secpal_pr_review import lifecycle_authority as authority
        from scripts.secpal_pr_review import lifecycle_publication as publication
        self.mock = mock
        self.publication = publication
        self.authority = authority
        self.json = json
        self.namespace = SimpleNamespace
        self.actions = provider_fallback.bootstrap_source_admission._load_actions_helper()
        self.runtime = object.__new__(provider_fallback.LiveProviderObservation)
        self.runtime.repository = "SecPal/.github"
        self.runtime.delivery_issue = 1031
        self.runtime.pull_request = 1035
        self.runtime.actions = self.actions
        self.observed = case()
        self.runtime.github = SimpleNamespace(
            read_provider_fallback_transport=mock.Mock(return_value={"provider_transport": self.observed}),
            inspect_actor=mock.Mock(return_value=self.observed["actor"]),
            runner=SimpleNamespace(run=mock.Mock()),
        )
        self.current = SimpleNamespace(
            publication_oid="e" * 40, publication_digest="f" * 64,
            lifecycle=SimpleNamespace(**{k: v for k, v in self.observed["lifecycle"].items()
                                        if k not in {"bundle", "publication_oid", "publication_digest"}}),
        )
        self.chronology = {
            "repository": "SecPal/.github", "pull_request": 1035,
            "head": HEAD, "state": "OPEN", "draft": False,
            "author": ("aroviqen", "U_actor", 42),
            "events": (
                {"kind": "COMMIT", "head": HEAD, "created_at": READY},
                {"kind": "ReadyForReviewEvent", "created_at": READY},
                {"kind": "IssueComment", "database_id": 5916314995,
                 "created_at": FALLBACK, "versions": ((FALLBACK, "@codex security review"),)},
            ),
            "head_publication": self.observed["head_publication"],
        }

    def test_every_maintained_bundle_shape_normalizes(self):
        bundle = self.observed["lifecycle"]["bundle"]
        wrapped = {"kind": self.authority.PUBLICATION_EVIDENCE_KIND, "lifecycle_evidence": bundle}
        adopted = {k: None for k in self.authority.EXACT_ADOPTION_PUBLICATION_FIELDS}
        adopted.update(kind=self.authority.EXACT_ADOPTION_EVIDENCE_KIND,
                       transition_authorizations=bundle["transition_authorizations"],
                       authority_chain=bundle["authority_chain"])
        for representation in (bundle, wrapped, adopted):
            with self.subTest(kind=representation.get("kind", "native")):
                self.current.serialized_lifecycle_evidence = self.authority.canonical_json_bytes(representation)
                with self.mock.patch.object(self.publication, "verify_current_lifecycle_authority", return_value=self.current), self.mock.patch.object(
                    provider_fallback.provider_acquisition, "_observe", return_value=self.chronology):
                    result = self.runtime.observe()
                self.assertEqual(result["lifecycle"]["bundle"]["authority_chain"], bundle["authority_chain"])
                self.assertEqual(result["actor"], self.observed["actor"])

    def test_current_recheck_occurs_after_external_reads(self):
        import copy
        self.current.serialized_lifecycle_evidence = self.authority.canonical_json_bytes(self.observed["lifecycle"]["bundle"])
        for field in ("publication_oid", "publication_digest", "authority_digest", "head_sha", "lifecycle_id", "pull_request"):
            fresh = copy.deepcopy(self.current)
            target = fresh if field.startswith("publication_") else fresh.lifecycle
            setattr(target, field, 1036 if field == "pull_request" else "changed")
            reads = []
            def read_current(*_):
                reads.append("CURRENT")
                if len(reads) == 2:
                    self.runtime.github.inspect_actor.assert_called()
                    return fresh
                return self.current
            with self.subTest(field=field), self.mock.patch.object(self.publication, "verify_current_lifecycle_authority", side_effect=read_current), self.mock.patch.object(
                provider_fallback.provider_acquisition, "_observe", return_value=self.chronology):
                with self.assertRaisesRegex(provider_fallback.ReplacementBlocked, "CURRENT changed"):
                    self.runtime.observe()
            self.assertEqual(reads, ["CURRENT", "CURRENT"])
            self.runtime.github.runner.run.assert_not_called()

    def test_definite_post_rejections_propagate_without_reconciliation(self):
        for status in (403, 422, 429):
            error = self.actions.ActionCommandFailure([], 1, "", f"HTTP {status}: rejected")
            self.runtime.github.runner.run.side_effect = error
            with self.subTest(status=status), self.assertRaises(self.actions.ActionCommandFailure):
                self.runtime.write("@codex security review")
            self.runtime.github.read_provider_fallback_transport.assert_not_called()

    def test_only_indeterminate_post_results_are_ambiguous(self):
        for error in (self.actions.ActionCommandFailure([], 124, "", "timed out"),
                      self.actions.ActionCommandFailure([], 1, "", "connection reset"),
                      self.actions.MutationFailure("malformed JSON")):
            self.runtime.github.runner.run.side_effect = error
            with self.subTest(error=type(error)), self.assertRaises(self.publication.AmbiguousProviderDispatchWrite):
                self.runtime.write("@codex security review")
        self.runtime.github.runner.run.side_effect = None
        self.runtime.github.runner.run.return_value = {"body": "@codex security review", "id": 1001}
        self.assertEqual(self.runtime.write("@codex security review"), 1001)


class ClaimedConsumerTests(unittest.TestCase):
    """Real protected Git/CAS with only the external GitHub transport replaced."""

    def setUp(self):
        import importlib.util
        import sys
        from pathlib import Path
        from types import SimpleNamespace
        from unittest import mock
        from scripts.secpal_pr_review import lifecycle_publication as publication
        path = Path(__file__).with_name("secpal-lifecycle-publication-unit.py")
        spec = importlib.util.spec_from_file_location("fallback_publication_fixture", path)
        self.fixture_module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = self.fixture_module
        spec.loader.exec_module(self.fixture_module)
        self.fixture = self.fixture_module.LifecyclePublicationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.publication = publication
        self.mock = mock
        chain = self.fixture_module.Chain()
        for transition in ("INITIALIZED_DRAFT", "DRAFT_TO_READY", "UNRESTRICTED_REVIEW_CONSUMED", "ADDITIONAL_REVIEW_AUTHORIZATION_CONSUMED"):
            chain.append(transition)
        self.chain, self.current = self.fixture.enroll(chain)
        self.initial = case()
        head = self.current.lifecycle.head_sha
        self.initial.update(delivery_issue=self.current.lifecycle.delivery_issue,
                            pull_request=self.current.lifecycle.pull_request, head_sha=head)
        self.initial["head_publication"]["head"] = head
        self.initial["timeline"] = [
            {"event": "committed", "sha": head},
            {"event": "ready_for_review", "created_at": READY},
            {"event": "commented", "id": 5916314995, "created_at": FALLBACK},
        ]
        self.initial["lifecycle"] = {
            "repository": self.current.lifecycle.repository,
            "delivery_issue": self.current.lifecycle.delivery_issue,
            "pull_request": self.current.lifecycle.pull_request,
            "head_sha": head, "lifecycle_id": self.current.lifecycle.lifecycle_id,
            "authority_digest": self.current.lifecycle.authority_digest,
            "publication_oid": self.current.publication_oid,
            "publication_digest": self.current.publication_digest,
            "bundle": publication._lifecycle_bundle({"lifecycle_evidence": __import__("json").loads(self.current.serialized_lifecycle_evidence)}),
            "state": self.current.lifecycle.state,
        }
        old = "f" * 40
        for item in self.initial["comments"]:
            item["body"] = item["body"].replace(OLD, old).replace("`aaaaaaa`", "`fffffff`").replace("bbbbbbbbbb", head[:10]).replace("bbbbbbb", head[:7]).replace('"pullRequestNumber":1035', f'"pullRequestNumber":{self.current.lifecycle.pull_request}')
        self.state = copy.deepcopy(self.initial)
        self.writes = []
        self.writer_error = None
        # Capture the source projection before the isolated journal fixture
        # replaces trust transport. Consumer methods and Git/CAS stay real.
        actions = self.fixture_module.actions_owner if hasattr(self.fixture_module, "actions_owner") else provider_fallback.bootstrap_source_admission._load_actions_helper()
        github = SimpleNamespace(
            read_provider_fallback_transport=lambda _: {"provider_transport": self.observe()},
            inspect_actor=lambda: self.state["actor"],
            runner=SimpleNamespace(run=lambda argv: {
                "body": argv[-1].removeprefix("body="),
                "id": self.write(argv[-1].removeprefix("body=")),
            }),
        )
        self.transport_patches = [
            mock.patch.object(provider_fallback.bootstrap_source_admission, "_load_actions_helper", return_value=actions),
            mock.patch.object(actions, "LiveGitHub", return_value=github),
            mock.patch.object(provider_fallback.provider_acquisition, "_observe", side_effect=self.chronology),
        ]
        for mocked in self.transport_patches:
            mocked.start()
            self.addCleanup(mocked.stop)

    def chronology(self, repository, pull_request):
        timeline = self.state["timeline"]
        events = []
        for event in timeline:
            if event["event"] == "committed":
                events.append({"kind": "COMMIT", "head": event["sha"], "created_at": READY})
            elif event["event"] == "ready_for_review":
                events.append({"kind": "ReadyForReviewEvent", "created_at": event["created_at"]})
            elif event["event"] == "commented":
                comment = next(c for c in self.state["comments"] if c["databaseId"] == event["id"])
                events.append({"kind": "IssueComment", "database_id": event["id"],
                    "created_at": event["created_at"], "versions": ((event["created_at"], comment["body"]),)})
        actor = self.state["actor"]
        return {"repository": repository, "pull_request": pull_request,
                "head": self.state["head_sha"], "state": "OPEN", "draft": False,
                "author": (actor["login"], actor["node_id"], actor["database_id"]),
                "head_publication": self.state["head_publication"], "events": events}

    def observe(self):
        return copy.deepcopy(self.state)

    def write(self, body):
        self.writes.append(body)
        if self.writer_error:
            raise self.writer_error
        self.persist()
        return 1001

    def persist(self, number=1001):
        item = copy.deepcopy(self.state["comments"][0])
        item.update(id=f"IC_{number}", databaseId=number, createdAt="2026-09-30T18:00:00Z", updatedAt="2026-09-30T18:00:00Z")
        self.state["comments"].append(item)
        self.state["timeline"].append({"event": "commented", "id": number, "created_at": item["createdAt"]})

    def execute(self, **kwargs):
        return self.publication.execute_provider_dispatch_with_claim(
            self.current.lifecycle.repository, self.current.lifecycle.delivery_issue, "SECURITY",
            signer_identity=self.fixture_module.SIGNER, signer=self.fixture_module.signer_for(),
            expected_pull_request=self.current.lifecycle.pull_request, **kwargs)

    def test_winner_posts_one_comment_with_no_lifecycle_growth(self):
        before = self.publication.verify_current_lifecycle_authority(self.current.lifecycle.repository, self.current.lifecycle.delivery_issue)
        key = provider_fallback.classify(self.observe(), "SECURITY", NOW).dispatch_key
        result = self.execute()
        self.assertEqual(result.status, "DISPATCH_PERSISTED")
        self.assertEqual(result.write_attempts, 1)
        self.assertEqual(self.writes, ["@codex security review"])
        after, claims = self.publication.verify_provider_dispatch_claims(key.repository, key.delivery_issue)
        self.assertEqual(after, before)
        self.assertEqual(after.lifecycle.state, before.lifecycle.state)
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0].key, key)
        self.assertEqual(len(self.state["comments"]), len(self.initial["comments"]) + 1)
        self.assertEqual(self.state["lifecycle"]["bundle"], self.initial["lifecycle"]["bundle"])
        with self.assertRaises(provider_fallback.ReplacementBlocked):
            self.execute()
        self.assertEqual(len(self.writes), 1)

    def test_two_eligible_consumers_only_real_cas_winner_posts(self):
        keys = [provider_fallback.classify(self.observe(), "SECURITY", NOW).dispatch_key for _ in range(2)]
        self.assertEqual(*keys)
        real_cas = self.publication._cas_remote_ref
        nested = False
        def compete(*args, **kwargs):
            nonlocal nested
            if not nested:
                nested = True
                self.assertEqual(self.execute().status, "DISPATCH_PERSISTED")
            return real_cas(*args, **kwargs)
        with self.mock.patch.object(self.publication, "_cas_remote_ref", side_effect=compete):
            with self.assertRaises(self.publication.LifecyclePublicationError):
                self.execute()
        self.assertEqual(self.writes, ["@codex security review"])
        _, claims = self.publication.verify_provider_dispatch_claims(keys[0].repository, keys[0].delivery_issue)
        self.assertEqual(len(claims), 1)
        with self.assertRaises(provider_fallback.ReplacementBlocked):
            self.execute()
        self.assertEqual(len(self.writes), 1)

    def test_ambiguous_cas_reconciles_only_invocation_owned_claim(self):
        real_cas = self.publication._cas_remote_ref
        def ambiguous(*args, **kwargs):
            real_cas(*args, **kwargs)
            raise self.publication.LifecyclePublicationError("unknown CAS outcome")
        with self.mock.patch.object(self.publication, "_cas_remote_ref", side_effect=ambiguous):
            result = self.execute()
        self.assertEqual(result.status, "DISPATCH_PERSISTED")
        self.assertEqual(len(self.writes), 1)

    def test_definite_post_failure_consumes_claim_and_cannot_retry(self):
        self.writer_error = PermissionError("HTTP 403")
        with self.assertRaises(PermissionError):
            self.execute()
        with self.assertRaisesRegex(self.publication.LifecyclePublicationError, "claim already exists"):
            self.execute()
        self.assertEqual(len(self.writes), 1)

    def test_ambiguous_post_zero_one_and_duplicate_history(self):
        self.writer_error = self.publication.AmbiguousProviderDispatchWrite("unknown POST")
        result = self.execute()
        self.assertEqual(result.status, "INCOMPLETE_UNKNOWN_WRITE_RESULT")
        self.assertEqual(len(self.writes), 1)
        with self.assertRaisesRegex(self.publication.LifecyclePublicationError, "claim already exists"):
            self.execute()
        self.assertEqual(len(self.writes), 1)

    def test_ambiguous_post_with_one_persisted_comment(self):
        def ambiguous(body):
            self.writes.append(body)
            self.persist()
            raise self.publication.AmbiguousProviderDispatchWrite("unknown POST")
        self.write = ambiguous
        result = self.execute()
        self.assertEqual(result.status, "DISPATCH_PERSISTED")
        self.assertEqual(len(self.writes), 1)

    def test_duplicate_ambiguous_post_fails_closed(self):
        def ambiguous(body):
            self.writes.append(body)
            self.persist()
            self.persist(1002)
            raise self.publication.AmbiguousProviderDispatchWrite("unknown POST")
        self.write = ambiguous
        with self.assertRaisesRegex(provider_fallback.ReplacementBlocked, "duplicate"):
            self.execute()
        self.assertEqual(len(self.writes), 1)

    def test_ack_after_claim_cancels_without_post(self):
        real_claim = self.publication._publish_provider_dispatch_claim
        def claim(*args, **kwargs):
            result = real_claim(*args, **kwargs)
            self.state["comments"][0]["reactions"]["nodes"].append({"id": "provider_ack"})
            return result
        with self.mock.patch.object(self.publication, "_publish_provider_dispatch_claim", side_effect=claim):
            result = self.execute()
        self.assertEqual(result.status, "REPLACEMENT_NO_LONGER_REQUIRED")
        self.assertEqual(result.write_attempts, 0)
        self.assertEqual(self.writes, [])

    def test_current_advance_after_claim_blocks_all_provider_writes(self):
        real_claim = self.publication._publish_provider_dispatch_claim
        def claim(*args, **kwargs):
            result = real_claim(*args, **kwargs)
            self.chain.append("ADDITIONAL_REVIEW_AUTHORIZATION_CONSUMED")
            self.publication.advance_current_terminal(
                self.chain.published(), signer_identity=self.fixture_module.SIGNER,
                signer=self.fixture_module.signer_for())
            return result
        with self.mock.patch.object(self.publication, "_publish_provider_dispatch_claim", side_effect=claim):
            with self.assertRaisesRegex(self.publication.LifecyclePublicationError, "CURRENT changed"):
                self.execute()
        self.assertEqual(self.writes, [])

    def test_cli_pr_identity_is_checked_before_claim(self):
        with self.assertRaises(self.publication.LifecyclePublicationError):
            self.publication.execute_provider_dispatch_with_claim(
                self.current.lifecycle.repository, self.current.lifecycle.delivery_issue, "SECURITY",
                signer_identity=self.fixture_module.SIGNER, signer=self.fixture_module.signer_for(),
                expected_pull_request=self.current.lifecycle.pull_request + 1)
        self.assertEqual(self.writes, [])
        _, claims = self.publication.verify_provider_dispatch_claims(self.current.lifecycle.repository, self.current.lifecycle.delivery_issue)
        self.assertEqual(claims, ())


if __name__ == "__main__":
    unittest.main()
