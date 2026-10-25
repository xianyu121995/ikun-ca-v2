import {test} from 'node:test';
import assert from 'node:assert/strict';
import {
  SETTINGS_KEY,
  WATERMARK_KEY,
  DEFAULT_SETTINGS,
  considerCuesSync,
  considerDiscoveries,
  formatAlertToast,
  loadSettings,
  loadWatermark,
  normalizeSettings,
  pickNewerThan,
  saveSettings,
  type DiscoveryCue,
} from '../lib/hunter-alert.ts';

function memoryStorage(seed: Record<string, string> = {}): Storage {
  const map = new Map(Object.entries(seed));
  return {
    get length() {return map.size;},
    clear() {map.clear();},
    getItem(k) {return map.has(k) ? map.get(k)! : null;},
    setItem(k, v) {map.set(k, String(v));},
    removeItem(k) {map.delete(k);},
    key(i) {return [...map.keys()][i] ?? null;},
  };
}

const t0 = Date.parse('2026-10-25T12:00:00.000Z');
const cue = (id: string, offsetSec: number, handle = id): DiscoveryCue => ({
  discovery_id: id,
  discovered_at: new Date(t0 + offsetSec * 1000).toISOString(),
  x_handle: handle,
});

test('defaults: sound off, dingdong, volume 0.7; malformed settings are repaired', () => {
  assert.deepEqual(DEFAULT_SETTINGS, {enabled: false, sound: 'dingdong', volume: 0.7});
  assert.equal(normalizeSettings({enabled: true, sound: 'nope', volume: 9}).sound, 'dingdong');
  assert.equal(normalizeSettings({volume: -1}).volume, 0);
  assert.equal(loadSettings(memoryStorage()).enabled, false);
});

test('first load seeds watermark silently and does not fire', () => {
  const storage = memoryStorage();
  const cues = [cue('a', 10, 'alpha'), cue('b', 20, 'beta')];
  const result = considerCuesSync(cues, storage, {...DEFAULT_SETTINGS, enabled: true}, t0);
  assert.equal(result.fired, false);
  assert.equal(result.initialized, true);
  assert.equal(result.batch, null);
  assert.equal(loadWatermark(storage), t0 + 20_000);
});

test('empty first load still seeds watermark to now', () => {
  const storage = memoryStorage();
  const result = considerCuesSync([], storage, {...DEFAULT_SETTINGS, enabled: true}, t0 + 99_000);
  assert.equal(result.fired, false);
  assert.equal(result.initialized, true);
  assert.equal(loadWatermark(storage), t0 + 99_000);
});

test('one fire per batch of newer discoveries; watermark advances to newest', () => {
  const storage = memoryStorage({[WATERMARK_KEY]: String(t0)});
  const cues = [cue('old', -5, 'old'), cue('n1', 5, 'one'), cue('n2', 8, 'two')];
  const result = considerCuesSync(cues, storage, {...DEFAULT_SETTINGS, enabled: true}, t0);
  assert.equal(result.fired, true);
  assert.equal(result.batch?.count, 2);
  assert.match(result.batch!.toast, /^新发现 2 个项目：/);
  assert.ok(result.batch!.toast.includes('@two') || result.batch!.toast.includes('@one'));
  assert.equal(loadWatermark(storage), t0 + 8_000);

  const again = considerCuesSync(cues, storage, {...DEFAULT_SETTINGS, enabled: true}, t0);
  assert.equal(again.fired, false);
  assert.equal(again.batch, null);
});

test('toggle off advances watermark but does not fire', () => {
  const storage = memoryStorage({[WATERMARK_KEY]: String(t0)});
  const result = considerCuesSync([cue('n', 30, 'neon')], storage, {...DEFAULT_SETTINGS, enabled: false}, t0);
  assert.equal(result.fired, false);
  assert.equal(result.batch, null);
  assert.equal(loadWatermark(storage), t0 + 30_000);
});

test('pickNewerThan ignores invalid timestamps and equal watermark', () => {
  assert.deepEqual(pickNewerThan([{discovery_id: 'x', discovered_at: 'bad'}], t0), []);
  assert.deepEqual(pickNewerThan([cue('eq', 0)], t0), []);
  assert.equal(pickNewerThan([cue('gt', 1)], t0).length, 1);
});

test('formatAlertToast caps handles at three', () => {
  const cues = ['a', 'b', 'c', 'd'].map((h, i) => cue(h, i + 1, h));
  assert.match(formatAlertToast(cues), /等 4 个/);
});

test('cross-tab lock: second consider after watermark write does not fire', async () => {
  const storage = memoryStorage({[WATERMARK_KEY]: String(t0)});
  let lockHeld = false;
  const locks = {
    request: async (_name: string, cb: (lock: unknown) => Promise<unknown>) => {
      assert.equal(lockHeld, false);
      lockHeld = true;
      try {return await cb({});} finally {lockHeld = false;}
    },
  };
  const fired: string[] = [];
  const a = await considerDiscoveries([cue('n', 5, 'x')], {
    storage, locks, settings: {...DEFAULT_SETTINGS, enabled: true},
    onFire: async (batch) => {fired.push(batch.toast);},
  });
  const b = await considerDiscoveries([cue('n', 5, 'x')], {
    storage, locks, settings: {...DEFAULT_SETTINGS, enabled: true},
    onFire: async (batch) => {fired.push(batch.toast);},
  });
  assert.equal(a.fired, true);
  assert.equal(b.fired, false);
  assert.equal(fired.length, 1);
});

test('settings round-trip persists sound choice', () => {
  const storage = memoryStorage();
  saveSettings(storage, {enabled: true, sound: 'bell', volume: 0.4});
  assert.deepEqual(loadSettings(storage), {enabled: true, sound: 'bell', volume: 0.4});
  assert.ok(storage.getItem(SETTINGS_KEY));
});
