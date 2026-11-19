/** Shared time-extract rules for the website button. Codex stays the CLI path; DeepSeek is chat completions. */

export type CodexConfig = { provider: 'codex'; codexBin?: string; proxy?: string };
export type DeepSeekConfig = {
  provider: 'deepseek';
  apiKey: string;
  model: string;
  baseUrl: string;
  timeoutMs: number;
  proxy?: string;
};
export type AiConfig = CodexConfig | DeepSeekConfig;
export type TimeExtract = { date: string | null; hour: string | null; title: string; status: 'confirmed' | 'estimated' };

const KEY = /^[A-Za-z0-9_.-]{20,300}$/;
const MODEL = /^[A-Za-z0-9._-]{1,80}$/;
const BASE = /^https:\/\/[A-Za-z0-9.-]+(?::\d{1,5})?(?:\/[A-Za-z0-9._~/-]*)?$/;
const PROXY = /^(https?|socks5h?):\/\/[A-Za-z0-9.-]+:\d{1,5}$/;

export const DEEPSEEK_MODEL = 'deepseek-flash';
export const DEEPSEEK_BASE = 'https://api.deepseek.com';

export class ExtractError extends Error {
  status: number;
  code: string;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = 'ExtractError';
    this.status = status;
    this.code = code;
  }
}

function proxyOf(value: unknown) {
  return typeof value === 'string' && PROXY.test(value) ? value : undefined;
}

function envValue(env: object, key: string) {
  if (!(key in env)) return undefined;
  const value = (env as Record<string, unknown>)[key];
  return typeof value === 'string' ? value : undefined;
}

function deepseekKey(data: Record<string, unknown>, env: object) {
  for (const value of [envValue(env, 'DEEPSEEK_API_KEY'), data.deepseek_api_key, data.api_key]) {
    if (typeof value === 'string' && KEY.test(value)) return value;
  }
  return null;
}

/** Same gate the route uses. A missing or non-codex/deepseek provider stays unconfigured. */
export function configFrom(data: unknown, env: object = {}): AiConfig | null {
  if (!data || typeof data !== 'object' || Array.isArray(data)) return null;
  const row = data as Record<string, unknown>;
  if (row.enabled === false) return null;
  const proxy = proxyOf(row.proxy);
  if (row.provider === 'codex') {
    const binary = row.codex_bin;
    return { provider: 'codex', codexBin: typeof binary === 'string' && binary.startsWith('/') ? binary : undefined, proxy };
  }
  if (row.provider !== 'deepseek') return null;
  const apiKey = deepseekKey(row, env);
  if (!apiKey) return null;
  const model = typeof row.model === 'string' && MODEL.test(row.model) ? row.model : DEEPSEEK_MODEL;
  const baseUrl = typeof row.base_url === 'string' && BASE.test(row.base_url) ? row.base_url.replace(/\/+$/, '') : DEEPSEEK_BASE;
  const timeoutMs = typeof row.timeout === 'number' && row.timeout >= 1 && row.timeout <= 600 ? row.timeout * 1000 : 60_000;
  return { provider: 'deepseek', apiKey, model, baseUrl, timeoutMs, proxy };
}

export function unconfiguredMessage(data: unknown, env: object = {}) {
  if (data && typeof data === 'object' && !Array.isArray(data) && (data as { provider?: unknown }).provider === 'deepseek' && !deepseekKey(data as Record<string, unknown>, env)) {
    return 'DeepSeek 未配置密钥';
  }
  return 'AI 未启用（需在 ikun AI设置 里选 Codex 或 DeepSeek）';
}

export function deepseekEndpoint(baseUrl: string) {
  return baseUrl.endsWith('/chat/completions') ? baseUrl : `${baseUrl}/chat/completions`;
}

export function deepseekBody(model: string, prompt: string) {
  return {
    model,
    messages: [{ role: 'user', content: prompt }],
    response_format: { type: 'json_object' },
    thinking: { type: 'disabled' },
  };
}

/** Beijing wall clock, same UTC+8 shift the Codex prompt already used. */
export function beijingNow(now = Date.now()) {
  return new Date(now + 8 * 3600_000).toISOString().slice(0, 16).replace('T', ' ');
}

