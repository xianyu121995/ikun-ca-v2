import type { TrackingCreateCommand } from '../tracking-command';

/** Body accepted by POST /api/v1/tracking/subscriptions, without inventing a second tracker. */
export interface TrackingHandoff {
  actorId: string;
  requestId: string;
  idempotencyKey: string;
  body: {
    name: string;
    x_handle: string;
    x_user_id: string | null;
    notes: string;
    confirmed: true;
    project_id?: string;
  };
  signal?: AbortSignal;
}

export interface TrackingHandoffResult {
  ok: boolean;
  status: number;
  command: TrackingCreateCommand | null;
  remoteState: string;
  error: string;
}

export type TrackingSubmitter = (input: TrackingHandoff) => Promise<TrackingHandoffResult>;
