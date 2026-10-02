#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Publish one authenticated post-Ready review on lifecycle CURRENT."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.secpal_pr_review import lifecycle_execution


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--delivery-issue", required=True, type=int)
    parser.add_argument("--apply", action="store_true")
    arguments = parser.parse_args()
    if not arguments.apply:
        parser.error("--apply is required for protected publication")
    current = lifecycle_execution.publish_review_consumption(
        arguments.repository, arguments.delivery_issue
    )
    print(json.dumps({
        "publication_oid": current.publication_oid,
        "authority_digest": current.lifecycle.authority_digest,
        "review_count": current.lifecycle.state["unrestricted_review_count"],
        "head_sha": current.lifecycle.head_sha,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
