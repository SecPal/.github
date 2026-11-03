#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
"""Administrative publication regression; use a disposable root-owned directory."""
import importlib.util,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
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
if __name__=="__main__":unittest.main()
