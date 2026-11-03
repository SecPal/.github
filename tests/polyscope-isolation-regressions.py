#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
"""Controller boundary regressions; native registration is tested separately."""
import importlib.util,sys,tempfile,unittest,copy,subprocess,os,json,hashlib,base64,shlex
from pathlib import Path
from unittest.mock import Mock,patch
root=Path(__file__).resolve().parents[1]
def load(name,file):
 s=importlib.util.spec_from_file_location(name,root/'scripts'/file)
 m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
iso=load('iso_reg','polyscope-isolation.py')
class ReconcileTests(unittest.TestCase):
 def test_quarantine_precedes_all_bootstrap_and_preserves_runtime_ids(self):
  m=load('rollout_reg','polyscope-rollout.py')
  with tempfile.TemporaryDirectory() as tmp:
   clone=Path(tmp)/'clones';target=clone/'api'/'new';target.mkdir(parents=True)
   ordinary=clone/'api'/'old';ordinary.mkdir()
   m.isolation_state=lambda:({},[],False)
   m.isolation_path_blocked=lambda p:p==target
   m.load_registered_worktree_paths=lambda *a,**k:{'api':[target,ordinary]}
   m.should_manage_api_runtime_units=lambda *a:True
   m.is_workspace_automation_enabled=lambda spec:True
   m.revoke_unregistered_preview_nginx_access=lambda *a:None
   m.is_provisionable_worktree=Mock(return_value=False)
   m.cleanup_removed_workspace_aliases=lambda *a:[]
   m.cleanup_removed_api_preview_databases=Mock(side_effect=AssertionError('GC ran'))
   m.ensure_api_runtime_owner=Mock(side_effect=AssertionError('worker start'))
   m.run_setup_commands=Mock(side_effect=AssertionError('setup ran'))
   m.reconcile_api_runtime_units=Mock()
   m.deny_preview_nginx_access=Mock()
   m.provision_worktrees({'api':{'id':'api'}},{'api':{'path':Path(tmp),'_native_setup_commands':['false']}},clone)
   self.assertEqual(m.is_provisionable_worktree.call_count,1)
   self.assertEqual(m.is_provisionable_worktree.call_args.args[1],ordinary)
   m.cleanup_removed_api_preview_databases.assert_not_called()
   m.deny_preview_nginx_access.assert_called_once_with(clone,target)
   m.ensure_api_runtime_owner.assert_not_called()
   m.run_setup_commands.assert_not_called()
   self.assertIn(m.build_api_runtime_id(target),m.reconcile_api_runtime_units.call_args.kwargs['preserve_runtime_ids'])
 def test_wrapping_does_not_change_existing_setup_hash_inputs(self):
  m=load('rollout_hash','polyscope-rollout.py')
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp);(path/'package.json').write_text('{"scripts":{}}')
   commands=['npm ci'];config={'scripts':{'setup':commands,'run':['npm run dev']}}
   m.resolve_current_workspace_name=lambda *a,**k:'ordinary'
   before=m.build_setup_hash(path,commands,linked_context={})
   wrapped=iso.wrap_config(config,'/etc/secpal/workspace-isolation.json')
   self.assertEqual(config['scripts']['setup'],commands)
   self.assertNotEqual(wrapped['scripts']['setup'],commands)
   self.assertEqual(before,m.build_setup_hash(path,commands,linked_context={}))
 def test_sync_cannot_unwrap_hooks_when_default_policy_is_armed(self):
  m=load('rollout_default_authority','polyscope-rollout.py')
  specs={'api':{'path':Path('/fixture/api'),'local_config':{'scripts':{'setup':['echo never-unwrapped']}}}}
  m._isolation_context=({},[],False)
  m.validate_preview_backend=lambda args:False
  m.build_repo_specs=lambda root:specs
  m.validate_repo_instruction_files=lambda *a:None
  m.validate_repo_local_configs=lambda *a:None
  class Captured(Exception):pass
  captured=[]
  def write(values):
   captured.append({'api':{'local_config':m.render_local_config(values['api'])}})
   raise Captured()
  m.require_repo_instruction_files=lambda spec:None
  m.instruction_reference=lambda spec:'AGENTS.md'
  m.write_local_configs=write
  from types import SimpleNamespace
  args=SimpleNamespace(workspace_root=Path('/fixture'),skip_local_configs=False)
  with patch.dict(os.environ,{},clear=True):
   with self.assertRaises(Captured):m.run_rollout(args)
  setup=captured[0]['api']['local_config']['scripts']['setup']
  self.assertEqual(len(setup),1)
  self.assertIn('--command-base64',setup[0])
  self.assertIn('/etc/secpal/workspace-isolation.json',setup[0])
 def test_snapshot_late_path_fails_closed_without_holding_create_lock(self):
  m=load('rollout_late','polyscope-rollout.py')
  row=dict(id='old',repo_id='api',path='/fixture/api/old',status='active',issue_number=1383,linked_worktree_ids=[],linked_from_worktree_id=None,is_repo_workspace=False)
  records=[dict(id='api',name='SecPal/api',linked_repo_ids=[],workspaces=[row])]
  policy=iso.reservation(records,'SecPal/api',2639,'/fixture')
  m._isolation_context=policy,records,False
  self.assertFalse(m.isolation_path_blocked('/fixture/api/old'))
  self.assertTrue(m.isolation_path_blocked('/fixture/api/late'))
