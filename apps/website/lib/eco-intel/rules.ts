import type { AccountType, Ecosystem, TweetTopic } from './types';
import { ACCOUNT_TYPES, ECOSYSTEMS } from './types';

export class IntelError extends Error {
  constructor(readonly status: number, readonly code: string, message: string) {
    super(message);
  }
}

const SECRET_KEY = /token|secret|password|authorization|api[_-]?key|cookie|credential/i;

/** 新协议、发射台、黑客松（明确的链上新项目）建议升为种子并继续看推文。个人与无关只记录。 */
const PROMOTE_TYPES = new Set<AccountType>(['protocol', 'launchpad', 'hackathon']);

const TOPIC_RULES: { id: TweetTopic; pattern: RegExp }[] = [
  { id: 'hackathon', pattern: /黑客松/ },
  { id: 'launch', pattern: /上线/ },
  { id: 'protocol', pattern: /新协议/ },
  { id: 'launchpad', pattern: /发射/ },
  { id: 'raise', pattern: /融资/ },
];

export function normalizeHandle(raw: unknown): string | null {
  if (typeof raw !== 'string') return null;
  const value = raw.trim().replace(/^@+/, '');
  return /^[A-Za-z0-9_]{1,15}$/.test(value) ? value : null;
}

export function requireHandle(raw: unknown, field = 'X 用户名'): string {
  const handle = normalizeHandle(raw);
  if (!handle) throw new IntelError(422, 'VALIDATION_ERROR', `${field}须为 1–15 位英文、数字或下划线`);
  return handle;
}

export function ecosystemOf(raw: unknown): Ecosystem {
  if (typeof raw !== 'string' || !ECOSYSTEMS.some(item => item.id === raw)) {
    throw new IntelError(422, 'VALIDATION_ERROR', '生态分组无效');
  }
  return raw as Ecosystem;
}

export function accountTypeOf(raw: unknown): AccountType {
  if (typeof raw !== 'string' || !ACCOUNT_TYPES.some(item => item.id === raw)) {
    throw new IntelError(422, 'VALIDATION_ERROR', '账号类型无效');
  }
  return raw as AccountType;
}

export function followDisposition(accountType: AccountType): { promote_suggested: boolean; watch_tweets: boolean } {
  const watch = PROMOTE_TYPES.has(accountType);
  return { promote_suggested: watch, watch_tweets: watch };
}

export function classifyTweet(text: string): { topics: TweetTopic[]; push_to_feed: boolean } {
  const topics = TOPIC_RULES.filter(rule => rule.pattern.test(text)).map(rule => rule.id);
  return { topics, push_to_feed: topics.length > 0 };
}

export function boundedText(raw: unknown, max: number, field: string, required = false): string {
  if (raw === undefined || raw === null) {
    if (required) throw new IntelError(422, 'VALIDATION_ERROR', `请填写${field}`);
    return '';
  }
  if (typeof raw !== 'string') throw new IntelError(422, 'VALIDATION_ERROR', `${field}必须是文本`);
  const value = raw.trim();
  if (required && !value) throw new IntelError(422, 'VALIDATION_ERROR', `请填写${field}`);
  if ([...value].length > max) throw new IntelError(422, 'VALIDATION_ERROR', `${field}最长 ${max} 字`);
  return value;
}

export function normalizeUrl(raw: unknown): string {
  if (raw === undefined || raw === null || raw === '') return '';
  if (typeof raw !== 'string' || raw.length > 500) throw new IntelError(422, 'VALIDATION_ERROR', '链接无效');
  let url: URL;
  try { url = new URL(raw); } catch { throw new IntelError(422, 'VALIDATION_ERROR', '链接无效'); }
  if (url.protocol !== 'https:' || url.username || url.password) throw new IntelError(422, 'VALIDATION_ERROR', '链接须为 https');
  return url.toString();
}

export function optionalTimestamp(raw: unknown): string | null {
  if (raw === undefined || raw === null || raw === '') return null;
  if (typeof raw !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z$/.test(raw)) {
    throw new IntelError(422, 'VALIDATION_ERROR', '时间须为 UTC ISO 格式');
  }
  if (!Number.isFinite(Date.parse(raw))) throw new IntelError(422, 'VALIDATION_ERROR', '时间无效');
  return raw;
}

export function assertPublicPayload(payload: unknown): Record<string, unknown> {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new IntelError(422, 'VALIDATION_ERROR', '队列载荷必须是对象');
  }
  const record = payload as Record<string, unknown>;
  for (const key of Object.keys(record)) {
    if (SECRET_KEY.test(key)) throw new IntelError(422, 'VALIDATION_ERROR', '队列载荷不能包含凭据字段');
  }
  const json = JSON.stringify(record);
  if (json.length > 8000) throw new IntelError(422, 'VALIDATION_ERROR', '队列载荷过大');
  return record;
}

export const RULES_ANALYSIS = { engine: 'rules-v1', todo: 'wss-6551-and-ai' } as const;
