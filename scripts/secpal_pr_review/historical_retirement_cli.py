# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Exact accepted-main retirement boundary; no successor/review capability."""

import argparse
from pathlib import Path
import sys

from . import fast_path, historical_retirement as retirement
from . import late_disposition, lifecycle_authority as authority


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("inspect", "authorize", "retire", "reconcile"))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--authorization-id")
    parser.add_argument("--exact-human-intent", choices=(retirement.INTENT,))
    parser.add_argument("--claim-oid")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.operation == "authorize" and (not args.authorization_id or not args.exact_human_intent):
        parser.error("authorize requires a separate exact human intent and authorization ID")
    if args.operation in {"retire", "reconcile"} and args.authorization is None:
        parser.error("retire/reconcile require the exact signed authorization")
    if args.operation == "retire" and not args.apply:
        parser.error("retire requires explicit --apply")
    if args.operation != "retire" and args.apply:
        parser.error("only retire permits --apply")
    if args.operation == "reconcile" and not args.claim_oid:
        parser.error("reconcile requires the exact attempted claim OID")
    try:
        if args.operation in {"inspect", "authorize"}:
            if args.authorization is not None or args.claim_oid is not None:
                parser.error("qualification/issuance accept no caller evidence")
            case = retirement.authenticate_case()
            report = retirement.issue_authorization(case, authorization_id=args.authorization_id) if args.operation == "authorize" else {"status": "QUALIFIED_RETIREMENT_REQUIRES_SEPARATE_AUTHORITY", "proof": case.proof, "successor": retirement.successor_eligibility(case.proof["facts"])}
        else:
            raw = late_disposition._read_bounded_regular_file(args.authorization, "retirement authorization", retirement.MAXIMUM_BYTES)
            document = authority.loads_closed_json(raw)
            report = retirement.retire(document) if args.operation == "retire" else retirement.reconcile(document, args.claim_oid)
        fast_path.atomic_write_json(args.output, report)
        print(report.get("status", report.get("kind")))
        return 0
    except (OSError, ValueError, RuntimeError, fast_path.SecurityBlocker) as exc:
        report = {"status": "BLOCKED", "reason": str(exc)}
        if isinstance(exc, retirement.RetirementAttemptStopped):
            report.update(claim_oid=exc.claim_oid, status="RETIREMENT_ATTEMPT_CONSUMED_OBSERVATION_ONLY", stage=exc.stage)
        fast_path.atomic_write_json(args.output, report)
        print(report["status"], file=sys.stderr)
        return 1
