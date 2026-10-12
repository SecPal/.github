#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Behavior evidence for bounded work-graph hard-gate refresh."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import shutil
import ssl
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import subprocess
import sys
from pathlib import Path
from unittest import SkipTest, TestCase, main, mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from secpal_work_graph import gate_refresh, replanning, replan_cli  # noqa: E402


class FakeGateway:
    def __init__(self, pulls, results):
        self.pulls = tuple(pulls)
        self.results = dict(results)
        self.statuses = []

    def open_pull_requests(self, repository, limit):
        self.repository = repository
        self.limit = limit
        return self.pulls

    def preflight(self, repository, pull):
        return None

    def publish(self, repository, pull, state, description):
        self.statuses.append(
            (repository, pull.number, pull.head_sha, state, description)
        )
        return {"outcome": "AUTHENTICATED_SUCCESS", "pr": pull.number, "state": state}

    def assess(self, repository, pull):
        return self.results[pull.number]


class GateRefreshTests(TestCase):
    def test_refresh_invalidates_each_bounded_head_before_reassessment(self):
        pulls = (
            gate_refresh.PullRequest(10, "a" * 40),
            gate_refresh.PullRequest(11, "b" * 40),
        )
        gateway = FakeGateway(pulls, {10: 0, 11: 1})

        report = gate_refresh.refresh_repository(
            gateway, "SecPal/.github", maximum_pull_requests=100
        )

        self.assertEqual(
            [(item[3], item[1]) for item in gateway.statuses],
            [("pending", 10), ("pending", 11), ("success", 10), ("failure", 11)],
        )
        self.assertEqual(report["refreshed"], 2)
        self.assertEqual(report["failed"], [11])

    def test_unavailable_gate_evidence_finishes_as_error_not_success(self):
        pull = gate_refresh.PullRequest(10, "a" * 40)
        gateway = FakeGateway((pull,), {10: 3})

        report = gate_refresh.refresh_repository(gateway, "SecPal/.github")

        self.assertEqual(gateway.statuses[-1][3], "error")
        self.assertEqual(report["unavailable"], [10])

    def test_candidate_overflow_fails_before_any_status_write(self):
        pulls = tuple(
            gate_refresh.PullRequest(number, f"{number:040x}")
            for number in range(1, 102)
        )
        gateway = FakeGateway(pulls, {})

        with self.assertRaisesRegex(
            gate_refresh.RefreshError, "bounded candidate limit"
        ):
            gate_refresh.refresh_repository(
                gateway, "SecPal/.github", maximum_pull_requests=100
            )

        self.assertEqual(gateway.statuses, [])

    def test_malformed_candidate_identity_fails_closed(self):
        with self.assertRaisesRegex(gate_refresh.RefreshError, "identity is malformed"):
            gate_refresh.PullRequest(True, "a" * 40)

    def test_refresh_workflow_covers_issue_edits_and_canonical_mutation_dispatch(self):
        workflow = (ROOT / ".github/workflows/work-graph-gate-refresh.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("issues:", workflow)
        self.assertIn("repository_dispatch:", workflow)
        self.assertIn("work_graph_mutated", workflow)
        self.assertIn("statuses: write", workflow)
        self.assertIn("scripts/secpal-work-graph-gate-refresh.py --apply", workflow)
        # Keep this maintained regression owner in normal CI and local preflight.
        command = "python3 -m unittest tests/secpal-work-graph-gate-refresh-unit.py"
        self.assertIn(command, (ROOT / ".github/workflows/quality.yml").read_text())
        self.assertIn(command, (ROOT / "scripts/preflight.sh").read_text())

    def test_canonical_replan_refreshes_every_affected_repository(self):
        classification = replanning.Classification(
            "NEW_RESPONSIBILITY",
            "CREATE_OWNED_SIBLING",
            False,
            True,
            "BEFORE_FREEZE",
            (),
        )
        plan = replanning.Plan(
            actor="alice",
            classification=classification,
            current_issue="SecPal/.github#735",
            owner="SecPal/.github#675",
            snapshot_digest="a" * 64,
            steps=(
                replanning.Step(
                    "ADD_BLOCKED_BY",
                    {
                        "blocked": "SecPal/.github#735",
                        "blocker": "SecPal/api#900",
                    },
                ),
            ),
            request={},
        )

        self.assertEqual(
            replan_cli._mutation_repositories(plan),
            ("SecPal/.github", "SecPal/api"),
        )

    def test_command_gateway_fails_closed_when_assessment_cannot_execute(self):
        gateway = gate_refresh.CommandGateway(gh="gh", repository_root=ROOT)

        with mock.patch.object(
            gate_refresh.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired("advisory", 120),
        ):
            with self.assertRaisesRegex(
                gate_refresh.RefreshError, "canonical hard-gate assessment failed"
            ):
                gateway.assess(
                    "SecPal/.github",
                    gate_refresh.PullRequest(759, "a" * 40),
                )


class PublicationTests(TestCase):
    def test_duplicate_response_keys_are_malformed_and_ambiguous(self):
        body = {
            "id": 123,
            "url": f"https://api.github.com/repos/{self.repository}/statuses/{self.pull.head_sha}",
            "state": "pending",
            "context": gate_refresh.HARD_CONTEXT,
            "target_url": self.target,
        }
        for key in ("url", "context", "state", "target_url", "id"):
            with self.subTest(key=key):
                raw = "{" + json.dumps(key) + ':"conflicting",' + json.dumps(body)[1:]
                response = subprocess.CompletedProcess(
                    [], 0, "HTTP/2.0 201 Created\n\n" + raw, ""
                )
                evidence = self.publish_error(response)
                self.assertEqual(evidence["outcome"], "AMBIGUOUS")
                self.assertEqual(evidence["http_status"], 201)
        status, _, payload = gate_refresh._response(
            'HTTP/2.0 200 OK\n\n[{"id":1,"id":2}]'
        )
        self.assertEqual(status, 200)
        self.assertIsNone(payload)

    def test_secondary_rate_limit_uses_validated_retry_after(self):
        evidence = self.publish_error(
            self.response(
                403,
                {
                    "message": "You have exceeded a secondary rate limit. Please wait a few minutes before you try again."
                },
                "Retry-After: 60\r\nX-RateLimit-Remaining: 100\r\n",
            )
        )
        self.assertEqual(evidence["category"], "RATE_LIMITED")
        self.assertIsNone(evidence["safe_message"])
        for value in ("secret", "-1", "99999999999"):
            evidence = self.publish_error(
                self.response(
                    403,
                    {"message": "untrusted"},
                    f"Retry-After: {value}\r\nX-RateLimit-Remaining: 100\r\n",
                )
            )
            self.assertEqual(evidence["category"], "AUTHORIZATION_REJECTED")

    def test_command_pins_host_and_excludes_unrelated_environment(self):
        environment = {
            "GH_HOST": "wrong.invalid",
            "GH_ENTERPRISE_TOKEN": "synthetic-enterprise",
            "GH_TOKEN": "synthetic-github",
            "PRIVATE_ENV": "synthetic-secret",
            "SSL_CERT_FILE": "wrong.pem",
            "PATH": "/untrusted",
            "HOME": "/synthetic-home",
            "GH_CONFIG_DIR": "/synthetic-config",
        }
        gateway = gate_refresh.CommandGateway(gh="/usr/bin/gh", repository_root=ROOT)
        with mock.patch.dict(os.environ, environment, clear=True), mock.patch(
            "subprocess.run", return_value=subprocess.CompletedProcess([], 0, "", "")
        ) as run:
            gateway._run(["api", "repos/SecPal/.github/commits/abc/statuses"])
        self.assertEqual(
            run.call_args.args[0][:4],
            ["/usr/bin/gh", "api", "--hostname", "github.com"],
        )
        child = run.call_args.kwargs["env"]
        self.assertEqual(child["GH_HOST"], "github.com")
        self.assertEqual(child["PATH"], os.defpath)
        self.assertEqual(child["GH_TOKEN"], "synthetic-github")
        self.assertEqual(child["GH_CONFIG_DIR"], "/synthetic-config")
        for key in ("GH_ENTERPRISE_TOKEN", "PRIVATE_ENV", "SSL_CERT_FILE"):
            self.assertNotIn(key, child)

    def test_optional_cli_absence_skips_only_real_transport(self):
        with mock.patch("shutil.which", return_value=None), self.assertRaises(SkipTest):
            self.test_real_gh_transport_preserves_http_rejection_without_secret_output()

    def setUp(self):
        self.gateway = gate_refresh.CommandGateway(gh="gh", repository_root=ROOT)
        self.pull = gate_refresh.PullRequest(10, "a" * 40)
        self.repository = "SecPal/.github"
        self.target = "https://github.com/SecPal/.github/pull/10"

    def response(self, status, body, headers="", returncode=1):
        return subprocess.CompletedProcess(
            [],
            returncode,
            f"HTTP/2.0 {status} Reason\r\n{headers}\r\n{json.dumps(body)}",
            "Authorization: Bearer PRIVATE-STDERR",
        )

    def publish_error(self, response, state="pending"):
        with mock.patch.object(self.gateway, "_run", return_value=response) as run:
            with self.assertRaises(gate_refresh.RefreshError) as caught:
                self.gateway.publish(self.repository, self.pull, state, "refresh")
        self.assertEqual(run.call_count, 1)
        self.assertNotIn("PRIVATE-STDERR", str(caught.exception))
        return caught.exception.evidence

    def test_http_rejections_have_bounded_identity_and_safe_provider_details(self):
        cases = (
            (401, {"message": "Bad credentials"}, "AUTHORIZATION_REJECTED"),
            (
                403,
                {"message": "Resource not accessible by integration"},
                "AUTHORIZATION_REJECTED",
            ),
            (
                422,
                {
                    "message": "Validation Failed",
                    "errors": [
                        {"resource": "Status", "code": "invalid", "field": "state"}
                    ],
                },
                "VALIDATION_REJECTED",
            ),
            (
                422,
                {
                    "message": "Validation Failed",
                    "errors": [
                        {
                            "resource": "Status",
                            "code": "custom",
                            "message": "This SHA and context has reached the maximum number of statuses.",
                        }
                    ],
                },
                "CAPACITY_EXHAUSTED",
            ),
            (429, {"message": "rate limit exceeded"}, "RATE_LIMITED"),
            (403, {"message": "untrusted rate message"}, "RATE_LIMITED"),
        )
        for status, body, category in cases:
            with self.subTest(status=status, category=category):
                evidence = self.publish_error(
                    self.response(
                        status,
                        body,
                        (
                            "X-GitHub-Request-Id: ABCD:1234:5678:90AB\r\nRetry-After: 60\r\nX-RateLimit-Remaining: 0\r\n"
                            if category == "RATE_LIMITED"
                            else ""
                        ),
                    )
                )
                self.assertEqual(evidence["outcome"], "HTTP_REJECTED")
                self.assertEqual(evidence["http_status"], status)
                self.assertEqual(evidence["category"], category)
                self.assertEqual(
                    (
                        evidence["repository"],
                        evidence["pr"],
                        evidence["sha"],
                        evidence["context"],
                        evidence["phase"],
                        evidence["state"],
                    ),
                    (
                        self.repository,
                        10,
                        self.pull.head_sha,
                        gate_refresh.HARD_CONTEXT,
                        "invalidation",
                        "pending",
                    ),
                )
                self.assertEqual(
                    evidence["command"], {"outcome": "EXITED", "returncode": 1}
                )
                if category == "RATE_LIMITED":
                    self.assertEqual(evidence["request_id"], "ABCD:1234:5678:90AB")
                    self.assertEqual(evidence["retry"]["retry_after_seconds"], 60)

    def test_no_response_and_server_failures_remain_ambiguous_without_replay(self):
        for response in (
            subprocess.CompletedProcess([], 1, "", "gh: connection lost (HTTP 403)"),
            self.response(503, {"message": "server error"}),
            self.response(408, {"message": "timeout"}),
        ):
            with self.subTest(response=response.stdout):
                evidence = self.publish_error(response)
                self.assertEqual(evidence["outcome"], "AMBIGUOUS")
                self.assertEqual(
                    evidence["http_status"],
                    None if not response.stdout else int(response.stdout.split()[1]),
                )
        for failure, outcome in (
            (subprocess.TimeoutExpired("gh", 60, output="secret"), "TIMED_OUT"),
            (OSError("secret"), "EXECUTION_FAILED"),
        ):
            with mock.patch.object(self.gateway, "_run", side_effect=failure):
                with self.assertRaises(gate_refresh.RefreshError) as caught:
                    self.gateway.publish(
                        self.repository, self.pull, "success", "passed"
                    )
            self.assertEqual(caught.exception.evidence["command"]["outcome"], outcome)
            self.assertIsNone(caught.exception.evidence["http_status"])
            self.assertNotIn("secret", str(caught.exception))

    def test_timeout_keeps_an_actually_received_http_envelope_ambiguous(self):
        partial = b"HTTP/2.0 201 Created\r\nX-GitHub-Request-Id: ABCD:1234:5678:90AB\r\n\r\n{incomplete PRIVATE"
        with mock.patch.object(
            gate_refresh.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired("gh", 60, output=partial),
        ) as run:
            with self.assertRaises(gate_refresh.RefreshError) as caught:
                self.gateway.publish(self.repository, self.pull, "success", "passed")
        evidence = caught.exception.evidence
        self.assertEqual(evidence["command"]["outcome"], "TIMED_OUT")
        self.assertEqual(evidence["http_status"], 201)
        self.assertEqual(evidence["http_response"], "RECEIVED")
        self.assertEqual(evidence["outcome"], "AMBIGUOUS")
        self.assertEqual(evidence["request_id"], "ABCD:1234:5678:90AB")
        self.assertNotIn("PRIVATE", str(caught.exception))
        self.assertEqual(run.call_count, 1)

    def test_malformed_oversized_and_nested_secrets_never_escape(self):
        bodies = (
            {
                "message": "Bearer PRIVATE-TOP",
                "errors": [
                    {
                        "resource": "Status",
                        "code": "PRIVATE-CODE",
                        "message": "ghp_PRIVATE",
                        "nested": {"token": "PRIVATE-NESTED"},
                    }
                ],
                "authorization": "PRIVATE-HEADER",
            },
            {
                "message": "Validation Failed",
                "errors": [{"code": {"secret": "PRIVATE-NESTED"}}],
            },
            {"message": "PRIVATE-OVERSIZED" * 10000},
            ["PRIVATE-LIST"],
        )
        for body in bodies:
            evidence = self.publish_error(
                self.response(
                    422,
                    body,
                    "X-GitHub-Request-Id: PRIVATE-ID\r\nRetry-After: PRIVATE-RETRY\r\nAuthorization: PRIVATE-HEADER\r\n",
                )
            )
            serialized = json.dumps(evidence)
            self.assertNotIn("PRIVATE", serialized)
            self.assertLess(len(serialized), 2000)
            self.assertEqual(evidence["outcome"], "HTTP_REJECTED")
        malformed = subprocess.CompletedProcess(
            [], 1, "HTTP/2.0 422 Reason\r\n\r\nnot-json PRIVATE", ""
        )
        self.assertEqual(self.publish_error(malformed)["outcome"], "HTTP_REJECTED")

    def test_success_requires_exact_provider_publication_identity(self):
        body = {
            "url": f"https://api.github.com/repos/{self.repository}/statuses/{self.pull.head_sha}",
            "id": 123,
            "state": "success",
            "context": gate_refresh.HARD_CONTEXT,
            "target_url": self.target,
        }
        with mock.patch.object(
            self.gateway, "_run", return_value=self.response(201, body, returncode=0)
        ) as run:
            evidence = self.gateway.publish(
                self.repository, self.pull, "success", "passed"
            )
        self.assertEqual(evidence["outcome"], "AUTHENTICATED_SUCCESS")
        self.assertIn("--include", run.call_args.args[0])
        for field, value in (
            ("url", body["url"].replace("a" * 40, "b" * 40)),
            ("url", body["url"].replace("SecPal/.github", "other/repo")),
            ("context", "other gate"),
            ("target_url", self.target + "1"),
            ("state", "pending"),
            ("id", True),
        ):
            with self.subTest(field=field, value=value):
                evidence = self.publish_error(
                    self.response(201, {**body, field: value}, returncode=0),
                    state="success",
                )
                self.assertEqual(evidence["outcome"], "AMBIGUOUS")
        self.assertEqual(
            self.publish_error(subprocess.CompletedProcess([], 0, "", ""))["outcome"],
            "AMBIGUOUS",
        )

    def test_capacity_preflight_counts_context_case_insensitively_and_requires_two_slots(
        self,
    ):
        for count, allowed in ((998, True), (999, False), (1000, False)):
            entries = [
                {
                    "context": gate_refresh.HARD_CONTEXT.lower(),
                    "url": f"https://api.github.com/repos/{self.repository}/statuses/{self.pull.head_sha}",
                    "id": n + 1,
                }
                for n in range(count)
            ]
            responses = [
                self.response(200, entries[i : i + 100], returncode=0)
                for i in range(0, count, 100)
            ]
            if count % 100 == 0:
                responses.append(self.response(200, [], returncode=0))
            with self.subTest(count=count), mock.patch.object(
                self.gateway, "_run", side_effect=responses
            ) as run:
                if allowed:
                    self.gateway.preflight(self.repository, self.pull)
                else:
                    with self.assertRaises(gate_refresh.RefreshError) as caught:
                        self.gateway.preflight(self.repository, self.pull)
                    self.assertEqual(
                        caught.exception.evidence["category"], "CAPACITY_INSUFFICIENT"
                    )
                    self.assertEqual(
                        caught.exception.evidence["outcome"], "NOT_ATTEMPTED"
                    )
                self.assertTrue(
                    all("POST" not in call.args[0] for call in run.call_args_list)
                )

    def test_capacity_accepts_realistic_full_status_pages(self):
        # List-status representations include creator/link metadata, not only
        # the three facts consumed by the counter. A normal 100-row page can
        # exceed the smaller status-POST diagnostic body budget.
        rows = [
            {
                "id": n + 1,
                "url": f"https://api.github.com/repos/{self.repository}/statuses/{self.pull.head_sha}",
                "context": gate_refresh.HARD_CONTEXT,
                "state": "success",
                "description": "Passed",
                "target_url": self.target,
                "creator": {
                    "login": "fixture-user",
                    "links": "https://api.github.com/users/fixture-user/" * 40,
                },
            }
            for n in range(100)
        ]
        self.assertGreater(len(json.dumps(rows)), gate_refresh.MAXIMUM_RESPONSE_BYTES)
        with mock.patch.object(
            self.gateway,
            "_run",
            side_effect=[
                self.response(200, rows, returncode=0),
                self.response(200, [], returncode=0),
            ],
        ):
            self.gateway.preflight(self.repository, self.pull)

    def test_unreadable_or_unbounded_capacity_fails_before_publication(self):
        for response in (
            self.response(403, {"message": "Bad credentials"}),
            self.response(200, [{"context": gate_refresh.HARD_CONTEXT}], returncode=0),
        ):
            with mock.patch.object(self.gateway, "_run", return_value=response):
                with self.assertRaises(gate_refresh.RefreshError):
                    self.gateway.preflight(self.repository, self.pull)

    def test_partial_invalidation_and_terminal_publication_preserve_truth(self):
        pulls = (self.pull, gate_refresh.PullRequest(11, "b" * 40))
        for failure_index in (0, 1, 2, 3):
            gateway = FakeGateway(pulls, {10: 0, 11: 0})
            original = gateway.publish

            def publish(repository, pull, state, description):
                if len(gateway.statuses) == failure_index:
                    raise gate_refresh.PublicationError(
                        {"outcome": "AMBIGUOUS", "pr": pull.number, "state": state}
                    )
                return original(repository, pull, state, description)

            with self.subTest(index=failure_index), mock.patch.object(
                gateway, "publish", side_effect=publish
            ), mock.patch.object(gateway, "assess", wraps=gateway.assess) as assess:
                with self.assertRaises(gate_refresh.RefreshError) as caught:
                    gate_refresh.refresh_repository(gateway, self.repository)
                report = caught.exception.evidence
                self.assertEqual(len(report["publications"]), failure_index)
                self.assertEqual(report["failure"]["outcome"], "AMBIGUOUS")
                self.assertEqual(report["refreshed"], max(0, failure_index - 2))
                self.assertEqual(assess.call_count, max(0, failure_index - 1))

    def test_capacity_pagination_and_identity_fail_closed(self):
        row = {
            "id": 1,
            "url": f"https://api.github.com/repos/{self.repository}/statuses/{self.pull.head_sha}",
            "context": "other check",
        }
        for rows in (
            [row, row],
            [{**row, "url": row["url"].replace(self.pull.head_sha, "b" * 40)}],
            [{**row, "url": row["url"].replace(self.repository, "other/repo")}],
            [{**row, "context": {"token": "PRIVATE"}}],
        ):
            with self.subTest(rows=rows), mock.patch.object(
                self.gateway,
                "_run",
                return_value=self.response(200, rows, returncode=0),
            ):
                with self.assertRaises(gate_refresh.RefreshError) as caught:
                    self.gateway.preflight(self.repository, self.pull)
                self.assertEqual(
                    caught.exception.evidence["category"], "CAPACITY_MALFORMED"
                )

        def page(arguments):
            number = int(arguments[-1].split("page=")[-1])
            return self.response(
                200, [{**row, "id": number * 100 + i} for i in range(100)], returncode=0
            )

        with mock.patch.object(self.gateway, "_run", side_effect=page) as run:
            with self.assertRaises(gate_refresh.RefreshError) as caught:
                self.gateway.preflight(self.repository, self.pull)
        self.assertEqual(
            caught.exception.evidence["category"], "CAPACITY_BOUND_EXCEEDED"
        )
        self.assertEqual(run.call_count, gate_refresh.MAXIMUM_STATUS_PAGES)

    def test_duplicate_headers_and_deep_json_cannot_supply_diagnostics(self):
        response = self.response(
            403,
            {},
            "Retry-After: 60\r\nRetry-After: 120\r\nX-GitHub-Request-Id: ABCD:1234:5678:90AB\r\nX-GitHub-Request-Id: ABCD:1111:2222:3333\r\n",
        )
        evidence = self.publish_error(response)
        self.assertEqual(evidence["retry"], {})
        self.assertIsNone(evidence["request_id"])
        response = subprocess.CompletedProcess(
            [], 1, "HTTP/2.0 422 Reason\n\n" + "[" * 2000 + "0" + "]" * 2000, ""
        )
        self.assertEqual(self.publish_error(response)["outcome"], "HTTP_REJECTED")

    def test_invalid_repository_never_executes_and_decode_loss_is_ambiguous(self):
        with mock.patch.object(self.gateway, "_run") as run:
            with self.assertRaises(gate_refresh.RefreshError):
                self.gateway.publish(
                    "SecPal/.github?credential=PRIVATE", self.pull, "success", "passed"
                )
        run.assert_not_called()
        with mock.patch.object(
            gate_refresh.subprocess,
            "run",
            side_effect=UnicodeDecodeError("utf-8", b"PRIVATE", 0, 1, "bad output"),
        ):
            with self.assertRaises(gate_refresh.RefreshError) as caught:
                self.gateway.publish(self.repository, self.pull, "success", "passed")
        self.assertEqual(
            caught.exception.evidence["command"]["outcome"], "OUTPUT_UNREADABLE"
        )
        self.assertEqual(caught.exception.evidence["outcome"], "AMBIGUOUS")
        self.assertNotIn("PRIVATE", str(caught.exception))

    def test_cli_failure_retains_partial_evidence_and_returns_nonzero(self):
        spec = importlib.util.spec_from_file_location(
            "refresh_cli", ROOT / "scripts/secpal-work-graph-gate-refresh.py"
        )
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        gateway = FakeGateway((self.pull,), {10: 0})
        original = gateway.publish

        def publish(repository, pull, state, description):
            if state == "success":
                raise gate_refresh.PublicationError(
                    {"outcome": "HTTP_REJECTED", "http_status": 403, "state": state}
                )
            return original(repository, pull, state, description)

        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(
            cli.gate_refresh, "CommandGateway", return_value=gateway
        ), mock.patch.object(gateway, "publish", side_effect=publish), mock.patch(
            "sys.stdout", stdout
        ), mock.patch(
            "sys.stderr", stderr
        ):
            code = cli.main(["--repo", self.repository, "--apply"])
        self.assertEqual(code, 2)
        self.assertEqual(stdout.getvalue(), "")
        report = json.loads(stderr.getvalue().split("hard-gate refresh failed: ", 1)[1])
        self.assertEqual(report["outcome"], "PARTIAL_PUBLICATION")
        self.assertEqual(report["refreshed"], 0)
        self.assertEqual(report["failure"]["http_status"], 403)
        self.assertEqual(report["publications"][0]["state"], "pending")

    def test_real_gh_transport_preserves_http_rejection_without_secret_output(self):
        # Real CLI/TLS/HTTP representation, with an entirely local provider and
        # a synthetic credential. Never contacts GitHub or reads local gh config.
        gh = shutil.which("gh")
        if gh is None:
            self.skipTest(
                "gh is optional for local preflight; controlled regressions still run"
            )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cert, key = root / "cert.pem", root / "key.pem"
            subprocess.run(
                [
                    "openssl",
                    "req",
                    "-x509",
                    "-newkey",
                    "rsa:2048",
                    "-nodes",
                    "-keyout",
                    str(key),
                    "-out",
                    str(cert),
                    "-days",
                    "1",
                    "-subj",
                    "/CN=localhost",
                    "-addext",
                    "subjectAltName=DNS:localhost",
                ],
                check=True,
                capture_output=True,
                timeout=20,
            )
            requests = []

            class Provider(BaseHTTPRequestHandler):
                def do_POST(self):
                    requests.append(
                        (
                            self.path,
                            json.loads(
                                self.rfile.read(int(self.headers["Content-Length"]))
                            ),
                        )
                    )
                    self.send_response(422)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("X-GitHub-Request-Id", "ABCD:1234:5678:90AB")
                    self.end_headers()
                    self.wfile.write(
                        json.dumps(
                            {
                                "message": "Validation Failed",
                                "errors": [
                                    {
                                        "resource": "Status",
                                        "code": "custom",
                                        "message": "This SHA and context has reached the maximum number of statuses.",
                                        "nested": {"token": "PRIVATE-NESTED"},
                                    }
                                ],
                            }
                        ).encode()
                    )

                def log_message(self, *arguments):
                    pass

            server = HTTPServer(("127.0.0.1", 0), Provider)
            tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            tls.load_cert_chain(cert, key)
            server.socket = tls.wrap_socket(server.socket, server_side=True)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            environment = {
                "PATH": os.defpath,
                "GH_HOST": f"localhost:{server.server_port}",
                "GH_ENTERPRISE_TOKEN": "synthetic-test-token",
                "GH_CONFIG_DIR": str(root / "gh-config"),
                "GH_PROMPT_DISABLED": "1",
                "SSL_CERT_FILE": str(cert),
            }
            try:
                gateway = gate_refresh.CommandGateway(gh=gh, repository_root=ROOT)

                # Only this controlled test transport selects the local host.
                # Production host/environment pinning has a separate regression.
                def local_transport(arguments):
                    return subprocess.run(
                        [gh, *arguments],
                        cwd=ROOT,
                        text=True,
                        capture_output=True,
                        check=False,
                        timeout=60,
                        env=environment,
                    )

                with mock.patch.object(gateway, "_run", side_effect=local_transport):
                    with self.assertRaises(gate_refresh.RefreshError) as caught:
                        gateway.publish(
                            self.repository, self.pull, "pending", "refresh"
                        )
                evidence = caught.exception.evidence
                self.assertEqual(evidence["http_status"], 422)
                self.assertEqual(evidence["outcome"], "HTTP_REJECTED")
                self.assertEqual(evidence["category"], "CAPACITY_EXHAUSTED")
                self.assertEqual(evidence["request_id"], "ABCD:1234:5678:90AB")
                self.assertNotIn("PRIVATE", str(caught.exception))
                self.assertNotIn("synthetic-test-token", str(caught.exception))
                self.assertEqual(len(requests), 1)
                self.assertTrue(
                    requests[0][0].endswith(
                        f"/repos/{self.repository}/statuses/{self.pull.head_sha}"
                    )
                )
                self.assertEqual(requests[0][1]["context"], gate_refresh.HARD_CONTEXT)
            finally:
                server.shutdown()
                worker.join(timeout=5)
                server.server_close()

    def test_all_capacity_preflights_finish_before_the_first_write(self):
        gateway = FakeGateway((self.pull, gate_refresh.PullRequest(11, "b" * 40)), {})
        with mock.patch.object(
            gateway,
            "preflight",
            side_effect=[None, gate_refresh.RefreshError("capacity unreadable")],
        ):
            with self.assertRaises(gate_refresh.RefreshError) as caught:
                gate_refresh.refresh_repository(gateway, self.repository)
        self.assertEqual(gateway.statuses, [])
        self.assertEqual(caught.exception.evidence["outcome"], "BEFORE_PUBLICATION")


if __name__ == "__main__":
    main()
