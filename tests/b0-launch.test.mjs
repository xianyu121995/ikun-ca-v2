import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawn, spawnSync } from 'node:child_process';
import { mkdtempSync, rmSync, readFileSync, writeFileSync, existsSync } from 'node:fs';
import { resolve, join, dirname } from 'node:path';
import { createHash } from 'node:crypto';

const launcher = resolve('scripts/service.mjs'), entry = resolve('tests/fixtures/projects-ipc.mjs');
const scratch = () => mkdtempSync('/private/tmp/ikun-b0-launch-');
const env = root => ({ PATH: process.env.PATH, IKUN_ENV_FILE: join(root, 'absent.env'), IKUN_ENV: 'test', DATA_ROOT: join(root, 'data') });
const descriptor = args => ({ executable: process.execPath, args: [entry, ...args], cwd: process.cwd(), entry_path: entry, entry_sha256: createHash('sha256').update(readFileSync(entry)).digest('hex'), build_sha: '4'.repeat(40) });
test('unsafe adapter configuration fails before creating stores or starting a child', () => {
  const root = scratch(); const path = join(root, 'adapter.json');
  try {
    writeFileSync(path, JSON.stringify(descriptor([])), { mode: 0o644 });
    const result = spawnSync(process.execPath, [launcher, 'website', 'start'], { env: { ...env(root), IKUN_PROJECTS_ADAPTER_CONFIG: path }, timeout: 5000, encoding: 'utf8' });
    assert.equal(result.status, 1); assert.match(result.stderr, /UNSAFE_PROJECTS_ADAPTER_CONFIG/);
    assert.equal(existsSync(join(root, 'data')), false);
  } finally { rmSync(root, { recursive: true, force: true }); }
});
test('malformed adapter configuration is rejected without logging its input', () => {
  const root = scratch(); const path = join(root, 'adapter.json'); const canary = 'private-fixture-marker-do-not-log';
  try {
    writeFileSync(path, `{"value":"${canary}"`, { mode: 0o600 });
    const result = spawnSync(process.execPath, [launcher, 'website'], { env: { ...env(root), IKUN_PROJECTS_ADAPTER_CONFIG: path }, timeout: 5000, encoding: 'utf8' });
    assert.equal(result.status, 1); assert.match(result.stderr, /SERVICE_BOOTSTRAP_FAILED/);
    assert.ok(!(result.stderr + result.stdout).includes(canary)); assert.equal(existsSync(join(root, 'data')), false);
  } finally { rmSync(root, { recursive: true, force: true }); }
});
test('a fourth independent Projects service cannot be started', () => {
  const root = scratch();
  try { const result = spawnSync(process.execPath, [launcher, 'projects', 'start'], { env: env(root), timeout: 5000, encoding: 'utf8' }); assert.equal(result.status, 1); assert.equal(existsSync(join(root, 'data')), false); }
  finally { rmSync(root, { recursive: true, force: true }); }
});
test('termination during IPC startup is bounded and leaves no child or private socket', async () => {
  const root = scratch(), state = join(root, 'state.json'), path = join(root, 'adapter.json');
  writeFileSync(path, JSON.stringify(descriptor(['--stall', '--state-file', state])), { mode: 0o600 });
  const parent = spawn(process.execPath, [launcher, 'website'], { env: { ...env(root), IKUN_PROJECTS_ADAPTER_CONFIG: path }, stdio: 'ignore' });
  const exited = new Promise(done => parent.once('exit', done)); let data;
  try {
    for (let i = 0; i < 100 && !existsSync(state); i++) await new Promise(done => setTimeout(done, 25));
    data = JSON.parse(readFileSync(state)); assert.ok(data.pid > 1);
    parent.kill('SIGTERM');
    const timeout = setTimeout(() => parent.kill('SIGKILL'), 4000);
    try { await exited; } finally { clearTimeout(timeout); }
    assert.notEqual(parent.signalCode, 'SIGKILL'); assert.equal(existsSync(dirname(data.socket)), false);
    assert.throws(() => process.kill(data.pid, 0), /ESRCH/);
    assert.equal(existsSync(join(root, 'data/projects/projects.db')), false);
  } finally {
    if (parent.exitCode === null && parent.signalCode === null) { parent.kill('SIGTERM'); await exited; }
    rmSync(root, { recursive: true, force: true });
  }
});
