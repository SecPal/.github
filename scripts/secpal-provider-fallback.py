#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Inspect or dispatch one same-assessment provider fallback replacement."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.secpal_pr_review import lifecycle_publication as publication
from scripts.secpal_pr_review import provider_fallback


def _actions() -> Any:
    path = ROOT / "scripts/secpal-pr-review-actions.py"
    spec = importlib.util.spec_from_file_location("secpal_provider_actions", path)
    if spec is None or spec.loader is None:
        raise provider_fallback.ReplacementBlocked("maintained action helper is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class LiveProviderObservation:
    def __init__(self, repository: str, delivery_issue: int, pull_request: int) -> None:
        self.repository = repository
        self.delivery_issue = delivery_issue
        self.pull_request = pull_request
        self.actions = _actions()
        self.github = self.actions.LiveGitHub()

    def _timeline_once(self) -> list[dict[str, Any]]:
        endpoint = (
            f"repos/{self.repository}/issues/{self.pull_request}"
            "/timeline?per_page=100"
        )
        response = publication._run_gh([
            "api", "--hostname", "github.com",
            "-H", "Accept: application/vnd.github+json",
            "-H", "X-GitHub-Api-Version: 2026-03-10",
            endpoint,
        ])
        if response.returncode != 0:
            raise provider_fallback.ReplacementBlocked("PR chronology is unavailable")
        try:
            items = json.loads(response.stdout)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise provider_fallback.ReplacementBlocked("PR chronology is malformed") from exc
        if not isinstance(items, list) or len(items) >= 100 or any(
            not isinstance(item, dict) for item in items
        ):
            raise provider_fallback.ReplacementBlocked("PR chronology exceeds its complete bound")
        return items

    def observe(self) -> dict[str, Any]:
        current = publication.verify_current_lifecycle_authority(
            self.repository, self.delivery_issue
        )
        transport = self.github.read_provider_fallback_transport({
            "repository": self.repository,
            "pull_request_number": self.pull_request,
        })["provider_transport"]
        first_timeline = self._timeline_once()
        second_timeline = self._timeline_once()
        if first_timeline != second_timeline:
            raise provider_fallback.ReplacementBlocked(
                "PR chronology changed between bounded reads"
            )
        actor = self.github.inspect_actor()["login"]
        lifecycle = current.lifecycle
        try:
            signed = json.loads(current.serialized_lifecycle_evidence)
            chain = signed["lifecycle_evidence"]["authority_chain"]
        except (TypeError, KeyError, json.JSONDecodeError) as exc:
            raise provider_fallback.ReplacementBlocked(
                "authenticated assessment history is unavailable"
            ) from exc
        return {
            **transport,
            "delivery_issue": self.delivery_issue,
            "actor": actor,
            "lifecycle": {
                "repository": lifecycle.repository,
                "delivery_issue": lifecycle.delivery_issue,
                "pull_request": lifecycle.pull_request,
                "head_sha": lifecycle.head_sha,
                "lifecycle_id": lifecycle.lifecycle_id,
                "authority_digest": lifecycle.authority_digest,
                "publication_oid": current.publication_oid,
                "authority_chain": chain,
                "state": lifecycle.state,
            },
            "timeline": second_timeline,
        }

    def write(self, body: str) -> int | None:
        response = self.github.runner.run([
            "gh", "api", "--hostname", "github.com",
            f"repos/{self.repository}/issues/{self.pull_request}/comments",
            "--method", "POST", "-f", f"body={body}",
        ])
        if not isinstance(response, dict) or response.get("body") != body:
            raise provider_fallback.ReplacementBlocked(
                "replacement write response is indeterminate"
            )
        value = response.get("id")
        if type(value) is not int or value <= 0:
            raise provider_fallback.ReplacementBlocked(
                "replacement write identity is indeterminate"
            )
        return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("inspect", "dispatch"))
    parser.add_argument("--repo", required=True)
    parser.add_argument("--delivery-issue", required=True, type=int)
    parser.add_argument("--pr", required=True, type=int)
    parser.add_argument("--review-type", required=True, choices=("CODE", "SECURITY"))
    args = parser.parse_args(argv)
    runtime = LiveProviderObservation(args.repo, args.delivery_issue, args.pr)
    try:
        if args.command == "inspect":
            eligible = provider_fallback.classify(
                runtime.observe(), args.review_type,
                datetime.now(timezone.utc),
            )
            result = {
                "status": "REPLACEMENT_DISPATCH_ELIGIBLE",
                "repository": eligible.repository,
                "delivery_issue": eligible.delivery_issue,
                "pull_request": eligible.pull_request,
                "head_sha": eligible.head_sha,
                "review_type": eligible.review_type,
                "first_fallback_comment": eligible.first_comment_database_id,
                "replacement_count": eligible.replacement_count,
                "new_lifecycle_review": False,
            }
        else:
            dispatched = provider_fallback.dispatch_once(
                runtime.observe, runtime.write, args.review_type,
                lambda: datetime.now(timezone.utc),
            )
            result = {
                "status": dispatched.status,
                "replacement_comment": dispatched.replacement_comment_database_id,
                "write_attempts": dispatched.write_attempts,
                "new_lifecycle_review": False,
            }
    except Exception as exc:
        reason = runtime.actions.evidence.redact_diagnostic(str(exc))
        print(json.dumps({"status": "BLOCKED", "reason": reason}), file=sys.stderr)
        return 3
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] in {"REPLACEMENT_DISPATCH_ELIGIBLE", "PERSISTED"} else 3


if __name__ == "__main__":
    raise SystemExit(main())
