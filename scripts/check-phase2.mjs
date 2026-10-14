import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const read = path => JSON.parse(readFileSync(resolve(root, path), 'utf8'));
const catalog = read('docs/phase2/contract.json');
const ownership = read('docs/phase2/ownership.json');
const releases = read('docs/phase2/releases.json');
const sources = read('docs/phase2/source-freeze.json');
const manifest = read('docs/phase2/freeze-manifest.json');
for (const doc of [ownership, releases, sources, manifest]) assert.equal(doc.contract_version, catalog.contract_version);
assert.equal(catalog.scope, 'ikun-main');
assert.deepEqual(catalog.roles, ['superadmin', 'user']);
assert.equal(catalog.business_routes_implemented_by_this_commit, false);
assert.deepEqual(catalog.runtime.independent_services, ['website', 'hunter', 'tracking']);
assert.equal(catalog.runtime.launchd_jobs, 3);
const transport = readFileSync(resolve(root, 'packages/contracts/src/phase2.ts'), 'utf8');
const foundationTypes = readFileSync(resolve(root, 'packages/contracts/src/index.ts'), 'utf8');
const union = (source, name) => {
  const match = source.match(new RegExp(`export type ${name} = ([^;]+);`));
  assert.ok(match, `Missing transport enum: ${name}`);
  return match[1].split('|').map(value => JSON.parse(value.trim()));
};
assert.ok(transport.includes(`PHASE2_CONTRACT_VERSION = "${catalog.contract_version}"`));
assert.ok(transport.includes(`SITE_SCOPE = "${catalog.scope}"`));
assert.deepEqual(union(foundationTypes, 'Role'), catalog.roles);
for (const [name, key] of [['ProjectRating', 'ratings'], ['ProgressStage', 'progress_stages'], ['HomeMembership', 'home_memberships'], ['CommandState', 'command_states']]) {
  assert.deepEqual(union(transport, name), catalog[key]);
}
assert.equal(releases.merge_authorized, false);
assert.equal(releases.production_authorized, false);
assert.deepEqual(releases.immediately_released, ['website', 'homepage-ui', 'hunter-ui', 'tracking-ui']);
const owners = new Set(ownership.rules.map(rule => rule.owner));
assert.equal(owners.size, 10);
const claims = ownership.rules.flatMap(rule => [
  ...rule.prefixes.map(path => ({ owner: rule.owner, path, prefix: true })),
  ...rule.files.map(path => ({ owner: rule.owner, path, prefix: false })),
]);
for (const path of ownership.reserved_destinations) claims.push({ owner: ownership.reserved_owner, path, prefix: true });
for (const claim of claims) {
  assert.ok(!claim.path.startsWith('/') && !claim.path.split('/').some(segment => segment === '..' || segment === '.') && !claim.path.includes('*'), `Invalid claim: ${claim.path}`);
}
const contains = (claim, path) => claim.prefix ? path.startsWith(claim.path) : path === claim.path;
for (let i = 0; i < claims.length; i++) for (let j = i + 1; j < claims.length; j++) {
  const a = claims[i], b = claims[j];
  if (a.owner !== b.owner) assert.ok(!contains(a, b.path) && !contains(b, a.path), `Ownership conflict: ${a.path} / ${b.path}`);
}
const completed = new Set();
assert.deepEqual(releases.stages.map(stage => stage.id), ['UI0', 'B0', 'B1', 'B2', 'B3', 'B4', 'C0', 'D0']);
for (const stage of releases.stages) {
  assert.ok(stage.requires.every(required => completed.has(required)), `Stage order invalid: ${stage.id}`);
  assert.ok(stage.owners.every(owner => owners.has(owner)));
  assert.equal(stage.state, stage.id === 'UI0' ? 'released' : 'held');
  completed.add(stage.id);
}
assert.equal(new Set(Object.values(catalog.databases).map(db => db.relative_path)).size, 4);
assert.equal(new Set(Object.values(catalog.databases).map(db => db.application_id)).size, 4);
for (const [index, name] of ['hunter', 'tracking', 'projects', 'auth'].entries()) {
  assert.equal(catalog.databases[name].application_id, 0x494b0201 + index);
}
assert.equal(sources.modules.length, 9);
assert.equal(new Set(sources.modules.map(module => module.owner)).size, 9);
for (const module of sources.modules) {
  assert.ok(owners.has(module.owner) && /^[a-f0-9]{40}$/.test(module.commit));
  execFileSync('git', ['cat-file', '-e', `${module.commit}^{commit}`], { cwd: root, stdio: 'pipe' });
  execFileSync('git', ['merge-base', '--is-ancestor', sources.foundation_commit, module.commit], { cwd: root, stdio: 'pipe' });
  assert.equal(module.frozen, true);
  assert.equal(module.worktree_clean_at_snapshot, true);
  assert.equal(module.integration_accepted, false);
}
for (const [path, expected] of Object.entries(manifest.files)) {
  assert.ok(existsSync(resolve(root, path)), `Missing authority file: ${path}`);
  const actual = createHash('sha256').update(readFileSync(resolve(root, path))).digest('hex');
  assert.equal(actual, expected, `Frozen spec drift: ${path}`);
}
process.stdout.write(`Phase 2 OK: ${sources.modules.length} pinned sources, ${Object.keys(manifest.files).length} frozen files, 10 non-overlapping owners, 4 UI releases, backend/merge/production held\n`);
