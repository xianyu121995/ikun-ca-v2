import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdtemp, readdir, rm } from 'node:fs/promises';
import { createServer } from 'node:net';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { randomBytes } from 'node:crypto';

const root = resolve(import.meta.dirname, '..');
// Canonical /private/tmp on macOS avoids the system /tmp symlink.
const temporaryRoot = process.platform === 'darwin' ? '/private/tmp' : tmpdir();
const dataRoot = await mkdtemp(join(temporaryRoot, 'ikun-ca-v2-smoke-'));
const freePort = () => new Promise((done, reject) => {
  const socket = createServer();
  socket.once('error', reject);
  socket.listen(0, '127.0.0.1', () => {
    const port = socket.address().port;
    socket.close(() => done(port));
  });
});
const ports = {};
for (const name of ['website', 'hunter', 'tracking']) ports[name] = await freePort();
const token = randomBytes(32).toString('hex');
const env = { ...process.env, IKUN_ENV: 'test', DATA_ROOT: dataRoot,
  WEBSITE_PORT: String(ports.website), HUNTER_PORT: String(ports.hunter), TRACKING_PORT: String(ports.tracking),
  HUNTER_API_TOKEN: token, TRACKING_API_TOKEN: token, PROJECTS_INGEST_HUNTER_TOKEN: token,
};
const children = new Map();
const start = name => {
  const child = spawn(process.execPath, [join(root, 'scripts/service.mjs'), name, 'start'], { cwd: root, env, stdio: ['ignore', 'pipe', 'pipe'] });
  let output = '';
  child.stdout.on('data', bytes => { output += bytes; });
  child.stderr.on('data', bytes => { output += bytes; });
  child.on('error', error => { output += error.name; });
  children.set(name, { child, output: () => output });
};
const get = (name, path, options) => fetch(`http://127.0.0.1:${ports[name]}${path}`, { ...options, signal: AbortSignal.timeout(2000) });
const ready = async name => {
  for (let attempt = 0; attempt < 80; attempt++) {
    const item = children.get(name);
    if (item.child.exitCode !== null) throw new Error(`${name} exited: ${item.output()}`);
    try { const res = await get(name, '/health/ready'); if (res.ok) return; } catch { /* startup */ }
    await new Promise(done => setTimeout(done, 250));
  }
  throw new Error(`${name} readiness timeout: ${children.get(name).output()}`);
};
const stop = async name => {
  const item = children.get(name);
  if (!item || item.child.exitCode !== null) return;
  const exited = new Promise(done => item.child.once('exit', done));
  item.child.kill('SIGTERM');
  const deadline = setTimeout(() => item.child.kill('SIGKILL'), 12000);
  await exited;
  clearTimeout(deadline);
  // Next 16.4 explicitly finishes its cleanup with 143 on SIGTERM.
  const expected = name === 'website' ? [0, 143] : [0];
  assert.ok(expected.includes(item.child.exitCode), `${name} did not exit gracefully: ${item.child.exitCode}`);
};
try {
  for (const name of ['website', 'hunter', 'tracking']) start(name);
  await Promise.all(['website', 'hunter', 'tracking'].map(ready));
  assert.equal((await get('website', '/')).status, 200);
  assert.equal((await get('website', '/api/v1/projects')).status, 503);
  assert.equal((await get('website', '/internal/v1/ingest/hunter', { method: 'POST' })).status, 401);
  assert.equal((await get('website', '/internal/v1/ingest/hunter', { method: 'POST', headers: { authorization: `Bearer ${token}` } })).status, 501);
  for (const name of ['hunter', 'tracking']) {
    assert.equal((await get(name, '/internal/v1/status')).status, 401);
    assert.equal((await get(name, '/internal/v1/status', { headers: { authorization: `Bearer ${token}` } })).status, 200);
    assert.equal((await get(name, '/internal/v1/commands', { method: 'POST', headers: { authorization: `Bearer ${token}` } })).status, 501);
    assert.equal((await get(name, '/unknown')).status, 404);
  }
  for (const name of ['hunter', 'tracking', 'projects', 'auth']) {
    assert.ok((await readdir(join(dataRoot, name))).includes(`${name}.db`));
  }
  await stop('hunter');
  assert.equal((await get('website', '/health/ready')).status, 200);
  assert.equal((await get('tracking', '/health/ready')).status, 200);
  start('hunter');
  await ready('hunter');
  await stop('tracking');
  assert.equal((await get('hunter', '/health/ready')).status, 200);
  assert.equal((await get('website', '/health/ready')).status, 200);
  start('tracking');
  await ready('tracking');
} finally {
  const results = await Promise.allSettled([...children.keys()].map(stop));
  await rm(dataRoot, { recursive: true, force: true });
  const failure = results.find(result => result.status === 'rejected');
  if (failure) throw failure.reason;
}
console.log('Smoke passed: 3 independent production services, 4 stores, auth gates, isolated worker restarts and shutdown');
