import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const read = path => JSON.parse(readFileSync(resolve(root, path), 'utf8'));
const current = read('docs/b0/current.json'), validation = read('docs/b0/validation.json');
const manifest = read('docs/b0/manifest.json'), ui = read('docs/b0/ui-acceptance.json');
const git = (...args) => execFileSync('git', args, { cwd: root, encoding: 'utf8' }).trim();
assert.equal(current.UI0.state, 'accepted_frozen');
assert.equal(current.B0.state, 'in_progress');
assert.equal(current.B0.owner, 'chief');
assert.equal(current.merge_authorized, false); assert.equal(current.production_authorized, false);
assert.equal(current.C0, 'held'); assert.equal(current.D0, 'held');
assert.equal(current.phase2_spec_commit, git('rev-parse', 'phase2-spec-v1.0.0^{commit}'));
assert.equal(git('rev-list', '--merges', `${current.phase2_spec_commit}..HEAD`), '');
assert.equal(current.backends.length, 5);
for (const module of current.backends) {
  assert.equal(module.release, 'held');
  assert.equal(git('rev-parse', `codex/${module.owner}`), module.commit);
}
assert.equal(current.UI0.sources.length, 4);
for (const source of current.UI0.sources) assert.equal(git('rev-parse', `codex/${source.owner}`), source.commit);
assert.equal(ui.ui_acceptance, 'PASS'); assert.equal(ui.layouts.length, 12);
assert.deepEqual(ui.errors, []); assert.deepEqual(ui.forbidden_requests, []);
assert.equal(validation.foundation_infrastructure_tests, 16);
assert.equal(validation.workspace.frozen_install, true);
assert.equal(validation.services.passed, true);
assert.equal(validation.services.next_wrote_projects_database, false);
assert.equal(validation.backend_business_enabled, false);
assert.equal(validation.production_deployed, false);
const prefixes = ['docs/b0/', 'config/b0/', 'scripts/', 'tests/', 'packages/runtime/'];
const files = ['apps/website/lib/stores.ts', 'apps/website/app/health/ready/route.ts'];
for (const [path, expected] of Object.entries(manifest.files)) {
  assert.ok(!path.split('/').includes('..') && (files.includes(path) || prefixes.some(prefix => path.startsWith(prefix))), `B0 ownership violation: ${path}`);
  assert.equal(createHash('sha256').update(readFileSync(resolve(root, path))).digest('hex'), expected, `B0 source drift: ${path}`);
}
if (process.argv.includes('--staged')) {
  const staged = git('diff', '--cached', '--name-only').split('\n').filter(Boolean).sort();
  assert.deepEqual(staged, [...Object.keys(manifest.files), 'docs/b0/manifest.json'].sort());
}
console.log('B0 checks PASS: UI accepted/frozen, infrastructure candidate pinned, all five backend sources held, no merge/deployment');
