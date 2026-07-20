#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path


arguments = sys.argv[1:]
log_path = os.environ.get("FAKE_ACTION_GH_LOG")
if log_path:
    with Path(log_path).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(arguments, separators=(",", ":")) + "\n")

if arguments[:3] != ["api", "--hostname", "github.com"]:
    raise SystemExit("fake action gh requires a pinned api invocation")

if arguments[3] == "graphql":
    query = next((value.split("=", 1)[1] for value in arguments if value.startswith("query=")), "")
    if "query ViewerIdentity" in query:
        print(
            json.dumps(
                {"data": {"viewer": {"login": "aroviqen", "id": "USER_1", "databaseId": 7}}},
                separators=(",", ":"),
            )
        )
        raise SystemExit(0)
    if "query CurrentMutationTarget" in query:
        print(
            json.dumps(
                {
                    "data": {
                        "viewer": {"login": "aroviqen", "id": "USER_1", "databaseId": 7},
                        "repository": {"pullRequest": {"headRefOid": "a" * 40, "state": "OPEN"}},
                        "node": {
                            "__typename": "PullRequestReviewComment",
                            "id": "RC_1",
                            "databaseId": 21,
                            "body": "Finding",
                            "url": "https://github.com/SecPal/.github/pull/1#discussion_r1",
                            "replyTo": None,
                            "author": {"login": "reviewer", "id": "ACTOR_reviewer", "databaseId": 7},
                            "pullRequestReviewThread": {"id": "THREAD_1", "isResolved": False, "isOutdated": False},
                            "reactions": {"nodes": [], "pageInfo": {"hasNextPage": False}},
                        },
                        "thread": {
                            "id": "THREAD_1",
                            "isResolved": False,
                            "isOutdated": False,
                            "comments": {
                                "nodes": [
                                    {
                                        "id": "RC_1",
                                        "databaseId": 21,
                                        "body": "Finding",
                                        "url": "https://github.com/SecPal/.github/pull/1#discussion_r1",
                                        "replyTo": None,
                                        "author": {
                                            "login": "reviewer",
                                            "id": "ACTOR_reviewer",
                                            "databaseId": 7,
                                        },
                                        "reactions": {
                                            "nodes": [],
                                            "pageInfo": {"hasNextPage": False},
                                        },
                                    }
                                ],
                                "pageInfo": {"hasNextPage": False},
                            },
                        },
                    }
                },
                separators=(",", ":"),
            )
        )
        raise SystemExit(0)
    if "query CurrentReviewFeedback" in query:
        empty = {"nodes": [], "pageInfo": {"hasNextPage": False}}
        print(
            json.dumps(
                {
                    "data": {
                        "repository": {
                            "pullRequest": {
                                "headRefOid": "a" * 40,
                                "state": "OPEN",
                                "reactions": empty,
                                "reviews": empty,
                                "comments": empty,
                                "reviewThreads": {
                                    "nodes": [
                                        {
                                            "id": "THREAD_1",
                                            "isResolved": False,
                                            "isOutdated": False,
                                            "comments": {
                                                "nodes": [
                                                    {
                                                        "id": "RC_1",
                                                        "body": "Finding",
                                                        "author": {
                                                            "login": "reviewer",
                                                            "id": "ACTOR_reviewer",
                                                            "databaseId": 7,
                                                        },
                                                        "reactions": empty,
                                                    }
                                                ],
                                                "pageInfo": {"hasNextPage": False},
                                            },
                                        }
                                    ],
                                    "pageInfo": {"hasNextPage": False},
                                },
                            }
                        }
                    }
                },
                separators=(",", ":"),
            )
        )
        raise SystemExit(0)
    if re.search(r"\bmutation\b", query):
        raise SystemExit("unexpected GraphQL mutation in reaction integration fixture")
    raise SystemExit("unknown fake GraphQL query")

method = arguments[arguments.index("--method") + 1] if "--method" in arguments else "GET"
endpoint = arguments[3]
if method == "POST" and endpoint == "repos/SecPal/.github/pulls/comments/21/reactions":
    print(json.dumps({"id": 99, "node_id": "REACTION_NEW", "content": "+1"}, separators=(",", ":")))
    raise SystemExit(0)
raise SystemExit(f"unexpected fake action endpoint: {method} {endpoint}")
