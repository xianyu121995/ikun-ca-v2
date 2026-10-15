"""Deployment guard tests only; no real worker, job, API, database or provider access."""
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import secrets
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/night_worker_ops.py'
SPEC = importlib.util.spec_from_file_location('night_worker_ops', SCRIPT)
ops = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ops)


class WorkerPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ikun-night-guard-', dir='/private/tmp')
        self.root = Path(self.temp.name) / 'owned'
        for relative in ('config', 'jobs/tracking', 'logs', 'toolchains/node24/bin'):
            (self.root / relative).mkdir(mode=0o700, parents=True)
        self.release = self.root / 'releases' / ('a' * 40)
        self.entry = self.release / 'services/tracking-worker/dist/main.js'
        self.entry.parent.mkdir(parents=True)
        self.entry.write_text('// synthetic artifact, never executed\n')
        self.exe = self.root / 'toolchains/node24/bin/node'
        self.exe.write_text('synthetic executable, never executed\n')
        self.exe.chmod(0o700)
        for name in ('auth', 'projects', 'hunter', 'tracking'):
            path = self.root / 'data' / name / (name + '.db')
            path.parent.mkdir(mode=0o700, parents=True)
            with sqlite3.connect(path) as database:
                database.execute('PRAGMA user_version=2')
                database.execute('PRAGMA application_id=123')
            path.chmod(0o600)
        self.config = self.root / 'config/tracking.json'
        self.write(self.config, {'db_path': str(self.root / 'data/tracking/tracking.db'), 'remote_enabled': False,
                                 'dedicated_account': False, 'host': '127.0.0.1', 'port': 4012, 'token_file': ''})
        self.env = self.root / 'config/tracking.environment.json'
        self.values = {'DATA_ROOT': str(self.root / 'data'), 'TRACKING_API_TOKEN': secrets.token_urlsafe(32),
                       'IKUN_TRACKING_CONFIG': str(self.config)}
        self.write(self.env, self.values)
        argv = [str(self.exe), str(self.entry)]
        self.receipt = self.root / 'config/tracking.accepted.json'
        self.record = {'worker': 'tracking', 'accepted_frozen': True, 'source_commit': 'b' * 40,
                       'control_commit': 'c' * 40, 'runtime_sha256': {'services/tracking-worker/dist/main.js': ops.sha(self.entry)},
                       'argv': argv, 'executable_sha256': ops.sha(self.exe), 'database_user_version': 2,
                       'database_application_id': 123}
        self.write(self.receipt, self.record)
        self.plan = {'worker': 'tracking', 'accepted_frozen': True, 'source_commit': 'b' * 40,
                     'control_commit': 'c' * 40, 'candidate_sha': 'a' * 40, 'release': str(self.release),
                     'runtime_sha256': self.record['runtime_sha256'], 'argv': argv,
                     'acceptance_file': str(self.receipt), 'acceptance_sha256': ops.sha(self.receipt),
                     'environment_file': str(self.env), 'cwd': str(self.root / 'jobs/tracking')}

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def write(path, data):
        path.write_text(json.dumps(data))
        path.chmod(0o600)

    def check(self):
        return ops.validate(self.plan, self.root)

    def test_accepted_local_plan_does_not_inherit_provider_secrets(self):
        with patch.dict(os.environ, {'OPENNEWS_TOKEN': 'synthetic-inherited-value', 'ALL_PROXY': 'http://outside.invalid'}):
            cwd, argv, env = self.check()
        self.assertEqual(cwd, self.root / 'jobs/tracking')
        self.assertEqual(argv, self.plan['argv'])
        self.assertNotIn('OPENNEWS_TOKEN', env)
        self.assertNotIn('ALL_PROXY', env)
        self.assertEqual(env['NODE_OPTIONS'], '--max-old-space-size=256')

    def test_pending_freeze_cannot_start(self):
        self.plan['accepted_frozen'] = False
        with self.assertRaisesRegex(ValueError, 'ACCEPTED_FREEZE_REQUIRED'):
            self.check()

    def test_acceptance_path_traversal_is_rejected(self):
        outside = Path(self.temp.name) / 'outside.accepted.json'
        self.write(outside, self.record)
        self.plan.update(acceptance_file=str(self.root / 'config/../../outside.accepted.json'),
                         acceptance_sha256=ops.sha(outside))
        with self.assertRaisesRegex(ValueError, 'OWNED_PATH_REQUIRED'):
            self.check()

    def test_environment_path_traversal_is_rejected(self):
        outside = Path(self.temp.name) / 'outside.environment.json'
        self.write(outside, self.values)
        self.plan['environment_file'] = str(self.root / 'config/../../outside.environment.json')
        with self.assertRaisesRegex(ValueError, 'OWNED_PATH_REQUIRED'):
            self.check()

    def test_tracking_config_path_traversal_is_rejected(self):
        outside = Path(self.temp.name) / 'outside.config.json'
        self.write(outside, json.loads(self.config.read_text()))
        self.values['IKUN_TRACKING_CONFIG'] = str(self.root / 'config/../../outside.config.json')
        self.write(self.env, self.values)
        with self.assertRaisesRegex(ValueError, 'OWNED_PATH_REQUIRED'):
            self.check()

    def test_render_path_traversal_is_rejected_before_writing(self):
        (self.root / 'plans').mkdir()
        outside = Path(self.temp.name) / 'escaped-render'
        for accepted in (False, True):
            with self.subTest(accepted_frozen=accepted):
                with self.assertRaisesRegex(ValueError, 'OWNED_PATH_REQUIRED'):
                    ops.render({'worker': 'tracking', 'accepted_frozen': accepted},
                               self.root / 'plans/../../escaped-render', self.root)
                self.assertFalse(outside.exists())

    def test_unload_path_traversal_is_rejected_before_launchctl(self):
        (self.root / 'plans').mkdir()
        outside = Path(self.temp.name) / 'outside.plan.json'
        self.write(outside, {'worker': 'tracking', 'accepted_frozen': False})
        before = outside.read_bytes()
        def unexpected(*args, **kwargs):
            raise AssertionError('must not call launchctl for a traversal plan')
        with self.assertRaisesRegex(ValueError, 'OWNED_PATH_REQUIRED'):
            ops.unload(self.root / 'plans/../../outside.plan.json', self.root, invoke=unexpected)
        self.assertEqual(outside.read_bytes(), before)

    def test_inside_checks_normalized_containment_and_rejects_parent_traversal(self):
        target = self.root / 'config/new/file.json'
        self.assertEqual(ops.inside(target, self.root / 'config'), target.resolve())
        for path, parent in ((self.root, self.root), (Path(self.temp.name) / 'outside', self.root),
                             (target, self.root / 'config/../config')):
            with self.subTest(path=path, parent=parent):
                with self.assertRaisesRegex(ValueError, 'OWNED_PATH_REQUIRED'):
                    ops.inside(path, parent)

    def test_symlink_leaf_and_ancestor_paths_are_rejected(self):
        outside = Path(self.temp.name) / 'outside'
        outside.mkdir()
        self.write(outside / 'private.json', {'synthetic': True})
        alias = self.root / 'config/alias'
        alias.symlink_to(outside, target_is_directory=True)
        leaf = self.root / 'config/leaf.json'
        leaf.symlink_to(outside / 'private.json')
        for path in (alias / 'private.json', leaf):
            with self.subTest(path=path):
                with self.assertRaisesRegex(ValueError, 'ALIASED_PATH_REJECTED'):
                    ops.inside(path, self.root / 'config')
                with self.assertRaisesRegex(ValueError, 'ALIASED_PATH_REJECTED'):
                    ops.private_json(path)

    def test_private_environment_cannot_override_process_controls(self):
        keys = ('HOME', 'home', 'PATH', 'PYTHONHOME', 'PYTHONPATH', 'PYTHONSTARTUP',
                'PYTHONNOUSERSITE', 'NODE_PATH', 'NODE_EXTRA_CA_CERTS', 'DYLD_INSERT_LIBRARIES',
                'DYLD_LIBRARY_PATH', 'LD_PRELOAD', 'LC_ALL', 'BASH_ENV', 'IKUN_ENV_FILE',
                'HUNTER_PYTHON_BIN', 'IKUN_TRACKING_PYTHON', 'UV_THREADPOOL_SIZE',
                'NEXT_TELEMETRY_DISABLED', '__PYVENV_LAUNCHER__')
        for key in keys:
            with self.subTest(key=key):
                self.write(self.env, {**self.values, key: 'synthetic-untrusted-control'})
                with self.assertRaisesRegex(ValueError, 'RESERVED_PROCESS_ENV_REJECTED'):
                    self.check()

    def test_process_controls_are_derived_without_host_environment(self):
        inherited = dict.fromkeys(('HOME', 'PATH', 'PYTHONHOME', 'PYTHONPATH', 'NODE_PATH',
                                   'DYLD_INSERT_LIBRARIES', 'DYLD_LIBRARY_PATH', 'LD_PRELOAD',
                                   'IKUN_TRACKING_PYTHON'), '/private/tmp/synthetic-untrusted')
        with patch.dict(os.environ, inherited):
            _, _, env = self.check()
        self.assertEqual(env['HOME'], str(ops.ACCOUNT_HOME))
        self.assertEqual(env['PATH'], str(self.root / 'toolchains/node24/bin') + ':/usr/bin:/bin')
        self.assertEqual(env['PYTHONPATH'], str(self.release / 'services/tracking-worker/python'))
        self.assertEqual(env['IKUN_TRACKING_PYTHON'], str(self.root / 'venvs/tracking/bin/python'))
        self.assertEqual(env['PYTHONNOUSERSITE'], '1')
        for key in ('PYTHONHOME', 'NODE_PATH', 'DYLD_INSERT_LIBRARIES', 'DYLD_LIBRARY_PATH', 'LD_PRELOAD'):
            self.assertNotIn(key, env)

    def test_node_resource_modes_remain_exact(self):
        for key, wrong in (('NODE_ENV', 'development'), ('NODE_OPTIONS', '--max-old-space-size=999')):
            with self.subTest(key=key):
                self.write(self.env, {**self.values, key: wrong})
                with self.assertRaisesRegex(ValueError, 'RESOURCE_MODE_CHANGED'):
                    self.check()
        self.write(self.env, {**self.values, 'NODE_ENV': 'production', 'NODE_OPTIONS': '--max-old-space-size=256'})
        self.check()

    def test_owned_python_entry_uses_derived_module_path(self):
        exe = self.root / 'venvs/tracking/bin/python'
        exe.parent.mkdir(parents=True)
        exe.write_text('synthetic Python executable, never executed')
        self.plan['argv'] = [str(exe), '-m', 'tracking.cli', 'serve', '--config', str(self.config)]
        self.record.update(argv=self.plan['argv'], executable_sha256=ops.sha(exe))
        self.write(self.receipt, self.record)
        self.plan['acceptance_sha256'] = ops.sha(self.receipt)
        _, argv, env = self.check()
        self.assertEqual(argv, self.plan['argv'])
        self.assertEqual(env['PYTHONPATH'], str(self.release / 'services/tracking-worker/python'))
        self.assertNotIn('PYTHONPATH', self.values)

    def test_isolated_guard_ignores_inherited_python_controls_before_preflight(self):
        pending = Path(self.temp.name) / 'pending.json'
        self.write(pending, {'worker': 'tracking', 'accepted_frozen': False})
        inherited = {**os.environ, 'PYTHONHOME': '/private/tmp/synthetic-missing-home',
                     'PYTHONPATH': '/private/tmp/synthetic-missing-modules'}
        result = subprocess.run([sys.executable, '-I', str(SCRIPT), 'check', '--plan', str(pending)],
                                env=inherited, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stderr), {'status': 'BLOCKED_WORKER_PREFLIGHT'})
        self.assertEqual(result.stdout, '')

    def test_provider_credentials_are_rejected(self):
        self.values['IKUN_TRACKING_6551_TOKEN'] = 'synthetic-unwanted-credential'
        self.write(self.env, self.values)
        with self.assertRaisesRegex(ValueError, 'PROVIDER_OR_PUBLIC_ENV_REJECTED'):
            self.check()

    def test_remote_enabled_is_rejected(self):
        config = json.loads(self.config.read_text());config['remote_enabled'] = True
        self.write(self.config, config)
        with self.assertRaisesRegex(ValueError, 'TRACKING_OFF_MODE_REQUIRED'):
            self.check()

    def test_external_destination_is_rejected(self):
        self.values['CONTROLLED_RECEIVER'] = 'https://outside.invalid/receive'
        self.write(self.env, self.values)
        with self.assertRaisesRegex(ValueError, 'NONLOCAL_URL_REJECTED'):
            self.check()

    def test_private_direction_loopback_is_permitted(self):
        self.values['CONTROLLED_RECEIVER'] = 'http://127.0.0.1:4000/internal/v1/ingest/hunter'
        self.write(self.env, self.values)
        self.check()

    def test_runtime_bytes_are_bound(self):
        self.entry.write_text('changed artifact')
        with self.assertRaisesRegex(ValueError, 'RUNTIME_FILE_DRIFT'):
            self.check()

    def test_implicit_dotenv_is_rejected(self):
        (self.release / '.env.local').write_text('synthetic-only')
        with self.assertRaisesRegex(ValueError, 'IMPLICIT_DOTENV_REJECTED'):
            self.check()

    def test_hardlinked_business_database_is_rejected(self):
        own = self.root / 'data/tracking/tracking.db'
        own.unlink();os.link(self.root / 'data/projects/projects.db', own)
        with self.assertRaisesRegex(ValueError, 'DATABASE_ALIAS_OR_PERMISSION'):
            self.check()

    def test_database_migration_is_never_implicit(self):
        own = self.root / 'data/tracking/tracking.db';own.unlink()
        with self.assertRaisesRegex(ValueError, 'EXPLICIT_MIGRATION_REQUIRED'):
            self.check()

    def test_schema_domain_version_mismatch_is_rejected(self):
        with sqlite3.connect(self.root / 'data/tracking/tracking.db') as database:
            database.execute('PRAGMA application_id=999')
        with self.assertRaisesRegex(ValueError, 'EXPLICIT_MIGRATION_OR_DOMAIN_MISMATCH'):
            self.check()

    def hunter(self):
        (self.root / 'jobs/hunter').mkdir(mode=0o700)
        self.plan.update(worker='hunter', cwd=str(self.root / 'jobs/hunter'))
        entry = self.release / 'services/hunter-worker/dist/main.js'
        entry.parent.mkdir(parents=True);entry.write_text('synthetic hunter entry')
        self.plan.update(argv=[str(self.exe),str(entry)],runtime_sha256={'services/hunter-worker/dist/main.js':ops.sha(entry)})
        self.record['worker'] = 'hunter'
        self.record.update(argv=self.plan['argv'],runtime_sha256=self.plan['runtime_sha256'])
        self.write(self.receipt, self.record)
        self.plan['acceptance_sha256'] = ops.sha(self.receipt)
        self.values = {'DATA_ROOT': str(self.root / 'data'), 'HUNTER_API_TOKEN': secrets.token_urlsafe(32),
                       'HUNTER_EXTERNAL_IO_ENABLED': '0', 'HUNTER_HOST': '127.0.0.1', 'HUNTER_PORT': '4011',
                       'HUNTER_DB': str(self.root / 'data/hunter/hunter.db'), 'HUNTER_V2_MODE': '1',
                       'HUNTER_TENANT_ID': 'ikun-main', 'HUNTER_DELIVERY_PROTOCOL': 'v2-event', 'HUNTER_ENGINE': 'python'}
        self.write(self.env, self.values)

    def test_hunter_requires_explicit_local_v2_off_mode(self):
        self.hunter()
        self.check()

    def test_hunter_external_collection_flag_cannot_be_enabled(self):
        self.hunter()
        self.values['HUNTER_EXTERNAL_IO_ENABLED'] = '1'
        self.write(self.env, self.values)
        with self.assertRaisesRegex(ValueError, 'HUNTER_OFF_MODE_REQUIRED'):
            self.check()

    def test_worker_cannot_run_other_domain_artifacts(self):
        self.plan['worker'] = 'hunter';self.record['worker'] = 'hunter'
        self.write(self.receipt, self.record);self.plan['acceptance_sha256'] = ops.sha(self.receipt)
        with self.assertRaisesRegex(ValueError, 'OTHER_DOMAIN_RUNTIME_REJECTED'):
            self.check()

    def test_unknown_startup_arguments_cannot_be_added(self):
        self.plan['argv'] = [str(self.exe), '-e', 'synthetic']
        self.record['argv'] = self.plan['argv']
        self.write(self.receipt, self.record);self.plan['acceptance_sha256'] = ops.sha(self.receipt)
        with self.assertRaisesRegex(ValueError, 'EXACT_WORKER_ENTRY_REQUIRED'):
            self.check()

    def test_render_is_new_owned_job_only_and_preserves_data_on_rollback(self):
        destination = Path(self.temp.name) / 'rendered'
        result = ops.render({'worker': 'tracking', 'accepted_frozen': False}, destination, self.root)
        self.assertFalse(result['installed'])
        self.assertFalse(result['started'])
        job = plistlib.loads((destination / 'ca.ikun.v2.c0lite.tracking.plist').read_bytes())
        self.assertEqual(job['Label'], 'ca.ikun.v2.c0lite.tracking')
        self.assertEqual(job['ProgramArguments'][1], '-I')
        self.assertTrue(job['KeepAlive'])
        self.assertEqual(job['Umask'], 0o077)
        self.assertEqual(json.loads((destination / 'rollback.json').read_text())['database_action'], 'preserve')
        with self.assertRaisesRegex(ValueError, 'NEW_PLAN_DIRECTORY_REQUIRED'):
            ops.render(self.plan, destination, self.root)

    def installed(self):
        destination = self.root / 'plans/tracking/prepared'
        destination.parent.mkdir(mode=0o700, parents=True)
        ops.render({'worker': 'tracking', 'accepted_frozen': False}, destination, self.root)
        agents = Path(self.temp.name) / 'agents';agents.mkdir()
        plist = agents / 'ca.ikun.v2.c0lite.tracking.plist'
        ops.write_new(plist, (destination / plist.name).read_bytes())
        return destination / 'worker.json', agents, plist

    def test_rollback_archives_only_exact_owned_job_without_touching_db(self):
        plan, agents, plist = self.installed();calls=[]
        before=ops.sha(self.root / 'data/tracking/tracking.db')
        def invoke(argv, **kwargs):
            calls.append(argv)
            if len(calls)>2:
                return SimpleNamespace(returncode=1,stderr=b'Could not find service "ca.ikun.v2.c0lite.tracking"')
            return SimpleNamespace(returncode=0,stderr=b'')
        result=ops.unload(plan,self.root,agents,invoke)
        self.assertEqual([x[1] for x in calls],['print','bootout','print'])
        self.assertTrue(all(x[-1].endswith('/ca.ikun.v2.c0lite.tracking') for x in calls))
        self.assertFalse(plist.exists())
        self.assertTrue((Path(result['archive']) / plist.name).is_file())
        self.assertEqual(before,ops.sha(self.root / 'data/tracking/tracking.db'))

    def test_rollback_refuses_existing_unowned_label(self):
        plan, agents, plist = self.installed();job=plistlib.loads(plist.read_bytes())
        job['ProgramArguments']=['/private/tmp/unrelated-job']
        plist.write_bytes(plistlib.dumps(job))
        def unexpected(*args, **kwargs):
            raise AssertionError('must not call launchctl for an unowned job')
        with self.assertRaisesRegex(ValueError,'OWNED_JOB_MISMATCH'):
            ops.unload(plan,self.root,agents,unexpected)

    def test_rollback_does_not_treat_permission_error_as_absent(self):
        plan, agents, plist = self.installed()
        def denied(*args, **kwargs):
            return SimpleNamespace(returncode=1,stderr=b'Operation not permitted')
        with self.assertRaisesRegex(ValueError,'OWNED_JOB_STATUS_UNAVAILABLE'):
            ops.unload(plan,self.root,agents,denied)
        self.assertTrue(plist.exists())


if __name__ == '__main__':
    unittest.main()
