import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync, mkdirSync, readdirSync } from 'node:fs';
import { resolve, dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const output = join(root, 'var/b0/closeout'); mkdirSync(output, { recursive: true });
const env = { ...process.env, PATH: `${dirname(process.execPath)}:${process.env.PATH}`, NEXT_TELEMETRY_DISABLED: '1', IKUN_ENV: 'test', IKUN_ENV_FILE: join(output, 'absent.env') };
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const steps = [
  ['build', 'pnpm', ['build']],
  ['typecheck', 'pnpm', ['typecheck']],
  ['tests', process.execPath, ['--test', '--test-reporter=tap', ...readdirSync(join(root, 'tests')).filter(path => path.endsWith('.test.mjs')).sort().map(path => `tests/${path}`)]],
  ['foundation-smoke', process.execPath, ['scripts/smoke.mjs']],
  ['ipc-smoke', process.execPath, ['scripts/smoke-b0.mjs']],
  ['clean-ui-workspace', process.execPath, ['scripts/verify-ui-workspace.mjs']],
  ['phase2-freeze', process.execPath, ['scripts/check-phase2.mjs']],
];
const sourcePaths = ['packages/runtime/src/managed.ts', 'packages/runtime/src/process-entry.ts', 'packages/runtime/src/stores.ts', 'apps/website/lib/stores.ts', 'apps/website/app/health/ready/route.ts', 'scripts/service.mjs', 'scripts/init-stores.mjs', 'scripts/verify-ui-workspace.mjs'];
const sourceHashes = Object.fromEntries(sourcePaths.map(path => [path, hash(readFileSync(join(root, path)))]));
const report = { phase: 'B0', checked_at: new Date().toISOString(), node: process.version, source_hashes: sourceHashes, steps: [], all_passed: false, business_tested: false, merge: false, production: false };
for (const [name, executable, args] of steps) {
  const started = Date.now(); let log;
  try {
    log = execFileSync(executable, args, { cwd: root, env, encoding: 'utf8', maxBuffer: 16 * 1024 * 1024, timeout: 180000, stdio: ['ignore', 'pipe', 'pipe'] });
  } catch (error) {
    writeFileSync(join(output, `${name}.log`), (error.stdout?.toString() ?? '') + (error.stderr?.toString() ?? ''));
    report.steps.push({ name, passed: false, exit_code: error.status });
    writeFileSync(join(output, 'acceptance.json'), JSON.stringify(report, null, 2) + '\n');
    throw new Error(`B0_ACCEPTANCE_FAILED:${name}; see var/b0/closeout/${name}.log`);
  }
  writeFileSync(join(output, `${name}.log`), log);
  const step = { name, passed: true, duration_ms: Date.now() - started, log_sha256: hash(log) };
  if (name === 'tests') {
    step.tests = Number(log.match(/^# tests (\d+)/m)?.[1]);
    step.failed = Number(log.match(/^# fail (\d+)/m)?.[1]);
    if (!Number.isSafeInteger(step.tests) || step.tests < 26 || step.failed !== 0) throw new Error('B0_TEST_REPORT_INVALID');
  }
  report.steps.push(step); console.log(`B0 ${name}: PASS`);
}
for (const [path, expected] of Object.entries(sourceHashes)) if (hash(readFileSync(join(root, path))) !== expected) throw new Error(`Source changed during acceptance: ${path}`);
report.workspace = JSON.parse(readFileSync(join(root, 'var/b0/workspace/validation.json')));
report.services = JSON.parse(readFileSync(join(root, 'var/b0/services/validation.json')));
report.all_passed = true;
writeFileSync(join(output, 'acceptance.json'), JSON.stringify(report, null, 2) + '\n');
console.log('B0 serial acceptance PASS; backend business remains frozen');
