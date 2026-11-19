import assert from 'node:assert/strict';
import test from 'node:test';
import {
  DEEPSEEK_BASE,
  DEEPSEEK_MODEL,
  ExtractError,
  beijingNow,
  configFrom,
  deepseekBody,
  deepseekEndpoint,
  deepseekExtract,
  parseTimeJson,
  timePrompt,
  unconfiguredMessage,
} from '../lib/ai-extract-time.ts';

const KEY = `sk-${'a'.repeat(32)}`;
const OTHER = `sk-${'b'.repeat(32)}`;

test('beijing clock stays the UTC+8 shift', () => {
  assert.equal(beijingNow(Date.parse('2026-11-02T16:30:00.000Z')), '2026-11-03 00:30');
});

test('prompt still asks for Beijing time and the tweet receive time', () => {
  const prompt = timePrompt('TGE tomorrow 20:00 UTC', 'quoted', '2026-11-02T12:00:00Z', '2026-11-02 20:00');
  assert.match(prompt, /北京时间 2026-11-02 20:00/);
  assert.match(prompt, /UTC\+8/);
  assert.match(prompt, /2026-11-02T12:00:00Z/);
  assert.match(prompt, /TGE tomorrow 20:00 UTC/);
  assert.match(prompt, /被引用推文：quoted/);
});

test('time JSON keeps the existing date, hour, title and status rules', () => {
  assert.deepEqual(parseTimeJson('```json\n{"date":"2026-11-08","hour":"09","title":"TGE 开盘","status":"confirmed"}\n```'), {
    date: '2026-11-08', hour: '09', title: 'TGE 开盘', status: 'confirmed',
  });
  assert.deepEqual(parseTimeJson('{"date":null,"hour":"09","title":"x","status":"maybe"}'), {
    date: null, hour: null, title: 'x', status: 'estimated',
  });
  assert.equal(parseTimeJson('{"date":"2026-11-08","hour":"9","title":"x"}').hour, null);
  assert.equal(parseTimeJson(`{"date":"2026-11-08","title":"${'事'.repeat(80)}"}`).title.length, 60);
  assert.throws(() => parseTimeJson('not json'));
});

test('codex config is unchanged and deepseek is selected from the same file', () => {
  assert.deepEqual(configFrom({ enabled: true, provider: 'codex', codex_bin: '/usr/local/bin/codex' }), {
    provider: 'codex', codexBin: '/usr/local/bin/codex', proxy: undefined,
  });
  assert.equal(configFrom({ enabled: false, provider: 'codex', codex_bin: '/bin/true' }), null);
  assert.equal(configFrom({ enabled: true, provider: 'gemini', api_key: KEY }), null);
  const deepseek = configFrom({ enabled: true, provider: 'deepseek', api_key: KEY });
  assert.equal(deepseek?.provider, 'deepseek');
  if (deepseek?.provider !== 'deepseek') return;
  assert.equal(deepseek.model, DEEPSEEK_MODEL);
  assert.equal(deepseek.baseUrl, DEEPSEEK_BASE);
  assert.equal(deepseek.timeoutMs, 60_000);
  assert.equal(configFrom({ provider: 'deepseek' }), null);
  assert.equal(unconfiguredMessage({ provider: 'deepseek' }), 'DeepSeek 未配置密钥');
  assert.match(unconfiguredMessage({ provider: 'codex', enabled: false }), /Codex 或 DeepSeek/);
});

test('deepseek honors model, base_url, timeout and env key without logging it', async () => {
  const cfg = configFrom({
    provider: 'deepseek',
    api_key: OTHER,
    model: 'deepseek-flash',
    base_url: 'https://api.deepseek.com/v1',
    timeout: 12,
  }, { DEEPSEEK_API_KEY: KEY });
  assert.ok(cfg && cfg.provider === 'deepseek');
  if (!cfg || cfg.provider !== 'deepseek') return;
  assert.equal(cfg.apiKey, KEY);
  assert.equal(cfg.timeoutMs, 12_000);
  let seen: { url: string; body: unknown; authorization: string } | undefined;
  const result = await deepseekExtract(cfg, '识别时间', async (url, init) => {
    seen = { url, body: JSON.parse(init.body), authorization: init.headers.authorization };
    return { status: 200, json: async () => ({ choices: [{ message: { content: '{"date":"2026-12-01","hour":"20","title":"主网上线","status":"confirmed"}' } }] }) };
  });
  assert.deepEqual(result, { date: '2026-12-01', hour: '20', title: '主网上线', status: 'confirmed' });
  assert.equal(seen?.url, 'https://api.deepseek.com/v1/chat/completions');
  assert.deepEqual(seen?.body, deepseekBody('deepseek-flash', '识别时间'));
  assert.deepEqual((seen?.body as { thinking: unknown }).thinking, { type: 'disabled' });
  assert.equal(seen?.authorization, `Bearer ${KEY}`);
  assert.equal(JSON.stringify(result).includes(KEY), false);
});

test('deepseek timeout, rejected key, invalid JSON and HTTP errors stay generic', async () => {
  const cfg = configFrom({ provider: 'deepseek', deepseek_api_key: KEY, base_url: 'not a url', model: 'bad model name' });
  assert.ok(cfg && cfg.provider === 'deepseek');
  if (!cfg || cfg.provider !== 'deepseek') return;
  assert.equal(cfg.model, DEEPSEEK_MODEL);
  assert.equal(cfg.baseUrl, DEEPSEEK_BASE);
  assert.equal(deepseekEndpoint(cfg.baseUrl), 'https://api.deepseek.com/chat/completions');

  const cases: Array<[(url: string, init: { method: string; headers: Record<string, string>; body: string; signal: AbortSignal }) => Promise<{ status: number; json: () => Promise<unknown> }>, string]> = [
    [async () => { const error = new Error('aborted'); error.name = 'AbortError'; throw error; }, 'AI_TIMEOUT'],
    [async () => ({ status: 401, json: async () => ({ error: KEY }) }), 'AI_KEY_REJECTED'],
    [async () => ({ status: 200, json: async () => ({ choices: [{ message: { content: 'nope' } }] }) }), 'AI_BAD_OUTPUT'],
    [async () => ({ status: 500, json: async () => ({ error: KEY }) }), 'AI_FAILED'],
  ];
  for (const [fetchImpl, code] of cases) {
    await assert.rejects(deepseekExtract(cfg, 'prompt', fetchImpl), (error: unknown) => {
      assert.ok(error instanceof ExtractError);
      assert.equal(error.code, code);
      assert.equal(error.message.includes(KEY), false);
      assert.equal(JSON.stringify({ message: error.message, code: error.code }).includes(KEY), false);
      return true;
    });
  }
});
