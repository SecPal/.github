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
 pageInfo { hasNextPage endCursor } nodes { number title body state stateReason repository { nameWithOwner } parent { number repository { nameWithOwner } } subIssues(first: 1) { totalCount } labels(first: 100) { nodes { name } } closedByPullRequestsReferences(first: 100, includeClosedPrs: true) { totalCount nodes { number repository { nameWithOwner } } } } } } }'''
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
    if response.errors:
     raise github.GitHubError("audit discovery data is unreadable")
    connection=(((response.data or {}).get("repository") or {}).get("issues") or {})
    if not ((response.data or {}).get("repository")) or not connection:
     raise github.GitHubError("audit discovery repository or issues connection is unreadable")
    rows.extend(connection.get("nodes") or []); page=connection.get("pageInfo") or {}
    if not page.get("hasNextPage"): break
    cursor=page.get("endCursor")
    if not cursor: raise github.GitHubError("issues pagination has no cursor")
   canonical_repositories={((row.get("repository") or {}).get("nameWithOwner")) for row in rows}
   if rows and (None in canonical_repositories or len(canonical_repositories)!=1):
    raise github.GitHubError("audit discovery repository identity is unreadable")
   canonical_repository=str(next(iter(canonical_repositories))) if rows else repository
   facts=parse([row.get("body") for row in rows])
   closing_by_issue={}
   for row in rows:
    refs=[]
    for pull in ((row.get("closedByPullRequestsReferences") or {}).get("nodes") or []):
     pull_repo=((pull.get("repository") or {}).get("nameWithOwner")); pull_number=pull.get("number")
     if pull_repo and pull_number is not None: refs.append(f"{pull_repo}#{int(pull_number)}")
    closing_by_issue[f"{canonical_repository}#{int(row['number'])}"]=tuple(sorted(refs))
   candidates=[]
   for row,fact in zip(rows,facts):
    labels={str(x.get("name", "")).casefold() for x in ((row.get("labels") or {}).get("nodes") or [])}
    native=bool(row.get("parent")) or bool(((row.get("subIssues") or {}).get("totalCount") or 0))
    multiple_closing=((row.get("closedByPullRequestsReferences") or {}).get("totalCount") or 0)>1
    legacy_epic="epic" in labels or "[epic]" in str(row.get("title","")).casefold()
    legacy=legacy_epic or bool(fact.relationship_mirrors) or fact.has_status_checklist
    # Native subtrees start at their highest local container.  A descendant can
    # still be a candidate for its own legacy evidence, so identical findings
    # from overlapping snapshots are deduplicated below.  Cross-repository
    # children remain roots here because their parent is outside this listing.
    parent_repo = ((row.get("parent") or {}).get("repository") or {}).get("nameWithOwner")
    native_root = native and (bool(((row.get("subIssues") or {}).get("totalCount") or 0)) and not row.get("parent") or parent_repo not in (None, canonical_repository))
    if native_root or legacy or multiple_closing:
     key=f"{canonical_repository}#{int(row['number'])}"; candidates.append(audit.Candidate(key,"native" if native else "legacy_candidate",fact.has_status_checklist,legacy_epic))
   findings=[]; seen_findings=set()
   for candidate in sorted(candidates,key=lambda x:x.key):
    snapshot,root=github.load_snapshot(adapter,candidate.key)
    for finding in audit.classify(snapshot,root,candidate,repository=canonical_repository,closing_pull_requests_by_issue=closing_by_issue):
     identity=json.dumps(finding,sort_keys=True,separators=(",",":"))
     if identity not in seen_findings:
      seen_findings.add(identity); findings.append(finding)
   results.append({"repository":canonical_repository,"status":"findings" if findings else "clean","findings":findings})
  except (github.GitHubError, MarkdownParserUnavailable) as error:
   failed=True; results.append({"repository":repository,"status":"unavailable","findings":[],"error":str(error)})
 print(json.dumps(audit.document(results),sort_keys=True,indent=2))
 return 3 if failed else 0
if __name__ == "__main__": raise SystemExit(main())