export function timePrompt(text: string, quote: string, receivedAt: string, nowLabel: string) {
  return `你是加密项目研究助手。从下面推文里找出项目即将发生的最重要时间点（如 TGE、发币、白名单、Mint、主网/测试网上线、空投快照）。\n` +
    `现在是北京时间 ${nowLabel}。把时间换算成北京时间（UTC+8）；"明天/今晚/周一"等相对时间按推文接收时间 ${receivedAt} 推算。\n` +
    `只输出一个 JSON：{"date":"YYYY-MM-DD 或 null","hour":"00-23 两位数 或 null（没写具体时刻就 null）","title":"不超过 20 字的中文事件说明","status":"confirmed（推文明确给出时间）或 estimated（推测/大概）"}。找不到时间就 date 为 null。不要运行任何命令。\n\n推文：${text}${quote ? `\n被引用推文：${quote}` : ''}`;
}

export function parseTimeJson(raw: string): TimeExtract {
  let text = raw.trim().replace(/^```(?:json)?\s*|\s*```$/g, '');
  const start = text.indexOf('{'), end = text.lastIndexOf('}');
  if (start >= 0 && end > start) text = text.slice(start, end + 1);
  const value = JSON.parse(text) as { date?: unknown; hour?: unknown; title?: unknown; status?: unknown };
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new ExtractError(502, 'AI_BAD_OUTPUT', 'AI 返回无法解析');
  const date = typeof value.date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value.date) ? value.date : null;
  const hour = date && typeof value.hour === 'string' && /^(?:[01]\d|2[0-3])$/.test(value.hour) ? value.hour : null;
  return {
    date,
    hour,
    title: typeof value.title === 'string' ? value.title.slice(0, 60) : '',
    status: value.status === 'confirmed' ? 'confirmed' : 'estimated',
  };
}

type FetchLike = (url: string, init: { method: string; headers: Record<string, string>; body: string; signal: AbortSignal }) => Promise<{ status: number; json: () => Promise<unknown> }>;

export async function deepseekExtract(cfg: DeepSeekConfig, prompt: string, fetchImpl: FetchLike): Promise<TimeExtract> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), cfg.timeoutMs);
  try {
    const response = await fetchImpl(deepseekEndpoint(cfg.baseUrl), {
      method: 'POST',
      headers: { authorization: `Bearer ${cfg.apiKey}`, 'content-type': 'application/json' },
      body: JSON.stringify(deepseekBody(cfg.model, prompt)),
      signal: controller.signal,
    });
    if (response.status === 401 || response.status === 403) throw new ExtractError(502, 'AI_KEY_REJECTED', 'DeepSeek 拒绝了密钥');
    if (response.status !== 200) throw new ExtractError(502, 'AI_FAILED', 'AI 识别失败，请稍后再试或手动填写');
    let payload: unknown;
    try { payload = await response.json(); } catch { throw new ExtractError(502, 'AI_BAD_OUTPUT', 'AI 返回无法解析'); }
    const content = (payload as { choices?: { message?: { content?: unknown } }[] } | null)?.choices?.[0]?.message?.content;
    if (typeof content !== 'string') throw new ExtractError(502, 'AI_BAD_OUTPUT', 'AI 返回无法解析');
    try { return parseTimeJson(content); } catch (error) {
      if (error instanceof ExtractError) throw error;
      throw new ExtractError(502, 'AI_BAD_OUTPUT', 'AI 返回无法解析');
    }
  } catch (error) {
    if (error instanceof ExtractError) throw error;
    const name = error instanceof Error ? error.name : '';
    if (name === 'AbortError' || name === 'TimeoutError') throw new ExtractError(504, 'AI_TIMEOUT', 'AI 识别超时，请稍后再试或手动填写');
    throw new ExtractError(502, 'AI_FAILED', 'AI 识别失败，请稍后再试或手动填写');
  } finally {
    clearTimeout(timer);
  }
}

type Assert<T extends true> = T;
type _processEnvFits = Assert<NodeJS.ProcessEnv extends Parameters<typeof configFrom>[1] ? true : never>;
type _emptyEnvFits = Assert<Record<string, never> extends Parameters<typeof configFrom>[1] ? true : never>;
type _processEnvMessageFits = Assert<NodeJS.ProcessEnv extends Parameters<typeof unconfiguredMessage>[1] ? true : never>;
type _emptyMessageFits = Assert<Record<string, never> extends Parameters<typeof unconfiguredMessage>[1] ? true : never>;
