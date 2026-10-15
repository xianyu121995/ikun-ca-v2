import { existsSync, readFileSync, lstatSync } from 'node:fs';
import { dirname, isAbsolute, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';
import { ManagedProjectsIpc, spawnManaged } from '../packages/runtime/dist/index.js';

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
let projects;
let managed;
let draining;
const stop = () => draining ??= (async () => { await managed?.stop(); await projects?.stop(); })();
process.once('SIGTERM', () => { void stop(); });
process.once('SIGINT', () => { void stop(); });
if (service === 'website') {
  const host = process.env.WEBSITE_HOST ?? '127.0.0.1';
  if (host !== '127.0.0.1') throw new Error('Website must bind to loopback; use a reverse proxy for public access');
  // Explicit bootstrap before accepting requests. Readiness itself never creates/migrates.
  const adapterConfig = process.env.IKUN_PROJECTS_ADAPTER_CONFIG;
  try {
    if (adapterConfig) {
      if (!isAbsolute(adapterConfig)) throw new Error('PROJECTS_ADAPTER_CONFIG_MUST_BE_ABSOLUTE');
      const info = lstatSync(adapterConfig);
      if (!info.isFile() || info.isSymbolicLink() || info.nlink !== 1 || (info.mode & 0o777) !== 0o600) throw new Error('UNSAFE_PROJECTS_ADAPTER_CONFIG');
      projects = new ManagedProjectsIpc(JSON.parse(readFileSync(adapterConfig, 'utf8')), process.env.DATA_ROOT);
    }
    execFileSync(process.execPath, [join(root, 'scripts/init-stores.mjs'), 'website', ...(adapterConfig ? ['--auth-only'] : [])], { env: process.env, stdio: 'inherit' });
    if (projects) {
      await projects.start();
      process.env.IKUN_PROJECTS_IPC_SOCKET = projects.identity.socketPath;
      process.env.IKUN_PROJECTS_IPC_TOKEN = projects.identity.token;
      process.env.IKUN_PROJECTS_BUILD_SHA = projects.identity.buildSha;
    }
  } catch (error) {
    await stop();
    throw new Error(/^[A-Z0-9_]+$/.test(error.message) ? error.message : 'SERVICE_BOOTSTRAP_FAILED');
  }
  args = [join(folder, 'node_modules/next/dist/bin/next'), mode === 'dev' ? 'dev' : 'start', '--hostname', host, '--port', process.env.WEBSITE_PORT ?? '3100'];
} else {
  args = mode === 'dev' ? [join(root, 'node_modules/tsx/dist/cli.mjs'), 'watch', 'src/main.ts'] : ['dist/main.js'];
}
if (draining) throw new Error('SERVICE_STOPPING');
managed = spawnManaged(process.execPath, args, { cwd: folder, env: process.env, inheritOutput: true, graceMs: 10000 });
const child = managed.child;
child.once('error', () => { process.stderr.write('Failed to start service\n'); process.exitCode = 1; void stop(); });
child.once('exit', (code, signal) => { process.exitCode = code ?? (signal ? 1 : 0); void stop(); });
