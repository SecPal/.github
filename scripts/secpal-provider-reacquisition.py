#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Canonical accepted-main provider reacquisition action; no provider selector."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))

from secpal_pr_review import fast_path
from secpal_pr_review import lifecycle_authority as authority
from secpal_pr_review import lifecycle_execution
from secpal_pr_review import lifecycle_publication as publication
from secpal_pr_review import provider_reacquisition


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("inspect", "authorize", "dispatch", "observe"))
    parser.add_argument("--repo", required=True)
    parser.add_argument("--delivery-issue", required=True, type=int)
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    if arguments.operation in {"dispatch", "observe"} and arguments.authorization is None:
        parser.error("dispatch and observe require the exact signed authorization")
    if arguments.operation in {"inspect", "authorize"} and arguments.authorization is not None:
        parser.error("loss admission and issuance do not accept caller authority")
    try:
        if arguments.operation == "inspect":
            loss = provider_reacquisition.authenticate_loss(arguments.repo, arguments.delivery_issue)
            report = {**provider_reacquisition._loss_projection(loss), "proof_digest": loss.proof_digest}
        elif arguments.operation == "authorize":
            report = provider_reacquisition.issue_authorization(arguments.repo, arguments.delivery_issue)
        else:
            document = authority.loads_closed_json(arguments.authorization.read_bytes())
            if document.get("repository") != arguments.repo or document.get("delivery_issue") != arguments.delivery_issue:
                raise fast_path.SecurityBlocker("reacquisition action delivery differs from signed authorization")
            report = (provider_reacquisition.dispatch_next(document)
                if arguments.operation == "dispatch" else provider_reacquisition.authenticate_assessment(document))
        fast_path.atomic_write_json(arguments.output, report)
        print(report.get("status", report.get("classification", report.get("kind"))))
        return 0
    except (OSError, ValueError, fast_path.SecurityBlocker, authority.LifecycleAuthorityError,
            publication.LifecyclePublicationError, lifecycle_execution.LifecycleExecutionError) as exc:
        fast_path.atomic_write_json(arguments.output, {"status": "BLOCKED", "reason": str(exc)})
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