class CreateScopeTests(unittest.TestCase):
 def test_target_rejects_valid_reservation_for_another_task_before_dispatch(self):
  from types import SimpleNamespace
  m=load('coordinator_scope','secpal-polyscope-workspace.py')
  original_spec=importlib.util.spec_from_file_location
  for repo_id,issue in [('api',2640),('foreign',2639)]:
   policy={'repo_id':repo_id,'issue':issue,'repo':'SecPal/api','model':'gpt-5.3-codex'}
   def trusted_fixture_spec(name,path):
    spec=original_spec(name,path)
    execute=spec.loader.exec_module
    def execute_fixture(module):
     execute(module)
     module.load_policy=lambda path:policy
     module.validate_policy=lambda *args:None
     module.snapshot=lambda *args:[]
    spec.loader.exec_module=execute_fixture
    return spec
   with patch.dict(os.environ,{'SECPAL_WORKSPACE_ISOLATION_POLICY':'/trusted-fixture'}), \
     patch.object(importlib.util,'spec_from_file_location',side_effect=trusted_fixture_spec), \
     patch.object(m.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='{"id":"unexpected"}')) as dispatch:
    with self.assertRaisesRegex(RuntimeError,'isolated-create-policy-scope'):
     m.create_native({'id':'api','name':'SecPal/api','github_assign_self_enabled':False},
      {'number':2639,'title':'unit','url':'https://github.com/SecPal/api/issues/2639','body':''},2639,None,None,[])
    dispatch.assert_not_called()


class NativeExecutableTests(unittest.TestCase):
 def test_native_create_uses_the_reservations_configured_executable(self):
  from types import SimpleNamespace
  m=load('native_executable','secpal-polyscope-workspace.py')
  with tempfile.TemporaryDirectory() as tmp:
   binary=Path(tmp)/'server';binary.write_bytes(b'qualified fixture')
   digest=hashlib.sha256(binary.read_bytes()).hexdigest()
   policy={'repo_id':'api','issue':2639,'repo':'SecPal/api','model':'gpt-5.3-codex','server_bin':str(binary),'server_sha256':digest}
   original_spec=importlib.util.spec_from_file_location
   def fixture_spec(name,path):
    spec=original_spec(name,path);execute=spec.loader.exec_module
    def execute_fixture(module):
     execute(module);module.load_policy=lambda path:policy
     module.validate_policy=lambda *args:None;module.snapshot=lambda *args:[]
     module.QUALIFIED_SERVER_SHA256=digest
    spec.loader.exec_module=execute_fixture
    return spec
   with patch.dict(os.environ,{'SECPAL_WORKSPACE_ISOLATION_POLICY':'/trusted-fixture'}),patch.object(importlib.util,'spec_from_file_location',side_effect=fixture_spec),patch.object(m.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='{"id":"native-fixture"}')) as dispatch:
    result=m.create_native({'id':'api','name':'SecPal/api','github_assign_self_enabled':False},{'number':2639,'title':'unit','url':'https://github.com/SecPal/api/issues/2639','body':''},2639,None,None,[])
    self.assertEqual(result['id'],'native-fixture')
    self.assertEqual(json.loads(dispatch.call_args.kwargs['input'])['message']['model'],'gpt-5.3-codex')

