"""Deployment guard tests only; no real worker, job, API, database or provider access."""
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import secrets
import sqlite3
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
