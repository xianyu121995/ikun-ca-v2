import { spawn, type ChildProcess } from 'node:child_process';
import { request } from 'node:http';
import { randomBytes, createHash } from 'node:crypto';
import { mkdtempSync, chmodSync, readFileSync, lstatSync, rmSync } from 'node:fs';
import { isAbsolute, join } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import { fileURLToPath } from 'node:url';

export interface ManagedProcess { child: ChildProcess; stop(): Promise<void> }
/** A private guardian controls this explicitly spawned tree, including parent death. */
export function spawnManaged(command: string, args: readonly string[], options: { cwd: string; env: NodeJS.ProcessEnv; graceMs?: number; inheritOutput?: boolean }): ManagedProcess {
  if (process.platform === 'win32' || !isAbsolute(command) || !isAbsolute(options.cwd)) throw new Error('INVALID_MANAGED_COMMAND');
  const graceMs = options.graceMs ?? 2000;
  if (!Number.isFinite(graceMs) || graceMs < 1 || graceMs > 10000) throw new Error('INVALID_SHUTDOWN_DEADLINE');
  const guardian = fileURLToPath(new URL('./process-entry.js', import.meta.url));
  const child = spawn(process.execPath, [guardian, String(process.pid), String(graceMs), command, JSON.stringify(args)], { cwd: options.cwd, env: options.env, detached: true, shell: false, stdio: options.inheritOutput ? 'inherit' : 'ignore' });
  // Always register error handlers, including binaries that fail before a PID exists.
  let ended = false; let stopPromise: Promise<void> | undefined;
  const exited = new Promise<void>(done => {
    child.once('error', () => { ended = true; done(); });
    child.once('exit', () => { ended = true; done(); });
  });
  const signal = (name: NodeJS.Signals) => {
    if (!child.pid) return;
    try { process.kill(-child.pid, name); } catch (error) { if ((error as NodeJS.ErrnoException).code !== 'ESRCH') throw error; }
  };
  return { child, stop() {
    return stopPromise ??= (async () => {
      signal('SIGTERM');
      await Promise.race([exited, delay(graceMs + 500, undefined, { ref: false })]);
      // A child may exit before an uncooperative grandchild: reap its private group too.
      signal('SIGKILL');
      if (!ended) await exited;
    })();
  } };
}
export interface IpcIdentity { socketPath: string; token: string; buildSha: string }
export async function probeProjectsIpc(identity: IpcIdentity, timeoutMs = 750): Promise<boolean> {
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0 || timeoutMs > 10000) return false;
  if (!isAbsolute(identity.socketPath) || Buffer.byteLength(identity.socketPath) > 100 || identity.token.length < 32 || !/^[a-f0-9]{40}$/.test(identity.buildSha)) return false;
  try {
    const socket = lstatSync(identity.socketPath);
    if (!socket.isSocket() || socket.uid !== process.getuid?.() || (socket.mode & 0o777) !== 0o600) return false;
  } catch { return false; }
  return new Promise<boolean>(done => {
    const req = request({ socketPath: identity.socketPath, path: '/health/ready', method: 'GET', headers: { authorization: `Bearer ${identity.token}` } }, res => {
      let bytes = 0; const chunks: Buffer[] = [];
      res.on('data', (chunk: Buffer) => { bytes += chunk.length; if (bytes > 16384) req.destroy(); else chunks.push(chunk); });
      res.on('end', () => {
        try {
          const data = JSON.parse(Buffer.concat(chunks).toString()).data;
          done(res.statusCode === 200 && data?.service === 'projects' && data?.ready === true && data?.writer === 'projects-domain' && data?.build_sha === identity.buildSha);
        } catch { done(false); }
      });
      res.on('error', () => done(false)); res.on('aborted', () => done(false));
    });
    // Hard deadline bounds even slow response bodies. No automatic write retries exist.
    const timer = setTimeout(() => { req.destroy(); done(false); }, timeoutMs);
    req.once('close', () => clearTimeout(timer)); req.on('error', () => done(false)); req.end();
  });
}
export interface ProjectsAdapterConfig {
  executable: string; args: string[]; cwd: string; entry_path: string;
  entry_sha256: string; build_sha: string;
}
/** Opt-in infrastructure only. B2 supplies the actual frozen Projects domain entry. */
export class ManagedProjectsIpc {
  readonly identity: IpcIdentity;
  private readonly directory: string;
  private managed?: ManagedProcess;
  private stopped = false;
  private failed = false;
  private readonly config: ProjectsAdapterConfig;
  private verifyEntry(): void {
    const entry = lstatSync(this.config.entry_path);
    if (!entry.isFile() || entry.isSymbolicLink() || entry.nlink !== 1 || createHash('sha256').update(readFileSync(this.config.entry_path)).digest('hex') !== this.config.entry_sha256) throw new Error('PROJECTS_ENTRY_MISMATCH');
  }
  constructor(config: ProjectsAdapterConfig, private readonly dataRoot: string) {
    if (!isAbsolute(dataRoot) || !isAbsolute(config.entry_path) || !isAbsolute(config.cwd) || !isAbsolute(config.executable) || !Array.isArray(config.args) || config.args[0] !== config.entry_path || !config.args.every(arg => typeof arg === 'string') || !/^[a-f0-9]{40}$/.test(config.build_sha)) throw new Error('INVALID_PROJECTS_ADAPTER');
    // Do not retain caller-owned mutable launch arguments after validating them.
    this.config = { ...config, args: [...config.args] };
    Object.freeze(this.config.args); Object.freeze(this.config);
    this.verifyEntry();
    this.directory = mkdtempSync('/private/tmp/ikp-'); chmodSync(this.directory, 0o700);
    this.identity = { socketPath: join(this.directory, 'p.sock'), token: randomBytes(32).toString('hex'), buildSha: config.build_sha };
  }
  async start(timeoutMs = 5000): Promise<void> {
    if (this.managed || this.stopped) throw new Error('PROJECTS_ADAPTER_ALREADY_USED');
    try {
      if (!Number.isFinite(timeoutMs) || timeoutMs <= 0 || timeoutMs > 30000) throw new Error('INVALID_STARTUP_DEADLINE');
      // Reject drift during bootstrap, immediately before launching the pinned entry.
      // Immutable release directories are still required; this is not an OS-level seal.
      this.verifyEntry();
      this.managed = spawnManaged(this.config.executable, this.config.args, { cwd: this.config.cwd, env: {
      PATH: '/usr/bin:/bin:/usr/sbin:/sbin', LANG: 'en_US.UTF-8', PYTHONUNBUFFERED: '1',
      PROJECTS_DB: join(this.dataRoot, 'projects/projects.db'), IKUN_ENV: 'isolated',
      IKUN_IPC_SOCKET: this.identity.socketPath, IKUN_IPC_TOKEN: this.identity.token,
      IKUN_BUILD_SHA: this.identity.buildSha,
      } });
      this.managed.child.once('exit', () => { this.failed = true; });
      this.managed.child.once('error', () => { this.failed = true; });
      const deadline = Date.now() + timeoutMs;
      while (Date.now() < deadline && !this.failed && !this.stopped) {
        if (await this.ready(Math.min(750, Math.max(1, deadline - Date.now())))) return;
        await delay(50);
      }
      throw new Error('PROJECTS_IPC_NOT_READY');
    } catch (error) { await this.stop(); throw error; }
  }
  async ready(timeoutMs = 750): Promise<boolean> { return !this.failed && !this.stopped && await probeProjectsIpc(this.identity, timeoutMs); }
  async stop(): Promise<void> {
    this.stopped = true;
    try { await this.managed?.stop(); } finally { rmSync(this.directory, { recursive: true, force: true }); }
  }
}
