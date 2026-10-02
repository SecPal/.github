# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Hermetic admission cases for one persisted, unacknowledged fallback."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import unittest

from scripts.secpal_pr_review import provider_fallback


HEAD = "b" * 40
OLD = "a" * 40
READY = "2026-09-30T12:32:06Z"
FALLBACK = "2026-09-30T17:27:44Z"
NOW = datetime(2026, 9, 30, 18, 1, tzinfo=timezone.utc)


def case() -> dict:
    return {
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
             "author": {"login": "chatgpt-codex-connector"},
             "reactions": {"nodes": [], "pageInfo": {"hasNextPage": False}}},
            {"id": "IC_CODE", "databaseId": 5916340367,
             "body": "Codex Review: Didn't find any major issues.\n\n"
                     "**Reviewed commit:** `bbbbbbbbbb`",
             "createdAt": "2026-09-30T17:29:22Z",
             "author": {"login": "chatgpt-codex-connector"},
             "reactions": {"nodes": [], "pageInfo": {"hasNextPage": False}}},
        ],
        "reviews": [],
        "threads": [],
    }


class ReplacementAdmissionTests(unittest.TestCase):
    def test_target_shaped_security_fallback_is_eligible(self):
        result = provider_fallback.classify(case(), "SECURITY", NOW)
        self.assertEqual(result.first_comment_database_id, 5916314995)
        self.assertEqual(result.trigger_body, "@codex security review")
        self.assertEqual(result.replacement_count, 0)

    def test_identity_and_authority_substitutions_fail_closed(self):
        changes = [
            lambda x: x.update(repository="Other/repo"),
            lambda x: x.update(pull_request=1036),
            lambda x: x.update(head_sha=OLD),
            lambda x: x.update(pr_state="CLOSED"),
            lambda x: x.update(is_draft=True),
            lambda x: x["lifecycle"]["state"].update(ready=False),
            lambda x: x["lifecycle"]["state"].update(unrestricted_review_count=0),
            lambda x: x["lifecycle"]["authority_chain"].pop(),
            lambda x: x["lifecycle"]["authority_chain"][-1].update(head_sha=OLD),
            lambda x: x["comments"][0]["author"].update(login="attacker"),
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
            {"id": "R1", "user": {"login": "chatgpt-codex-connector"}}
        )
        variants.append(reaction)
        processing = case()
        processing["comments"].append({
            "id": "IC_STATUS", "databaseId": 5916400001,
            "body": "Security review is running", "createdAt": FALLBACK,
            "author": {"login": "chatgpt-codex-connector"},
            "reactions": {"nodes": [], "pageInfo": {"hasNextPage": False}},
        })
        variants.append(processing)
        review = case()
        review["reviews"].append({
            "id": "PRR_SECURITY", "body": "### 🛡️ Codex Security Review",
            "commit": {"oid": HEAD},
            "author": {"login": "chatgpt-codex-connector"},
        })
        variants.append(review)
        terminal = case()
        terminal["comments"].append({
            "id": "IC_SECURITY", "databaseId": 5916400002,
            "body": "### 🛡️ Codex Security Review\n"
                    "No security issues were found in this pull request.\n"
                    "**Reviewed commit:** `bbbbbbbbbb`",
            "createdAt": FALLBACK,
            "author": {"login": "chatgpt-codex-connector"},
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
            "author": {"login": "chatgpt-codex-connector"},
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

        initial = case()
        changed = case()
        changed["lifecycle"]["lifecycle_id"] = "lifecycle:" + "d" * 64
        observations = iter((initial, changed))
        writes = []
        with self.assertRaises(provider_fallback.ReplacementBlocked):
            provider_fallback.dispatch_once(
                lambda: next(observations), writes.append, "SECURITY", lambda: NOW)
        self.assertEqual(writes, [])

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
        observations = iter((before, before, after))
        writes = []

        def ambiguous_write(body):
            writes.append(body)
            raise OSError("unknown mutation outcome")

        result = provider_fallback.dispatch_once(
            lambda: next(observations), ambiguous_write, "SECURITY", lambda: NOW)
        self.assertEqual(result.status, "PERSISTED")
        self.assertEqual(result.replacement_comment_database_id, 5916400003)
        self.assertEqual(writes, ["@codex security review"])
        self.assertEqual(
            before["lifecycle"]["state"]["unrestricted_review_count"], 1)
        self.assertEqual(
            len([x for x in before["lifecycle"]["authority_chain"]
                 if x["transition_kind"] == "ADDITIONAL_REVIEW_AUTHORIZATION_CONSUMED"]),
            1,
        )

        observations = iter((before, before, before))
        result = provider_fallback.dispatch_once(
            lambda: next(observations), ambiguous_write, "SECURITY", lambda: NOW)
        self.assertEqual(result.status, "INCOMPLETE_UNKNOWN_WRITE_RESULT")
        self.assertEqual(len(writes), 2)

    def test_late_original_ack_prevents_write(self):
        later = case()
        later["comments"][0]["reactions"]["nodes"].append(
            {"id": "R1", "user": {"login": "chatgpt-codex-connector"}}
        )
        observations = iter((case(), later))
        writes = []
        with self.assertRaises(provider_fallback.ReplacementBlocked):
            provider_fallback.dispatch_once(
                lambda: next(observations), writes.append, "SECURITY", lambda: NOW)
        self.assertEqual(writes, [])


if __name__ == "__main__":
    unittest.main()
