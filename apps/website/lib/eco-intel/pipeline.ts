import { assertPublicPayload } from './rules';
import type { IntelStore } from './store';
import type { QueueKind, QueueRecord } from './types';

/**
 * Later pipeline: 6551 WSS event → intel_ingest_queue → AI analysis → tweets / follows.
 * TODO(6551): subscribe in a dedicated worker. This skeleton performs no network I/O
 * and must not call 6551, twitterapi, or the hunter Watch.
 *
 * AI input reserved on intel_follows: handle, bio, recent_summary, seed_handle, chain.
 * A follow is a project only for protocol / launchpad / hackathon tied to BSC, Solana, ETH, Base, or Robinhood Chain.
 * Token, KOL, media, exchange, personal, airdrop, and unrelated brands stay on the follow log.
 * Token never auto-promotes and never auto-enters hunter. Unclear bios stay pending.
 * 「项目追踪」enqueues tracking.create through the existing projects/tracking path. Nothing here auto-clicks it.
 * Seed tweets that mention 黑客松 / 上线 / 新协议 / 发射 / 融资 set push_to_feed.
 */
export function acceptProviderEvent(store: IntelStore, kind: Extract<QueueKind, 'wss_follow' | 'wss_tweet'>, payload: unknown): QueueRecord {
  return store.enqueue(kind, assertPublicPayload(payload));
}