class RenderBoundaryTests(unittest.TestCase):
 def test_final_repo_and_container_actions_are_guarded_after_enrichment(self):
  m=load('final_render','polyscope-rollout.py')
  m._isolation_context=({},[],False)
  m.require_repo_instruction_files=lambda spec:None
  m.instruction_reference=lambda spec:'AGENTS.md'
  m.should_manage_api_runtime_units=lambda *args:True
  spec={'path':Path('/fixture/api'),'local_config':{'scripts':{'setup':['echo setup'],'run':[{'label':'Pest','command':'old'}]}}}
  with patch.dict(os.environ,{},clear=True):
   repo=m.render_local_config(spec)
   tree=json.loads(m.render_worktree_local_config(spec,Path('/fixture/clones/api/new'),container_preview=True))
  for config in [repo,tree]:
   for action in config['scripts']['run']:
    self.assertIn('--command-base64',action['command'])
  pest=next(a for a in tree['scripts']['run'] if a['label']=='Pest')
  self.assertEqual(base64.b64decode(shlex.split(pest['command'])[-1]).decode(),'polyscope-api-test')
  self.assertEqual(spec['local_config']['scripts']['setup'],['echo setup'])
 def test_refresh_only_withdraws_protected_acl_before_rendering(self):
  from types import SimpleNamespace
  m=load('refresh_only_acl','polyscope-rollout.py')
  with tempfile.TemporaryDirectory() as tmp:
   clone=Path(tmp);target=clone/'api'/'protected';target.mkdir(parents=True)
   m.validate_preview_backend=lambda args:False
   m.build_repo_specs=lambda root:{}
   m.validate_repo_instruction_files=lambda *args:set()
   m.validate_repo_local_configs=lambda *args:None
   m.load_repo_state=lambda path:{}
   m.detect_nginx_http2_syntax=lambda:'modern'
   m.isolation_blocked_paths=lambda:{str(target)}
   m.deny_preview_nginx_access=Mock()
   class Captured(Exception):pass
   m.build_preview_workspace_redirects=Mock(side_effect=Captured)
   args=SimpleNamespace(workspace_root=clone,skip_local_configs=True,repo_state_file=clone/'state',skip_db_sync=True,nginx_http2_syntax='modern',install_nginx=False,refresh_nginx=True,clone_root=clone)
   with self.assertRaises(Captured):m.run_rollout(args)
   m.deny_preview_nginx_access.assert_called_once_with(clone,target)
 def test_host_redirects_exclude_protected_members_but_preserve_ordinary_aliases(self):
  m=load('host_routes','polyscope-rollout.py')
  with tempfile.TemporaryDirectory() as tmp:
   clone=Path(tmp);base=clone/'api';base.mkdir()
   for canonical,physical in [('ordinary','ordinary-old'),('protected','protected-new')]:
    (base/physical).mkdir();(base/canonical).symlink_to(physical)
   (base/'.polyscope-secpal-workspace-aliases.json').write_text(json.dumps({'version':1,'aliases':{'ordinary':'ordinary-old','protected':'protected-new'}}))
   m.isolation_path_blocked=lambda path:path.name=='protected-new'
   self.assertEqual(m.build_preview_workspace_redirects({'api':{'id':'api'}},clone),{'api':{'ordinary-old':'ordinary'}})

class ExecutableTests(unittest.TestCase):
 def test_configured_qualified_executable_is_accepted(self):
  with tempfile.TemporaryDirectory() as tmp:
   binary=Path(tmp)/'server';binary.write_bytes(b'qualified fixture')
   digest=hashlib.sha256(binary.read_bytes()).hexdigest()
   with patch.object(iso,'QUALIFIED_SERVER_SHA256',digest),patch.object(iso,'load_policy',return_value={'server_bin':str(binary),'server_sha256':digest}):
    iso.Gate('/authority',owner=Mock())
 def test_replacement_retaining_mtime_cannot_reuse_a_qualified_digest(self):
  with tempfile.TemporaryDirectory() as tmp:
   binary=Path(tmp)/'server';binary.write_bytes(b'qualified fixture')
   digest=hashlib.sha256(binary.read_bytes()).hexdigest();before=binary.stat()
   real_path=Path
   def fixture_path(value):
    return binary if str(value)=='/opt/secpal/tools/bin/polyscope-server' else real_path(value)
   clear=getattr(iso.server_digest,'cache_clear',lambda:None);clear()
   try:
    with patch.object(iso,'Path',side_effect=fixture_path),patch.object(iso,'QUALIFIED_SERVER_SHA256',digest),patch.object(iso,'load_policy',return_value={'server_bin':str(binary),'server_sha256':digest}):
     iso.Gate('/authority',owner=Mock())
     replacement=real_path(tmp)/'replacement';replacement.write_bytes(b'unqualified fixture')
     os.utime(replacement,ns=(before.st_atime_ns,before.st_mtime_ns));os.replace(replacement,binary)
     with self.assertRaises(iso.IsolationError):iso.Gate('/authority',owner=Mock())
   finally:clear()
 def test_extensionless_installed_coordinator_remains_the_mapping_owner(self):
  with tempfile.TemporaryDirectory() as tmp:
   directory=Path(tmp);installed=directory/'secpal-polyscope-workspace'
   installed.write_bytes((root/'scripts/secpal-polyscope-workspace.py').read_bytes())
   iso.coordinator.cache_clear()
   try:
    with patch.object(iso,'__file__',str(directory/'polyscope-isolation.py')),patch.object(iso,'COORDINATOR_PATH',installed,create=True):
     self.assertTrue(callable(iso.coordinator().admit_native_group))
   finally:iso.coordinator.cache_clear()

class StandaloneTests(unittest.TestCase):
 def test_missing_helper_allowed_only_when_no_isolation_authority_is_armed(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/"polyscope-rollout.py"
   path.write_bytes((root/"scripts/polyscope-rollout.py").read_bytes())
   code="import importlib.util,sys;s=importlib.util.spec_from_file_location('standalone',sys.argv[1]);m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m);assert m.isolation_state() is None"
   env={k:v for k,v in os.environ.items() if k!="SECPAL_WORKSPACE_ISOLATION_POLICY"}
   p=subprocess.run([sys.executable,"-c",code,str(path)],env=env,capture_output=True)
   self.assertEqual(p.returncode,0,p.stderr)
   env["SECPAL_WORKSPACE_ISOLATION_POLICY"]="/missing/required-policy"
   p=subprocess.run([sys.executable,"-c",code,str(path)],env=env,capture_output=True)
   self.assertNotEqual(p.returncode,0)
if __name__=='__main__':unittest.main()
