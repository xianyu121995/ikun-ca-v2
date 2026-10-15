/** Install the unchanged frozen @ikun/ui package locally, without editing workspace files. */
import { execFileSync } from 'node:child_process';
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync, copyFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';

const feature = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const root = resolve(feature, '../../../..');
const sourceCommit = '4527ba4510dcb3ea8a3d1bf932dc46367070d1d5';
const run = (file, args, cwd = root, options = {}) => execFileSync(file, args, { cwd, stdio: 'inherit', ...options });
if (!process.versions.node.startsWith('24.')) throw new Error('Use the repository Node 24 toolchain');
const actualRoot = execFileSync('git', ['rev-parse', '--show-toplevel'], { cwd: root, encoding: 'utf8' }).trim();
if (actualRoot !== root) throw new Error('Run from the dedicated tracking-ui Worktree');
execFileSync('git', ['cat-file', '-e', `${sourceCommit}:packages/ui/src/index.ts`], { cwd: root });
const scratch = mkdtempSync(join(tmpdir(), 'ikun-tracking-ui-package-'));
const output = join(feature, '.ui-consumer');
mkdirSync(output, { recursive: true });
const protectedPaths = ['pnpm-lock.yaml', 'package.json', 'apps/website/package.json'];
const before = protectedPaths.map(p => readFileSync(join(root, p)));
try {
  const archive = execFileSync('git', ['archive', sourceCommit, 'packages/ui/src', 'packages/ui/package.json'], { cwd: root });
  run('tar', ['-xf', '-', '-C', scratch], root, { input: archive, stdio: ['pipe', 'inherit', 'inherit'] });
  const source = join(scratch, 'packages/ui');
  const types = join(root, 'apps/website/node_modules/@types');
  const config = { extends: join(root, 'tsconfig.base.json'), compilerOptions: {
    jsx: 'react-jsx', lib: ['ES2022', 'DOM', 'DOM.Iterable'], rootDir: 'src', outDir: 'dist', types: ['node', 'react', 'react-dom'],
    typeRoots: [types, join(root, 'node_modules/@types')], paths: {
      react: [join(types, 'react/index.d.ts')], 'react/jsx-runtime': [join(types, 'react/jsx-runtime.d.ts')], 'react/jsx-dev-runtime': [join(types, 'react/jsx-dev-runtime.d.ts')],
      'react-dom': [join(types, 'react-dom/index.d.ts')], 'react-dom/*': [join(types, 'react-dom/*')],
    },
  }, include: ['src/**/*.ts', 'src/**/*.tsx'] };
  writeFileSync(join(source, 'tsconfig.json'), JSON.stringify(config));
  run(process.execPath, [join(root, 'node_modules/typescript/bin/tsc'), '-p', join(source, 'tsconfig.json')]);
  copyFileSync(join(source, 'src/styles.css'), join(source, 'dist/styles.css'));
  run('pnpm', ['--dir', source, 'pack', '--pack-destination', output]);
  run('pnpm', ['--dir', feature, 'install', '--ignore-workspace', '--lockfile=false', '--ignore-scripts', '--config.auto-install-peers=false', '--store-dir', join(root, '.pnpm-store')]);
  protectedPaths.forEach((p, i) => { if (!readFileSync(join(root, p)).equals(before[i])) throw new Error(`Protected file unexpectedly changed: ${p}`); });
  const digest = createHash('sha256').update(readFileSync(join(output, 'ikun-ui-0.1.0.tgz'))).digest('hex');
  writeFileSync(join(output, 'source.json'), JSON.stringify({ package: '@ikun/ui', source_commit: sourceCommit, archive_sha256: digest, unchanged_upstream_source: true, workspace_registration_pending: true }, null, 2) + '\n');
  process.stdout.write(`Reused frozen @ikun/ui ${sourceCommit}; root manifests and lock unchanged.\n`);
} finally { rmSync(scratch, { recursive: true, force: true }); }
