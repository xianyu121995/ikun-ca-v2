export const ECOSYSTEMS = [
  { id: 'bsc', label: 'BSC' },
  { id: 'solana', label: 'Solana' },
  { id: 'eth', label: 'ETH' },
  { id: 'base', label: 'Base' },
  { id: 'robinhood', label: 'Robinhood' },
  { id: 'other', label: '其他' },
] as const;
export type Ecosystem = (typeof ECOSYSTEMS)[number]['id'];

export const ACCOUNT_TYPES = [
  { id: 'official', label: '官方' },
  { id: 'launchpad', label: '发射台' },
  { id: 'hackathon', label: '黑客松项目' },
  { id: 'protocol', label: '新协议' },
  { id: 'token', label: '新币·memecoin' },
  { id: 'founder', label: '创始人个人' },
  { id: 'unrelated', label: '无关' },
  { id: 'unclassified', label: '待分析' },
] as const;
export type AccountType = (typeof ACCOUNT_TYPES)[number]['id'];

export const TWEET_TOPICS = [
  { id: 'hackathon', label: '黑客松' },
  { id: 'launch', label: '上线' },
  { id: 'protocol', label: '新协议' },
  { id: 'launchpad', label: '发射' },
  { id: 'raise', label: '融资' },
] as const;
export type TweetTopic = (typeof TWEET_TOPICS)[number]['id'];

export type SeedSource = 'fixture' | 'manual' | 'promoted';
export type ActivitySource = 'stub' | 'manual' | 'wss' | 'rest';
export type FollowStatus = 'open' | 'promoted' | 'dismissed';
export type QueueKind = 'wss_follow' | 'wss_tweet' | 'ai_analyze';

export interface SeedRecord {
  seed_id: string;
  x_handle: string;
  ecosystem: Ecosystem;
  role_label: string;
  notes: string;
  enabled: boolean;
  source: SeedSource;
  revision: number;
  created_at: string;
  updated_at: string;
}

export interface TweetRecord {
  tweet_id: string;
  seed_id: string | null;
  x_handle: string;
  text: string;
  url: string;
  occurred_at: string | null;
  received_at: string;
  topics: TweetTopic[];
  push_to_feed: boolean;
  source: ActivitySource;
  analysis_status: 'pending' | 'skipped' | 'done';
  analysis: { engine: string; todo: string };
  created_at: string;
}

export interface FollowRecord {
  follow_id: string;
  seed_id: string | null;
  seed_handle: string;
  x_handle: string;
  display_name: string;
  bio: string;
  recent_summary: string;
  account_type: AccountType;
  promote_suggested: boolean;
  watch_tweets: boolean;
  promoted_seed_id: string | null;
  notes: string;
  status: FollowStatus;
  source: 'stub' | 'manual' | 'wss';
  revision: number;
  occurred_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface QueueRecord {
  queue_id: string;
  kind: QueueKind;
  status: 'pending' | 'processing' | 'done' | 'failed' | 'skipped';
  attempts: number;
  created_at: string;
}

export interface IntelPage<T> {
  items: T[];
  next_cursor: string | null;
}

export interface IntelPrincipal {
  user_id: string;
  role: 'superadmin' | 'user';
}

export function labelOf<T extends { id: string; label: string }>(rows: readonly T[], id: string): string {
  return rows.find(row => row.id === id)?.label ?? id;
}
