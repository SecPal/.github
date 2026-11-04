#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
import importlib.util,sys,unittest,copy
from pathlib import Path
spec=importlib.util.spec_from_file_location("isolation",Path(__file__).resolve().parents[1]/"scripts/polyscope-isolation.py")
iso=importlib.util.module_from_spec(spec);sys.modules[spec.name]=iso;spec.loader.exec_module(iso)
def row(id,repo,issue=None,links=None,parent=None):
 return dict(id=id,repo_id=repo,path="/fixture/clones/"+repo+"/"+id,status="active",issue_number=issue,pr_number=None,is_repo_workspace=False,linked_worktree_ids=links or [],linked_from_worktree_id=parent)
def records():
 return [dict(id="api",name="SecPal/api",linked_repo_ids=["web","mobile","contracts"],workspaces=[row("old","api",1383)]),dict(id="web",name="SecPal/frontend",linked_repo_ids=[],workspaces=[]),dict(id="mobile",name="SecPal/android",linked_repo_ids=[],workspaces=[]),dict(id="contracts",name="SecPal/contracts",linked_repo_ids=[],workspaces=[])]
class GuardTests(unittest.TestCase):
 def setUp(self):
  self.before=records();self.policy=iso.reservation(self.before,"SecPal/api",2639,"/fixture/clones")
 def test_prior_workspace_continues(self):
  self.assertFalse(iso.classify(self.policy,self.before,"/fixture/clones/api/old"))
 def test_partial_group_and_interruption_are_quarantined(self):
  s=copy.deepcopy(self.before);s[0]["workspaces"].append(row("new","api",2639))
  s[1]["workspaces"].append(row("partial","web"))
  self.assertTrue(iso.classify(self.policy,s,"/fixture/clones/api/new"))
  self.assertTrue(iso.classify(self.policy,s,"/fixture/clones/web/partial"))
  self.assertTrue(iso.classify(self.policy,s,"/fixture/clones/web/partial",pending=True))
 def test_complete_group_is_quarantined(self):
  s=copy.deepcopy(self.before);ids=["new","a","b","c"]
  for n,repo in enumerate(s):
   repo["workspaces"].append(row(ids[n],repo["id"],2639 if n==0 else None,[i for i in ids if i!=ids[n]],None if n==0 else "new"))
  for n,repo in enumerate(s):self.assertTrue(iso.classify(self.policy,s,"/fixture/clones/"+repo["id"]+"/"+ids[n]))
 def test_later_independent_bound_group_recovers_after_fence(self):
  s=copy.deepcopy(self.before);ids=["other","other-a","other-b","other-c"]
  for n,repo in enumerate(s):
   repo["workspaces"].append(row(ids[n],repo["id"],2640 if n==0 else None,[i for i in ids if i!=ids[n]],None if n==0 else "other"))
  for n,repo in enumerate(s):
   path="/fixture/clones/"+repo["id"]+"/"+ids[n]
   self.assertTrue(iso.classify(self.policy,s,path,pending=True))
   self.assertFalse(iso.classify(self.policy,s,path,pending=False))
 def test_inconsistent_independent_group_never_gets_permission(self):
  s=copy.deepcopy(self.before);ids=["other","a","b","c"]
  for n,repo in enumerate(s):
   repo["workspaces"].append(row(ids[n],repo["id"],2640 if n==0 else None,[i for i in ids if i!=ids[n]],None if n==0 else "other"))
  s[1]["workspaces"][-1]["linked_from_worktree_id"]="foreign"
  with self.assertRaises(iso.IsolationError):
   iso.classify(self.policy,s,"/fixture/clones/web/a")
 def test_missing_conflicting_and_foreign_data_fail_closed(self):
  with self.assertRaises(iso.IsolationError):iso.classify({},self.before,"/fixture/clones/api/old")
  with self.assertRaises(iso.IsolationError):iso.classify(self.policy,self.before,"/outside")
  s=copy.deepcopy(self.before);s[0]["linked_repo_ids"]=[]
  with self.assertRaises(iso.IsolationError):iso.classify(self.policy,s,"/fixture/clones/api/old")
 def test_reservation_must_precede_task(self):
  s=records();s[0]["workspaces"].append(row("existing-target","api",2639))
  with self.assertRaises(iso.IsolationError):iso.reservation(s,"SecPal/api",2639,"/fixture/clones")
if __name__=="__main__":unittest.main()
