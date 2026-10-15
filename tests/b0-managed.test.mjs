import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync, readFileSync, existsSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { createHash } from 'node:crypto';
import { spawn } from 'node:child_process';
import { ManagedProjectsIpc, probeProjectsIpc, spawnManaged } from '../packages/runtime/dist/index.js';

const entry = resolve('tests/fixtures/projects-ipc.mjs');
const config = { executable: process.execPath, args: [entry], cwd: process.cwd(), entry_path: entry, entry_sha256: createHash('sha256').update(readFileSync(entry)).digest('hex'), build_sha: '1'.repeat(40) };
test('private IPC has a bound identity; bad token/build, timeout and shutdown fail closed', async () => {
  const dataRoot = mkdtempSync('/private/tmp/ikun-b0-ipc-');
  const service = new ManagedProjectsIpc(config, dataRoot);
  try {
    await service.start(); assert.equal(await service.ready(), true);
    assert.equal(await probeProjectsIpc({ ...service.identity, token: 'wrong'.repeat(12) }), false);
    assert.equal(await probeProjectsIpc({ ...service.identity, buildSha: '2'.repeat(40) }), false);
    assert.equal(existsSync(join(dataRoot, 'projects/projects.db')), false);
    await service.stop(); assert.equal(await service.ready(), false);
    assert.equal(existsSync(service.identity.socketPath), false);
  } finally { await service.stop(); rmSync(dataRoot, { recursive: true, force: true }); }
});
test('modified entry is rejected and child death invalidates readiness without paid retries', async () => {
  const dataRoot = mkdtempSync('/private/tmp/ikun-b0-ipc-');
  assert.throws(() => new ManagedProjectsIpc({ ...config, entry_sha256: '0'.repeat(64) }, dataRoot), /PROJECTS_ENTRY_MISMATCH/);
  const state = join(dataRoot, 'fixture-state.json');
  const service = new ManagedProjectsIpc({ ...config, args: [entry, '--state-file', state] }, dataRoot);
  try { await service.start(); const { pid } = JSON.parse(readFileSync(state)); assert.ok(Number.isInteger(pid) && pid > 1); process.kill(pid, 'SIGKILL'); await new Promise(done => setTimeout(done, 30)); assert.equal(await service.ready(), false); }
  finally { await service.stop(); rmSync(dataRoot, { recursive: true, force: true }); }
});
test('failed child startup is bounded and cleans its private IPC directory', async () => {
  const root = mkdtempSync('/private/tmp/ikun-b0-ipc-');
  const failing = resolve('tests/fixtures/projects-ipc-exit.mjs');
  const service = new ManagedProjectsIpc({ ...config, args: [failing], entry_path: failing, entry_sha256: createHash('sha256').update(readFileSync(failing)).digest('hex') }, root);
  try { await assert.rejects(() => service.start(1000), /PROJECTS_IPC_NOT_READY/); assert.equal(existsSync(service.identity.socketPath), false); }
  finally { await service.stop(); rmSync(root, { recursive: true, force: true }); }
});
test('a stalled IPC body has a hard startup deadline and is cleaned up', async () => {
  const root = mkdtempSync('/private/tmp/ikun-b0-ipc-');
  const service = new ManagedProjectsIpc({ ...config, args: [entry, '--stall'] }, root);
  const before = Date.now();
  try { await assert.rejects(() => service.start(250), /PROJECTS_IPC_NOT_READY/); assert.ok(Date.now() - before < 1500); }
  finally { await service.stop(); rmSync(root, { recursive: true, force: true }); }
});
test('managed process group shutdown reaches an uncooperative grandchild', async () => {
  const childScript = `process.on('SIGTERM',()=>{});setInterval(()=>{},1000)`;
  const parentScript = `const {spawn}=require('node:child_process');const child=spawn(process.execPath,['-e',${JSON.stringify(childScript)}],{stdio:'ignore'});process.on('SIGTERM',()=>process.exit(0));setInterval(()=>{},1000);`;
  const managed = spawnManaged(process.execPath, ['-e', parentScript], { cwd: process.cwd(), env: { PATH: '/usr/bin:/bin' }, graceMs: 250 });
  await new Promise(done => setTimeout(done, 150));
  await managed.stop(); await managed.stop();
  for (let i = 0; i < 30; i++) {
    try { process.kill(-managed.child.pid, 0); await new Promise(done => setTimeout(done, 20)); }
    catch (error) { assert.equal(error.code, 'ESRCH'); return; }
  }
  assert.fail('Private child process group survived shutdown');
});
test('abrupt parent SIGKILL does not orphan the private service or its grandchild', async () => {
  const root = mkdtempSync('/private/tmp/ikun-b0-orphan-'); const state = join(root, 'state.json');
  const parent = spawn(process.execPath, [resolve('tests/fixtures/orphan-parent.mjs'), resolve('tests/fixtures/idle-tree.mjs'), state], { stdio: 'ignore' });
  let pids;
  try {
    for (let i = 0; i < 80 && !existsSync(state); i++) await new Promise(done => setTimeout(done, 25));
    pids = JSON.parse(readFileSync(state)); assert.ok(pids.pid > 1 && pids.grandchild > 1);
    const exited = new Promise(done => parent.once('exit', done)); parent.kill('SIGKILL'); await exited;
    for (const pid of [pids.pid, pids.grandchild]) {
      let alive = true;
      for (let i = 0; i < 100; i++) {
        try { process.kill(pid, 0); await new Promise(done => setTimeout(done, 25)); }
        catch (error) { assert.equal(error.code, 'ESRCH'); alive = false; break; }
      }
      assert.equal(alive, false, `Owned fixture process ${pid} survived parent death`);
    }
  } finally {
    if (parent.exitCode === null && parent.signalCode === null) parent.kill('SIGKILL');
    rmSync(root, { recursive: true, force: true });
  }
});
test('entry drift after construction is rejected before spawning and cleans private directory', async () => {
  const root = mkdtempSync('/private/tmp/ikun-b0-entry-'); const local = join(root, 'entry.mjs');
  writeFileSync(local, readFileSync(entry));
  const service = new ManagedProjectsIpc({ ...config, entry_path: local, args: [local] }, root);
  writeFileSync(local, 'throw new Error("must never execute changed entry");');
  try { await assert.rejects(() => service.start(), /PROJECTS_ENTRY_MISMATCH/); assert.equal(existsSync(join(service.identity.socketPath, '..')), false); }
  finally { await service.stop(); rmSync(root, { recursive: true, force: true }); }
});
test('caller argument mutation does not change the pinned launch; invalid deadlines reject', async () => {
  const root = mkdtempSync('/private/tmp/ikun-b0-entry-');
  const launch = { ...config, args: [entry] }; const service = new ManagedProjectsIpc(launch, root);
  launch.args.splice(0, 1, '/not-the-pinned-entry'); launch.build_sha = 'a'.repeat(40);
  try { await service.start(); assert.equal(await service.ready(), true); }
  finally { await service.stop(); rmSync(root, { recursive: true, force: true }); }
  const other = mkdtempSync('/private/tmp/ikun-b0-deadline-'); const invalid = new ManagedProjectsIpc(config, other);
  try { await assert.rejects(() => invalid.start(Infinity), /INVALID_STARTUP_DEADLINE/); assert.equal(await probeProjectsIpc(invalid.identity, Infinity), false); }
  finally { await invalid.stop(); rmSync(other, { recursive: true, force: true }); }
});
test('private Projects child does not inherit unrelated parent credentials or environment', async () => {
  const root = mkdtempSync('/private/tmp/ikun-b0-env-');
  const previous = process.env.IKUN_B0_ENV_CANARY; process.env.IKUN_B0_ENV_CANARY = 'synthetic-parent-only';
  const service = new ManagedProjectsIpc(config, root);
  try { await service.start(); assert.equal(await service.ready(), true); }
  finally { await service.stop(); if (previous === undefined) delete process.env.IKUN_B0_ENV_CANARY; else process.env.IKUN_B0_ENV_CANARY = previous; rmSync(root, { recursive: true, force: true }); }
});
