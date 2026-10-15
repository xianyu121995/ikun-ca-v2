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
const closeout = read('docs/b0/closeout.json'), receiving = read('config/b0/receiving-plan.json');
const git = (...args) => execFileSync('git', args, { cwd: root, encoding: 'utf8' }).trim();
assert.equal(current.UI0.state, 'accepted_frozen');
assert.equal(current.B0.state, 'accepted');
assert.equal(current.B0.acceptance_scope, 'infrastructure_only');
assert.deepEqual(current.B0.remaining_B0_blockers, []);
assert.equal(current.B1.state, 'held');
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
const testReport = closeout.steps.find(step => step.name === 'tests');
assert.equal(closeout.all_passed, true); assert.ok(closeout.steps.every(step => step.passed));
assert.equal(testReport.failed, 0); assert.ok(testReport.tests >= 26);
assert.equal(validation.foundation_infrastructure_tests, testReport.tests);
assert.equal(validation.workspace.next_ui_consumption, true);
assert.equal(validation.workspace.ui_css_consumption, true);
assert.equal(validation.workspace.frozen_install, true);
assert.equal(validation.services.passed, true);
assert.equal(validation.services.next_wrote_projects_database, false);
assert.equal(validation.backend_business_enabled, false);
assert.equal(validation.production_deployed, false);
assert.equal(receiving.status, 'reviewed_not_executed');
assert.equal(receiving.execution_authorized, false);
assert.equal(receiving.merge_authorized, false); assert.equal(receiving.production_authorized, false);
assert.deepEqual(receiving.receiver_order, ['ui-package', 'auth', 'projects', 'tracking-worker', 'hunter-worker']);
for (const [path, expected] of Object.entries(receiving.protected_main_files_sha256)) assert.equal(createHash('sha256').update(readFileSync(resolve(root, path))).digest('hex'), expected, `Protected receiving file changed: ${path}`);
for (const [owner, commit] of Object.entries(receiving.source_pins)) assert.equal(git('rev-parse', `codex/${owner}`), commit);
assert.equal(manifest.version, 2);
assert.equal(manifest.previous_candidate, current.previous_candidate);
assert.equal(git('rev-parse', 'b0-infra-candidate-v0.1.0^{commit}'), current.previous_candidate);
assert.equal(createHash('sha256').update(execFileSync('git', ['show', `${current.previous_candidate}:docs/b0/manifest.json`], { cwd: root })).digest('hex'), manifest.previous_manifest_sha256);
execFileSync('git', ['merge-base', '--is-ancestor', current.previous_candidate, 'HEAD'], { cwd: root });
const prefixes = ['docs/b0/', 'config/b0/', 'scripts/', 'tests/', 'packages/runtime/'];
const files = ['apps/website/lib/stores.ts', 'apps/website/app/health/ready/route.ts'];
for (const [path, expected] of Object.entries(manifest.files)) {
  assert.ok(!path.split('/').includes('..') && (files.includes(path) || prefixes.some(prefix => path.startsWith(prefix))), `B0 ownership violation: ${path}`);
  assert.equal(createHash('sha256').update(readFileSync(resolve(root, path))).digest('hex'), expected, `B0 source drift: ${path}`);
}
for (const [path, hash] of Object.entries(closeout.source_hashes)) assert.equal(manifest.files[path], hash, `Untested final source: ${path}`);
if (process.argv.includes('--staged')) {
  const staged = git('diff', '--cached', '--name-only').split('\n').filter(Boolean).sort();
  assert.deepEqual(staged, manifest.this_commit_files.slice().sort());
  assert.ok(staged.every(path => path === 'docs/b0/manifest.json' || manifest.files[path]));
}
console.log('B0 acceptance PASS: closed infrastructure scope, receiving plan reviewed, all five backend sources held, no merge/deployment');
