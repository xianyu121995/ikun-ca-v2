import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync, mkdtempSync, mkdirSync, rmSync, copyFileSync, existsSync, readdirSync } from 'node:fs';
import { resolve, dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import assert from 'node:assert/strict';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const config = JSON.parse(readFileSync(join(root, 'config/b0/workspace.json')));
const temp = mkdtempSync('/private/tmp/ikun-b0-workspace-');
const env = { ...process.env, PATH: `${dirname(process.execPath)}:${process.env.PATH}`, CI: 'true', NEXT_TELEMETRY_DISABLED: '1' };
const run = (args, cwd = temp) => execFileSync('pnpm', args, { cwd, env, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], maxBuffer: 8 * 1024 * 1024 });
const git = args => execFileSync('git', args, { cwd: root, maxBuffer: 8 * 1024 * 1024 });
const generatedLock = join(root, 'config/b0/pnpm-ui-lock.yaml');
try {
  // No Git operations or business-source merges in the receiving repository.
  // A disposable clean filesystem fixture contains only tracked foundation code and pinned UI.
  const paths = git(['ls-files', '-z']).toString().split('\0').filter(path => path && !path.startsWith('modules/'));
  for (const path of paths) {
    if (/^(config\/b0|docs\/b0|scripts\/audit-ui-final)/.test(path)) continue;
    mkdirSync(dirname(join(temp, path)), { recursive: true });
    copyFileSync(join(root, path), join(temp, path));
  }
  const uiFiles = git(['ls-tree', '-r', '--name-only', config.ui_commit, '--', config.package_prefix]).toString().trim().split('\n');
  for (const path of uiFiles) {
    assert.ok(path.startsWith(config.package_prefix));
    mkdirSync(dirname(join(temp, path)), { recursive: true });
    writeFileSync(join(temp, path), git(['show', `${config.ui_commit}:${path}`]));
  }
  const websitePath = join(temp, 'apps/website/package.json');
  const website = JSON.parse(readFileSync(websitePath));
  website.dependencies[config.package_name] = config.website_dependency;
  writeFileSync(websitePath, JSON.stringify(website, null, 2) + '\n');
  // Prove actual Next consumption, not only an unused workspace dependency.
  // This disabled, synthetic route exists only in the disposable fixture.
  const route = join(temp, 'apps/website/app/b0-ui-check/page.tsx');
  mkdirSync(dirname(route), { recursive: true });
  writeFileSync(route, `"use client";
import { Button, Panel, ScoreBadge } from '@ikun/ui';
import '@ikun/ui/styles.css';
export default function Check() { return <Panel title="B0 dependency check"><Button disabled>B0 dependency fixture</Button><ScoreBadge grade={null}/></Panel>; }
`);
  const store = process.env.IKUN_B0_PNPM_STORE ?? join(root, '.pnpm-store');
  const log = [];
  if (process.argv.includes('--refresh-lock')) {
    log.push(run(['install', '--lockfile-only', '--offline', '--ignore-scripts', '--store-dir', store]));
    mkdirSync(dirname(generatedLock), { recursive: true });
    copyFileSync(join(temp, 'pnpm-lock.yaml'), generatedLock);
  } else {
    assert.ok(existsSync(generatedLock), 'First generate the infrastructure-only lock candidate with --refresh-lock');
    copyFileSync(generatedLock, join(temp, 'pnpm-lock.yaml'));
  }
  log.push(run(['install', '--frozen-lockfile', '--offline', '--ignore-scripts', '--store-dir', store]));
  // All builds are serial on the 8GB machine. No service is started.
  for (const name of config.serial_build_order) log.push(run(['--filter', name, 'build']));
  const rendered = readFileSync(join(temp, 'apps/website/.next/server/app/b0-ui-check.html'), 'utf8');
  assert.ok(rendered.includes('B0 dependency fixture') && rendered.includes('未评分'));
  const cssDir = join(temp, 'apps/website/.next/static/css');
  assert.ok(readdirSync(cssDir).filter(path => path.endsWith('.css')).some(path => readFileSync(join(cssDir, path), 'utf8').includes('--ik-bg:')));
  log.push(run(['--filter', '@ikun/ui', 'typecheck']));
  log.push(run(['--filter', '@ikun/ui', 'test']));
  const output = join(root, 'var/b0/workspace'); mkdirSync(output, { recursive: true });
  writeFileSync(join(output, 'build.log'), log.join('\n'));
  writeFileSync(join(output, 'validation.json'), JSON.stringify({ passed: true, ui_commit: config.ui_commit, clean_filesystem: true, frozen_install: true, offline: true, install_scripts: false, serial_build_order: config.serial_build_order, next_ui_consumption: true, ui_css_consumption: true, fixture_route_committed: false, lock_sha256: createHash('sha256').update(readFileSync(generatedLock)).digest('hex'), services_started: false, source_merge: false }, null, 2) + '\n');
  console.log('B0 workspace PASS: pinned UI in disposable fixture, offline frozen install, six serial builds, UI typecheck and tests; no source merge');
} catch (error) {
  console.error(error.stdout?.toString() ?? ''); console.error(error.stderr?.toString() ?? ''); throw error;
} finally { rmSync(temp, { recursive: true, force: true }); }
