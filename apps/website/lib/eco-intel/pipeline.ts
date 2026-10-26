import { assertPublicPayload } from './rules';
import type { IntelStore } from './store';
import type { QueueKind, QueueRecord } from './types';

/**
 * Later pipeline: 6551 WSS event → intel_ingest_queue → AI analysis → tweets / follows.
 * TODO(6551): subscribe in a dedicated worker. This skeleton performs no network I/O
 * and must not call 6551, twitterapi, or the hunter Watch.
 *
 * AI input reserved on intel_follows: handle, bio, recent_summary, seed_handle.
 * Account types: 官方 / 发射台 / 黑客松项目 / 新协议 / 新币·memecoin / 创始人个人 / 无关.
 * Promote + keep watching tweets: 新协议, 发射台, 明确链上新项目 (hackathon).
 * Personal and noise: log only.
 * Seed tweets that mention 黑客松 / 上线 / 新协议 / 发射 / 融资 set push_to_feed.
 */
export function acceptProviderEvent(store: IntelStore, kind: Extract<QueueKind, 'wss_follow' | 'wss_tweet'>, payload: unknown): QueueRecord {
  return store.enqueue(kind, assertPublicPayload(payload));
}
