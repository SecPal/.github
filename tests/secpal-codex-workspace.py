#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
import importlib.util,unittest,copy,tempfile,subprocess,os
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
class PreparationTests(unittest.TestCase):
 def tree(self,tmp):
  root=Path(tmp)/"workspace";root.mkdir()
  subprocess.run(["git","init","--quiet",str(root)],check=True)
  (root/"nested").mkdir()
  (root/"payload").write_text("fixture")
  return root
 def test_clean_tree_keeps_development_ownership(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=self.tree(tmp)
   self.assertEqual(m.prepare_tree(root,source_uid=os.getuid(),source_gid=os.getgid()),0)
 def test_nested_directory_uid_and_gid_must_match_the_source_owner(self):
  for field in [4,5]:
   with self.subTest(field=field),tempfile.TemporaryDirectory() as tmp:
    root=self.tree(tmp);foreign=root/"nested";original=Path.lstat
    def changed(path,*args,**kwargs):
     info=original(path,*args,**kwargs)
     if path==foreign:
      values=list(info);values[field]+=1
      return os.stat_result(values)
     return info
    with patch.object(Path,"lstat",autospec=True,side_effect=changed):
     with self.assertRaises(m.IsolationError):m.prepare_tree(root,source_uid=os.getuid(),source_gid=os.getgid())
 def test_writable_nested_directory_is_rejected_before_grant(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=self.tree(tmp);(root/"nested").chmod(0o777)
   with self.assertRaises(m.IsolationError):m.prepare_tree(root,source_uid=os.getuid(),source_gid=os.getgid())
 def test_internal_credential_named_symlinks_are_rejected_before_grant(self):
  for name in [".env",".npmrc","auth.json",".git-credentials"]:
   with self.subTest(name=name),tempfile.TemporaryDirectory() as tmp:
    root=self.tree(tmp);(root/name).symlink_to("payload")
    with self.assertRaises(m.IsolationError):m.prepare_tree(root,source_uid=os.getuid(),source_gid=os.getgid())

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
