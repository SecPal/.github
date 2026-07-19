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

if len(arguments) > 1 and arguments[1] == "graphql":
    query = next((value.split("=", 1)[1] for value in arguments if value.startswith("query=")), "")
    if re.search(r"\bmutation\b", query, re.IGNORECASE):
        fail("fake gh rejected GraphQL mutation")
    match = re.search(r"\bquery\s+([A-Za-z0-9_]+)", query)
    if not match:
        fail("fake gh could not identify GraphQL operation")
    operation = match.group(1)
    cursor = "null"
    for value in arguments:
        if value.startswith("after="):
            cursor = value.split("=", 1)[1]
    response = fixture.get("graphql", {}).get(operation, {}).get(cursor)
    if response is None:
        fail(f"no fake GraphQL response for {operation} cursor={cursor}")
    print(json.dumps(response, ensure_ascii=False, separators=(",", ":")))
    raise SystemExit(0)

endpoint = next(
    (
        value
        for value in reversed(arguments[1:])
        if not value.startswith("-") and "=" not in value and value != method
    ),
    "",
)
response = fixture.get("rest", {}).get(endpoint)
if response is None:
    fail(f"no fake REST response for {endpoint}")
print(json.dumps(response, ensure_ascii=False, separators=(",", ":")))
