import {test} from 'node:test';
import assert from 'node:assert/strict';
import {SAMPLE_WIRE} from '../features/radar/sample.ts';
import {
  displayText, formatBeijing, maybeSpeak, presentRadar, radarBridgeConfig, safeHref,
  sealWatermark, seenKey, shouldNotify, voiceLine,
} from '../lib/radar-view.ts';

const userA = 'usr_11111111-1111-4111-8111-111111111111';
const userB = 'usr_22222222-2222-4222-8222-222222222222';

test('beijing time is explicit and stable', () => {
  assert.equal(formatBeijing(0), '1970-01-01 08:00:00 北京时间');
});

test('urls and secrets from untrusted payloads are clamped', () => {
  assert.equal(safeHref('javascript:alert(1)'), '');
  assert.equal(safeHref('https://user:pass@github.com/x'), '');
  assert.equal(safeHref('https://evil.example/phish'), '');
  assert.equal(safeHref('http://github.com/x'), '');
  assert.equal(safeHref('https://github.com/four-meme-community/fourmeme-docs'), 'https://github.com/four-meme-community/fourmeme-docs');
  assert.equal(displayText('see bearer abcdefghijklmnop and wss://rpc.example/secret'), 'see [已隐藏] and [已隐藏]');
  assert.equal(displayText('bot123456:ABCDEFGHIJK'), '[已隐藏]');
});

test('sample preview is labeled and does not claim four.meme event coverage', () => {
  const model = presentRadar(SAMPLE_WIRE, 1763510400);
  assert.ok(model);
  assert.equal(model!.sample, true);
  assert.equal(model!.cards.find(card => card.id === 'four-events')?.state, 'unconfigured');
  assert.match(model!.cards.find(card => card.id === 'four-events')?.limit ?? '', /不能把它看成完整监控/);
  assert.equal(model!.cards.find(card => card.id === 'flap-events')?.state, 'live');
  assert.equal(model!.cards.find(card => card.id === 'flap-github')?.state, 'unconfigured');
  assert.equal(model!.cards.find(card => card.id === 'four-identity')?.state, 'partial');
  const injected = model!.events.find(event => event.id === 2);
  assert.equal(injected?.href, '');
  assert.match(injected?.title ?? '', /<script>/);
  assert.equal(model!.events.find(event => event.id === 1)?.href, '');
  assert.equal(model!.events.find(event => event.id === 4)?.href.startsWith('https://bscscan.com/tx/'), true);
});

test('history, baseline, duplicates and reconnect do not notify twice', () => {
  const baseline = {id: 1, kind: 'baseline', title: '已建立基线：flap'};
  const fresh = {id: 5, kind: 'new', title: '新文档页面'};
  const seen = new Set<number>();
  assert.equal(sealWatermark(null, 4), 4);
  assert.equal(shouldNotify(fresh, 4, seen), true);
  assert.equal(shouldNotify(baseline, 0, seen), false);
  assert.equal(shouldNotify({id: 3, kind: 'new', title: '雷达在线 | 心跳'}, 0, seen), false);
  seen.add(5);
  assert.equal(shouldNotify(fresh, 4, seen), false);
  assert.equal(sealWatermark('4', 9), 4);
  assert.equal(sealWatermark('nope', 9), 9);
});

test('a new verified repository notifies once and does not speak untrusted text', () => {
  const event = {
    id: 9,
    source: 'github-discover:FLAP',
    kind: 'new',
    title: 'FLAP 官方账号 flap-sh 新增公开仓库 Demo <script>',
  };
  assert.equal(shouldNotify(event, 0, new Set()), true);
  assert.equal(shouldNotify(event, 9, new Set()), false);
  assert.equal(voiceLine(event), 'FLAP，有新变化');
  assert.equal(voiceLine({source: 'github-discover:FLAP', kind: 'baseline', title: '已建立 FLAP 官方仓库基线'}), null);
  assert.equal(safeHref('https://github.com/flap-sh/Demo'), 'https://github.com/flap-sh/Demo');
  assert.equal(safeHref('javascript:alert(1)'), '');
  assert.equal(safeHref('https://user:pass@github.com/flap-sh/Demo'), '');
});

test('voice follows the gesture gate and speaks project plus motion once', () => {
  const event = {id: 7, source: 'docs:flap', kind: 'gone', title: '文档页面删除'};
  assert.equal(voiceLine(event), 'FLAP，有删除');
  assert.equal(voiceLine({source: 'github:four-meme-community/openfour-docs', kind: 'new', title: '新增文件'}), 'four.meme，有新变化');
  assert.equal(voiceLine({source: 'radar', kind: 'baseline', title: '已建立基线'}), null);
  const spoken = new Set<number>();
  const said: string[] = [];
  const input = {event, armed: false, enabled: true, quiet: false, available: true, spoken, speak: (text: string) => said.push(text)};
  assert.equal(maybeSpeak(input), false);
  assert.equal(maybeSpeak({...input, armed: true, enabled: false}), false);
  assert.equal(maybeSpeak({...input, armed: true, quiet: true}), false);
  assert.equal(maybeSpeak({...input, armed: true}), true);
  assert.deepEqual(said, ['FLAP，有删除']);
  assert.equal(maybeSpeak({...input, armed: true}), false);
});

test('seen watermarks do not cross users', () => {
  assert.equal(seenKey(userA), `ikun.radar.seen.v1.${userA}`);
  assert.notEqual(seenKey(userA), seenKey(userB));
  assert.equal(seenKey('root'), null);
  assert.equal(seenKey('../other'), null);
});

test('bridge config rejects public hosts, sniper rpc and empty env', () => {
  assert.equal(radarBridgeConfig({}), null);
  assert.equal(radarBridgeConfig({IKUN_RADAR_TOKEN: 'x'.repeat(32), IKUN_RADAR_ORIGIN: 'http://127.0.0.1:8545'}), null);
  assert.equal(radarBridgeConfig({IKUN_RADAR_TOKEN: 'x'.repeat(32), IKUN_RADAR_ORIGIN: 'http://example.com:3921'}), null);
  assert.equal(radarBridgeConfig({IKUN_RADAR_TOKEN: 'x'.repeat(32), IKUN_RADAR_ORIGIN: 'https://127.0.0.1:3921'}), null);
  assert.deepEqual(radarBridgeConfig({IKUN_RADAR_TOKEN: 'x'.repeat(32)}), {origin: 'http://127.0.0.1:3921', token: 'x'.repeat(32)});
  assert.equal(radarBridgeConfig(process.env) === null || typeof radarBridgeConfig(process.env)?.token === 'string', true);
});
