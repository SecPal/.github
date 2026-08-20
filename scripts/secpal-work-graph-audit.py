#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Read-only advisory audit entrypoint; it never mutates GitHub.

Discovery is deliberately narrow: native containment participants and legacy
epic, relationship-mirror, or task-list signals.  Legacy signals select audit
candidates only; they are never turned into native graph edges.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from secpal_work_graph import audit, github
from secpal_work_graph.acceptance_criteria import MarkdownParserUnavailable, parse

QUERY = '''query WorkGraphAuditIssues($owner: String!, $name: String!, $cursor: String) {
 repository(owner: $owner, name: $name) { issues(first: 100, after: $cursor, states: [OPEN, CLOSED], orderBy: {field: UPDATED_AT, direction: DESC}) {
 pageInfo { hasNextPage endCursor } nodes { number title body state stateReason repository { nameWithOwner } parent { number repository { nameWithOwner } } subIssues(first: 1) { totalCount } labels(first: 100) { nodes { name } } } } } }'''
def main(argv=None):
 p=argparse.ArgumentParser(prog="secpal-work-graph-audit")
 p.add_argument("--repo", action="append", dest="repos")
 p.add_argument("--gh", default="gh"); p.add_argument("--timeout", type=float, default=30)
 args=p.parse_args(argv); repos=tuple(args.repos or audit.DEFAULT_REPOSITORIES)
 if any("/" not in repo for repo in repos): return 2
 adapter=github.GitHubReadAdapter(gh_executable=args.gh, timeout=args.timeout)
 results=[]; failed=False
 for repository in repos:
  try:
   owner,name=repository.split("/",1); cursor=None; rows=[]
   while True:
    response=adapter.query(QUERY,{"owner":owner,"name":name,"cursor":cursor})
    connection=(((response.data or {}).get("repository") or {}).get("issues") or {})
    rows.extend(connection.get("nodes") or []); page=connection.get("pageInfo") or {}
    if not page.get("hasNextPage"): break
    cursor=page.get("endCursor")
    if not cursor: raise github.GitHubError("issues pagination has no cursor")
   facts=parse([row.get("body") for row in rows])
   candidates=[]
   for row,fact in zip(rows,facts):
    labels={str(x.get("name", "")).casefold() for x in ((row.get("labels") or {}).get("nodes") or [])}
    native=bool(row.get("parent")) or bool(((row.get("subIssues") or {}).get("totalCount") or 0))
    legacy_epic="epic" in labels or "[epic]" in str(row.get("title","")).casefold()
    legacy=legacy_epic or bool(fact.relationship_mirrors) or fact.has_status_checklist
    # A native subtree is resolved once from its highest local container.  Its
    # descendants are classified from that canonical resolver result, avoiding
    # repeated overlapping graph reads.  Cross-repository children remain roots
    # in this repository result because their parent is outside this listing.
    parent_repo = ((row.get("parent") or {}).get("repository") or {}).get("nameWithOwner")
    native_root = native and (bool(((row.get("subIssues") or {}).get("totalCount") or 0)) and not row.get("parent") or parent_repo not in (None, repository))
    if native_root or legacy:
     key=f"{repository}#{int(row['number'])}"; candidates.append(audit.Candidate(key,"native" if native else "legacy_candidate",fact.has_status_checklist,legacy_epic))
   findings=[]
   for candidate in sorted(candidates,key=lambda x:x.key):
    snapshot,root=github.load_snapshot(adapter,candidate.key)
    findings.extend(audit.classify(snapshot,root,candidate,repository=repository))
   results.append({"repository":repository,"status":"findings" if findings else "clean","findings":findings})
  except (github.GitHubError, MarkdownParserUnavailable) as error:
   failed=True; results.append({"repository":repository,"status":"unavailable","findings":[],"error":str(error)})
 print(json.dumps(audit.document(results),sort_keys=True,indent=2))
 return 3 if failed else 0
if __name__ == "__main__": raise SystemExit(main())
