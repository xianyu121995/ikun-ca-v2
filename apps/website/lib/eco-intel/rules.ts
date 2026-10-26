import type { AccountType, Ecosystem, FollowAiSuggestion, FollowClassification, TrackChain, TweetTopic } from './types';
import { ACCOUNT_TYPES, ECOSYSTEMS, TRACK_CHAINS, isTrackChain, labelOf } from './types';

export class IntelError extends Error {
  constructor(readonly status: number, readonly code: string, message: string) {
    super(message);
  }
}

const SECRET_KEY = /token|secret|password|authorization|api[_-]?key|cookie|credential/i;

/** Project types eligible for a human 「项目追踪」 click. Nothing here auto-enters hunter. */
const PROJECT_TYPES = new Set<AccountType>(['protocol', 'launchpad', 'hackathon']);
/** Logged on the follow stream only. Token is included and never auto-promotes. */
const NOISE_TYPES = new Set<AccountType>(['token', 'kol', 'media', 'exchange', 'personal', 'airdrop', 'brand', 'founder', 'official', 'unrelated']);

const INFER_TYPES: { type: AccountType; pattern: RegExp }[] = [
  { type: 'token', pattern: /memecoin|meme\s*coin|个人代币|土狗|\btoken\b|代币/i },
  { type: 'airdrop', pattern: /airdrop|空投/i },
  { type: 'exchange', pattern: /\bexchange\b|交易所/i },
  { type: 'kol', pattern: /\bkol\b|意见领袖|博主/i },
  { type: 'media', pattern: /\bnews\b|媒体|新闻/i },
  { type: 'hackathon', pattern: /hackathon|黑客松/i },
  { type: 'launchpad', pattern: /launchpad|发射台|发射平台/i },
  { type: 'protocol', pattern: /\bprotocol\b|协议|\bdefi\b|预言机|\boracle\b|跨链桥|\bbridge\b|\bl2\b|layer\s*2|钱包基础设施/i },
];

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

export function trackChainOf(raw: unknown): TrackChain | '' {
  if (raw === undefined || raw === null || raw === '') return '';
  if (typeof raw === 'string' && isTrackChain(raw)) return raw;
  throw new IntelError(422, 'VALIDATION_ERROR', '链只能是 BSC、Solana、ETH、Base 或 Robinhood Chain');
}

export function inferAccountType(bio: string, summary: string): AccountType | null {
  const text = `${bio}\n${summary}`;
  return INFER_TYPES.find(rule => rule.pattern.test(text))?.type ?? null;
}

/** A single clear chain mention. Two or more chains stay unresolved. */
export function inferChain(text: string): TrackChain | '' {
  const value = text.toLowerCase();
  const hits: TrackChain[] = [];
  if (/robinhood/.test(value)) hits.push('robinhood');
  if (/base chain|\bon base\b/.test(value)) hits.push('base');
  if (/solana/.test(value)) hits.push('solana');
  if (/ethereum|\bon eth\b|\beth\b/.test(value)) hits.push('eth');
  if (/bnb chain|bnbchain|\bbsc\b|binance smart chain/.test(value)) hits.push('bsc');
  return hits.length === 1 ? hits[0] : '';
}

export function isProjectType(accountType: AccountType): boolean {
  return PROJECT_TYPES.has(accountType);
}

export interface FollowClass {
  accountType: AccountType;
  chain: TrackChain | '';
  classification: FollowClassification;
  promote_suggested: boolean;
  watch_tweets: boolean;
  track_eligible: boolean;
  /** Local rules never enqueue hunter. A person clicks 项目追踪. */
  auto_track: false;
}

/**
 * Project: protocol / launchpad / hackathon tied to one of the five chains.
 * Token and the other noise types never auto-promote and are not track-eligible.
 * Unclear type or chain → pending. Pending can be tracked by a person, never automatically.
 */
export function classifyFollow(input: {
  accountType: AccountType;
  chain: TrackChain | '';
  bio: string;
  recentSummary: string;
}): FollowClass {
  const text = `${input.bio}\n${input.recentSummary}`;
  const accountType = input.accountType === 'unclassified' ? (inferAccountType(input.bio, input.recentSummary) ?? 'unclassified') : input.accountType;
  const chain = input.chain || inferChain(text);
  const auto_track = false as const;
  if (accountType === 'token' || NOISE_TYPES.has(accountType)) {
    return { accountType, chain, classification: 'noise', promote_suggested: false, watch_tweets: false, track_eligible: false, auto_track };
  }
  if (PROJECT_TYPES.has(accountType) && chain && isTrackChain(chain)) {
    return { accountType, chain, classification: 'project', promote_suggested: true, watch_tweets: true, track_eligible: true, auto_track };
  }
  return { accountType, chain, classification: 'pending', promote_suggested: false, watch_tweets: false, track_eligible: true, auto_track };
}

export function followDisposition(accountType: AccountType, chain: TrackChain | '' = '') {
  return classifyFollow({ accountType, chain, bio: '', recentSummary: '' });
}

const NAME_CHAIN: Record<TrackChain, string> = {
  bsc: 'BSC',
  solana: 'SOL',
  eth: 'ETH',
  base: 'Base',
  robinhood: 'RH',
};

/**
 * Draft shown when 编辑 opens. Mirrors hunter `withAi`: fill the popup, never save until the person clicks 保存.
 * Discovery stays on classifyFollow. Hunter's worker cache is not read (it calls 6551).
 */
export function suggestFollow(input: { handle: string; displayName: string; bio: string; recentSummary: string }): FollowAiSuggestion {
  const guessed = classifyFollow({ accountType: 'unclassified', chain: '', bio: input.bio, recentSummary: input.recentSummary });
  const typeLabel = labelOf(ACCOUNT_TYPES, guessed.accountType);
  const chainLabel = guessed.chain ? labelOf(TRACK_CHAINS, guessed.chain) : '';
  const fallback = input.displayName.trim() || input.handle;
  const name = guessed.classification === 'project' && guessed.chain
    ? `${NAME_CHAIN[guessed.chain]}上的${typeLabel}`.slice(0, 16)
    : fallback;
  const description = guessed.accountType === 'token'
    ? '简介指向代币。代币只记录，不会自动进入项目追踪。'
    : guessed.classification === 'project'
      ? `简介显示这是${chainLabel}上的${typeLabel}。请核对后再保存，不会自动加入猎手。`
      : guessed.classification === 'noise'
        ? `简介指向${typeLabel}，只记在关注流里，不进入项目追踪。`
        : '简介不足以判断类型或链，记为待定。可以手工点项目追踪，不会自动加入猎手。';
  return {
    name,
    account_type: guessed.accountType,
    chain: guessed.chain,
    notes: description,
    description,
    engine: 'eco-rules',
  };
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
