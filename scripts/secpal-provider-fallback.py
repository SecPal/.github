#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Inspect or dispatch one same-assessment provider fallback replacement."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.secpal_pr_review import provider_fallback


LiveProviderObservation = provider_fallback.LiveProviderObservation


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
            key = provider_fallback.inspect(runtime, args.review_type).dispatch_key
            result = {
                "status": "REPLACEMENT_DISPATCH_ELIGIBLE",
                "repository": key.repository,
                "delivery_issue": key.delivery_issue,
                "pull_request": key.pull_request,
                "head_sha": key.current_head_sha,
                "review_type": key.review_type,
                "first_fallback_comment": key.original_fallback_comment_database_id,
                "dispatch_claim_id": provider_fallback.publication.provider_dispatch_claim_id(key),
                "protected_claim_available": True,
                "replacement_count": 0,
                "new_lifecycle_review": False,
            }
        else:
            dispatched = provider_fallback.dispatch(args.repo, args.delivery_issue, args.pr, args.review_type)
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
    return 0 if result["status"] in {"REPLACEMENT_DISPATCH_ELIGIBLE", "DISPATCH_PERSISTED", "REPLACEMENT_NO_LONGER_REQUIRED"} else 3


if __name__ == "__main__":
    raise SystemExit(main())
