/** Private process guardian. Never invoke with secrets in argv. */
import { spawn } from 'node:child_process';

const [parent, grace, executable, serialized] = process.argv.slice(2);
const parentPid = Number(parent), graceMs = Number(grace);
if (!executable || !serialized || !Number.isInteger(parentPid) || parentPid < 2 || !Number.isFinite(graceMs)) throw new Error('INVALID_PROCESS_GUARDIAN');
const args: string[] = JSON.parse(serialized);
const child = spawn(executable, args, { detached: true, shell: false, env: process.env, stdio: 'inherit' });
let exitCode: number | undefined, cleanup: Promise<void> | undefined;
let finish: () => void;
const exited = new Promise<void>(done => { finish = done; });
const signalGroup = (signal: NodeJS.Signals) => {
  if (!child.pid) return;
  try { process.kill(-child.pid, signal); } catch (error) { if ((error as NodeJS.ErrnoException).code !== 'ESRCH') throw error; }
};
const stop = () => cleanup ??= (async () => {
  clearInterval(monitor);
  signalGroup('SIGTERM');
  let timer: NodeJS.Timeout | undefined;
  await Promise.race([exited, new Promise<void>(done => { timer = setTimeout(done, graceMs); })]);
  if (timer) clearTimeout(timer);
  signalGroup('SIGKILL'); // descendants may survive even when the direct child exited
  await exited;
  process.exitCode = exitCode ?? 1;
})();
const monitor = setInterval(() => {
  // Mac lacks Linux PDEATHSIG: a dedicated guardian detects reparenting after SIGKILL.
  if (process.ppid !== parentPid) void stop();
}, 100);
process.once('SIGTERM', () => { void stop(); });
process.once('SIGINT', () => { void stop(); });
child.once('error', () => { exitCode = 1; finish(); void stop(); });
child.once('exit', (code, signal) => { exitCode = code ?? (signal ? 1 : 0); finish(); void stop(); });
