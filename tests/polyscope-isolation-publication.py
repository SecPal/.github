#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
"""Administrative publication regression; use a disposable root-owned directory."""
import importlib.util,os,tempfile,unittest,hashlib
from types import SimpleNamespace
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch,Mock
spec=importlib.util.spec_from_file_location("publication",Path(__file__).resolve().parents[1]/"scripts/polyscope-isolation.py")
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

@unittest.skipUnless(os.geteuid()==0,"requires isolated administrative fixture")
class Publication(unittest.TestCase):
 def setUp(self):
  base=Path(os.environ["SECPAL_PUBLICATION_TEST_ROOT"])
  self.temp=tempfile.TemporaryDirectory(dir=base)
  self.addCleanup(self.temp.cleanup)
  self.path=Path(self.temp.name)/"authority.json"
 def test_published_file_is_complete_and_exclusive(self):
  data={"version":1,"payload":"fixture"*10000}
  m.publish_policy(self.path,data)
  self.assertEqual(m.load_policy(self.path),data)
  with self.assertRaises(FileExistsError):m.publish_policy(self.path,{"other":True})
  self.assertEqual(m.load_policy(self.path),data)
  self.assertEqual(list(self.path.parent.iterdir()),[self.path])
 def test_interruption_before_publish_leaves_no_authority_or_temporary_file(self):
  with patch.object(os,"fsync",side_effect=OSError("fixture-interruption")):
   with self.assertRaises(OSError):m.publish_policy(self.path,{"version":1})
  self.assertFalse(self.path.exists())
  self.assertEqual(list(self.path.parent.iterdir()),[])
@unittest.skipUnless(os.geteuid()==0,"requires isolated administrative fixture")
class Arming(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(dir=Path(os.environ["SECPAL_PUBLICATION_TEST_ROOT"]))
  self.addCleanup(self.temp.cleanup)
  self.root=Path(self.temp.name);self.path=self.root/"authority.json";self.marker=self.root/"authority.required"
  self.lock=self.root/"configured.lock";self.lock.write_text("");self.lock.chmod(0o600);os.chown(self.lock,1003,1003)
  self.binary=self.root/"server";self.binary.write_bytes(b"qualified fixture")
  self.owner=SimpleNamespace(LOCK_PATH=self.lock,CLONE_ROOT=self.root/"configured-clones",configure_paths=Mock())
  records=[dict(id="api",name="SecPal/api",linked_repo_ids=[],workspaces=[])]
  stack=ExitStack();self.addCleanup(stack.close)
  stack.enter_context(patch.object(m,"coordinator",return_value=self.owner))
  stack.enter_context(patch.object(m,"snapshot",return_value=records))
  stack.enter_context(patch.object(m,"QUALIFIED_SERVER_SHA256",hashlib.sha256(self.binary.read_bytes()).hexdigest()))
  stack.enter_context(patch.object(m,"REQUIRED_MARKER_PATH",self.marker,create=True))
  stack.enter_context(patch.object(m,"DEFAULT_POLICY_PATH",self.path,create=True))
  original=os.open
  self.opened=[]
  def scoped_open(path,*args,**kwargs):
   self.opened.append(str(path))
   # Old code must not touch the real service's default creation lock.
   if str(path)=="/home/secpal/.local/state/polyscope/workspace-create.lock":path=self.lock
   return original(path,*args,**kwargs)
  stack.enter_context(patch.object(m.os,"open",side_effect=scoped_open))
 def test_configured_paths_and_marker_precede_authority(self):
  published=[];original=m.publish_policy
  def publish(path,data):
   published.append(Path(path));return original(path,data)
  with patch.object(m,"publish_policy",side_effect=publish):
   m.arm(self.path,"gpt-5.3-codex",str(self.binary))
  self.owner.configure_paths.assert_called_once_with(1003)
  self.assertEqual(m.load_policy(self.path)["clone_root"],str(self.owner.CLONE_ROOT))
  self.assertIn(str(self.lock),self.opened)
  self.assertNotIn("/home/secpal/.local/state/polyscope/workspace-create.lock",self.opened)
  self.assertEqual(published,[self.marker,self.path])
 def test_interrupted_authority_publication_retains_fail_closed_marker(self):
  original=m.publish_policy
  def publish(path,data):
   if Path(path)==self.path:raise OSError("fixture interruption")
   return original(path,data)
  with patch.object(m,"publish_policy",side_effect=publish):
   with self.assertRaises(OSError):m.arm(self.path,"gpt-5.3-codex",str(self.binary))
  self.assertTrue(self.marker.is_file());self.assertFalse(self.path.exists())
  with patch.dict(os.environ,{},clear=True):
   with self.assertRaises(FileNotFoundError):m.from_environment()
 def test_untrusted_existing_marker_cannot_publish_authority(self):
  self.marker.write_text("fixture");os.chown(self.marker,1003,1003)
  with self.assertRaises(m.IsolationError):m.arm(self.path,"gpt-5.3-codex",str(self.binary))
  self.assertFalse(self.path.exists())

if __name__=="__main__":unittest.main()
