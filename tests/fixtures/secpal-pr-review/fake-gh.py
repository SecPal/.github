#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


arguments = sys.argv[1:]
log_path = os.environ.get("FAKE_GH_LOG")
if log_path:
    with Path(log_path).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(arguments, ensure_ascii=False, separators=(",", ":")) + "\n")

if not arguments or arguments[0] != "api":
    fail(f"fake gh rejected non-api operation: {arguments!r}")
if arguments[1:3] != ["--hostname", "github.com"]:
    fail(f"fake gh rejected unpinned API host: {arguments!r}")

method = "GET"
for index, value in enumerate(arguments):
    if value == "--method" and index + 1 < len(arguments):
        method = arguments[index + 1]
if method != "GET":
    fail(f"fake gh rejected write method: {method}")

fixture_path = os.environ.get("FAKE_GH_FIXTURE")
if not fixture_path:
    fail("FAKE_GH_FIXTURE is required")
fixture = json.loads(Path(fixture_path).read_text(encoding="utf-8"))

if len(arguments) > 3 and arguments[3] == "graphql":
    query = next((value.split("=", 1)[1] for value in arguments if value.startswith("query=")), "")
    if re.search(r"\bmutation\b", query, re.IGNORECASE):
        fail("fake gh rejected GraphQL mutation")
    match = re.search(r"\bquery\s+([A-Za-z0-9_]+)", query)
    if not match:
        fail("fake gh could not identify GraphQL operation")
    operation = match.group(1)
    cursor = "null"
    node_id = None
    for value in arguments:
        if value.startswith("after="):
            cursor = value.split("=", 1)[1]
        if value.startswith("nodeId="):
            node_id = value.split("=", 1)[1]
    operation_responses = fixture.get("graphql", {}).get(operation, {})
    response = operation_responses.get(f"{node_id}:{cursor}") if node_id else None
    if response is None:
        response = operation_responses.get(cursor)
    if response is None:
        fail(f"no fake GraphQL response for {operation} cursor={cursor}")
    if operation == "PullRequestAnchor" and os.environ.get("FAKE_GH_MERGED") == "1":
        pull_request = response["data"]["repository"]["pullRequest"]
        pull_request["state"] = "MERGED"
        pull_request["merged"] = True
        pull_request["isDraft"] = False
        pull_request["mergeable"] = "UNKNOWN"
        pull_request["mergeStateStatus"] = "UNKNOWN"
        pull_request["potentialMergeCommit"] = None
    print(json.dumps(response, ensure_ascii=False, separators=(",", ":")))
    raise SystemExit(0)

endpoint = arguments[-1] if arguments[-1] != method and not arguments[-1].startswith("-") else ""
response = fixture.get("rest", {}).get(endpoint)
if response is None:
    fail(f"no fake REST response for {endpoint}")
print(json.dumps(response, ensure_ascii=False, separators=(",", ":")))
