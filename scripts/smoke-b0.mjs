import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createServer } from 'node:net';
import { mkdtemp, readFile, writeFile, access, rm, mkdir } from 'node:fs/promises';
import { join, resolve, dirname } from 'node:path';
import { createHash, randomBytes } from 'node:crypto';

const root = resolve(import.meta.dirname, '..');
const scratch = await mkdtemp('/private/tmp/ikun-b0-service-');
const data = join(scratch, 'data'); await mkdir(data);
const entry = join(root, 'tests/fixtures/projects-ipc.mjs'); const stateFile = join(scratch, 'ipc-state.json');
const configPath = join(scratch, 'projects-adapter.json');
await writeFile(configPath, JSON.stringify({ executable: process.execPath, args: [entry, '--state-file', stateFile], cwd: root, entry_path: entry, entry_sha256: createHash('sha256').update(await readFile(entry)).digest('hex'), build_sha: '3'.repeat(40) }), { mode: 0o600 });
const freePort = () => new Promise((done, reject) => { const server = createServer(); server.once('error', reject); server.listen(0, '127.0.0.1', () => { const port = server.address().port; server.close(() => done(port)); }); });
const children = new Map(), ports = {};
for (const name of ['website', 'hunter', 'tracking']) ports[name] = await freePort();
const token = randomBytes(32).toString('hex');
const env = { ...process.env, IKUN_ENV_FILE: join(scratch, 'absent.env'), IKUN_ENV: 'test', DATA_ROOT: data,
  WEBSITE_PORT: String(ports.website), HUNTER_PORT: String(ports.hunter), TRACKING_PORT: String(ports.tracking), HUNTER_API_TOKEN: token, TRACKING_API_TOKEN: token };
const get = (name, path) => fetch(`http://127.0.0.1:${ports[name]}${path}`, { signal: AbortSignal.timeout(2000) });
async function stop(name) {
  const child = children.get(name)?.child;
  if (!child || child.exitCode !== null || child.signalCode !== null) return;
  const exited = new Promise(done => child.once('exit', done)); child.kill('SIGTERM');
  const timer = setTimeout(() => child.kill('SIGKILL'), 14500);
  try { await exited; assert.ok([0, 143].includes(child.exitCode), `${name} unclean exit`); }
  finally { clearTimeout(timer); }
}
try {
  for (const name of ['website', 'hunter', 'tracking']) {
    const child = spawn(process.execPath, [join(root, 'scripts/service.mjs'), name, 'start'], { cwd: root, env: { ...env, ...(name === 'website' ? { IKUN_PROJECTS_ADAPTER_CONFIG: configPath } : {}) }, stdio: ['ignore', 'pipe', 'pipe'] });
    let output = ''; child.stdout.on('data', bytes => output += bytes); child.stderr.on('data', bytes => output += bytes);
    children.set(name, { child, output: () => output });
  }
  for (const name of children.keys()) {
    let ready = false;
    for (let attempt = 0; attempt < 80; attempt++) {
      const item = children.get(name); assert.equal(item.child.exitCode, null, `${name} failed: ${item.output()}`);
      try { if ((await get(name, '/health/ready')).ok) { ready = true; break; } } catch {}
      await new Promise(done => setTimeout(done, 100));
    }
    assert.equal(ready, true, `${name} readiness deadline`);
  }
  assert.equal((await get('website', '/api/v1/projects')).status, 503);
  await access(join(data, 'auth/auth.db'));
  await assert.rejects(() => access(join(data, 'projects/projects.db'))); // Next cannot initialize the IPC writer's DB
  const state = JSON.parse(await readFile(stateFile, 'utf8')); assert.ok(state.pid > 1);
  process.kill(state.pid, 'SIGKILL');
  assert.equal((await get('website', '/health/ready')).status, 503);
  assert.equal((await get('hunter', '/health/ready')).status, 200);
  assert.equal((await get('tracking', '/health/ready')).status, 200);
  await stop('website');
  await assert.rejects(() => access(dirname(state.socket)));
  assert.equal((await get('hunter', '/health/ready')).status, 200);
  assert.equal((await get('tracking', '/health/ready')).status, 200);
  const output = join(root, 'var/b0/services'); await mkdir(output, { recursive: true });
  await writeFile(join(output, 'validation.json'), JSON.stringify({ passed: true, independent_services: 3, projects_runtime: 'synthetic private IPC child', child_failure_readiness: 503, next_wrote_projects_database: false, unaffected_workers: ['hunter', 'tracking'], real_business_connected: false, production_deployment: false }, null, 2) + '\n');
} finally {
  const result = await Promise.allSettled([...children.keys()].map(stop));
  await rm(scratch, { recursive: true, force: true });
  const failed = result.find(item => item.status === 'rejected'); if (failed) throw failed.reason;
}
console.log('B0 smoke PASS: three isolated services, website-managed private IPC, child failure rejects readiness, no Next Projects writer, clean shutdown');
