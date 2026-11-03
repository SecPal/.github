#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
import importlib.util,unittest,sys,copy,tempfile,subprocess
from unittest.mock import patch
from types import SimpleNamespace
from pathlib import Path
spec=importlib.util.spec_from_file_location("launcher",Path(__file__).resolve().parents[1]/"scripts/secpal-codex-workspace.py")
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class AttestationTests(unittest.TestCase):
 def setUp(self):
  self.proof=dict(version=1,repo="SecPal/api",repo_id="repo",issue=2639,workspace_id="root",path="/native/root",branch="topic",head="a"*40,filesystem={"device":1,"inode":2,"uid":1003,"gid":1003},members=[dict(id="root",repo_id="repo",path="/native/root",linked_from_worktree_id=None,linked_worktree_ids=["a","b","c"]),*[dict(id=i,repo_id=i,path="/native/"+i,linked_from_worktree_id="root",linked_worktree_ids=[x for x in ["root","a","b","c"] if x!=i]) for i in ["a","b","c"]]])
 def test_exact_identity_and_development_head(self):
  q=copy.deepcopy(self.proof);q["head"]="b"*40
  m.check_attestation(q,self.proof)
 def test_same_native_path_with_replaced_root_inode_is_rejected(self):
  q=copy.deepcopy(self.proof)
  q["filesystem"]["inode"]+=1
  with self.assertRaises(m.IsolationError):m.check_attestation(q,self.proof)
 def test_wrong_issue_repo_path_workspace_group_and_branch(self):
  for key,val in [("issue",1383),("repo","SecPal/frontend"),("path","/else"),("workspace_id","foreign"),("branch","main")]:
   q=copy.deepcopy(self.proof);q[key]=val
   with self.assertRaises(m.IsolationError):m.check_attestation(q,self.proof)
  q=copy.deepcopy(self.proof);q["members"].pop()
  with self.assertRaises(m.IsolationError):m.check_attestation(q,self.proof)
class InterruptedCreationTests(unittest.TestCase):
 def test_interruption_inside_network_creation_still_removes_resource_intent(self):
  with tempfile.TemporaryDirectory() as tmp:
   private=Path(tmp)/"credentials";private.mkdir()
   launcher=m.Launcher()
   launcher.authorize=lambda:({"postgres_image":"fixture"},Path(tmp))
   calls=[]
   def podman(receipt,args,**kwargs):
    calls.append(args)
    if args[:2]==["network","create"]:raise InterruptedError("fixture interruption after creation")
    return SimpleNamespace(returncode=0,stdout="")
   launcher.podman=podman
   with patch.object(m.tempfile,"mkdtemp",return_value=str(private)):
    with self.assertRaises(InterruptedError):launcher._test(["true"])
   self.assertTrue(any(c[:2]==["network","exists"] for c in calls))
   self.assertTrue(any(c[:2]==["network","rm"] for c in calls))
   self.assertFalse(private.exists())
 def test_cleanup_failure_does_not_preserve_test_credentials(self):
  with tempfile.TemporaryDirectory() as tmp:
   private=Path(tmp)/"credentials";private.mkdir()
   launcher=m.Launcher()
   launcher.authorize=lambda:({"postgres_image":"fixture"},Path(tmp))
   def podman(receipt,args,**kwargs):
    if args[:2]==["volume","create"]:raise InterruptedError("fixture")
    if args[:2]==["network","rm"]:raise subprocess.CalledProcessError(1,["podman"])
    return SimpleNamespace(returncode=0,stdout="")
   launcher.podman=podman
   with patch.object(m.tempfile,"mkdtemp",return_value=str(private)):
    with self.assertRaises((OSError,subprocess.SubprocessError,m.IsolationError)):launcher._test(["true"])
   self.assertFalse(private.exists())

if __name__=="__main__":unittest.main()
