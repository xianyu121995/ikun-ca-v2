import { existsSync } from 'node:fs';
import { dirname, isAbsolute, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const [service, mode = 'start'] = process.argv.slice(2);
if (!['website', 'hunter', 'tracking'].includes(service) || !['dev', 'start'].includes(mode)) {
  throw new Error('Usage: node scripts/service.mjs website|hunter|tracking dev|start');
}
if (Number(process.versions.node.split('.')[0]) !== 24) throw new Error('Use Node 24 LTS; see .node-version');
const envFile = process.env.IKUN_ENV_FILE ? resolve(process.env.IKUN_ENV_FILE) : join(root, '.env.local');
if (existsSync(envFile)) process.loadEnvFile(envFile);
if (process.env.IKUN_ENV === 'production' && !process.env.DATA_ROOT) throw new Error('Production DATA_ROOT is required');
const dataRoot = process.env.DATA_ROOT ?? './var/dev';
process.env.DATA_ROOT = isAbsolute(dataRoot) ? dataRoot : resolve(root, dataRoot);
process.env.NEXT_TELEMETRY_DISABLED = '1';
process.env.NODE_ENV = mode === 'dev' ? 'development' : 'production';
process.env.NODE_OPTIONS ??= service === 'website' ? '--max-old-space-size=1024' : '--max-old-space-size=256';
const folder = service === 'website' ? join(root, 'apps/website') : join(root, `services/${service}-worker`);
let args;
if (service === 'website') {
  const host = process.env.WEBSITE_HOST ?? '127.0.0.1';
  if (host !== '127.0.0.1') throw new Error('Website must bind to loopback; use a reverse proxy for public access');
  args = [join(folder, 'node_modules/next/dist/bin/next'), mode === 'dev' ? 'dev' : 'start', '--hostname', host, '--port', process.env.WEBSITE_PORT ?? '3100'];
} else {
  args = mode === 'dev' ? [join(root, 'node_modules/tsx/dist/cli.mjs'), 'watch', 'src/main.ts'] : ['dist/main.js'];
}
const child = spawn(process.execPath, args, { cwd: folder, env: process.env, stdio: 'inherit' });
child.once('error', () => { process.stderr.write('Failed to start service\n'); process.exitCode = 1; });
const forward = signal => { if (child.exitCode === null) child.kill(signal); };
process.on('SIGTERM', () => forward('SIGTERM'));
process.on('SIGINT', () => forward('SIGINT'));
child.once('exit', (code, signal) => { process.exitCode = code ?? (signal ? 1 : 0); });
