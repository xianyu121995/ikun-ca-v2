import { createHash } from 'node:crypto';

/** Same id the tracking BFF derives for POST /api/v1/tracking/subscriptions. */
export function commandId(actor: string, route: string, key: string) {
  const bytes = createHash('sha256').update(JSON.stringify([actor, 'ikun-main', route, key])).digest().subarray(0, 16);
  bytes[6] = (bytes[6]! & 15) | 64;
  bytes[8] = (bytes[8]! & 63) | 128;
  const hex = bytes.toString('hex');
  return 'cmd_' + [hex.slice(0, 8), hex.slice(8, 12), hex.slice(12, 16), hex.slice(16, 20), hex.slice(20)].join('-');
}

export const TRACKING_CREATE_ROUTE = 'POST /api/v1/tracking/subscriptions';

/**
 * Command envelope posted to Tracking after Projects resolves a canonical project.
 * Field order matches the historical object in tracking.ts so JSON.stringify stays stable.
 * Hunter 项目追踪 reaches this same operation via hunter.monitoring_requested → projects outbox.
 */
export function trackingCreateCommand<TActor extends { user_id: string }>(input: {
  actor: TActor;
  route?: string;
  idempotencyKey: string;
  projectId: string | null;
  name: unknown;
  xUserId: unknown;
  xHandle: unknown;
  notes: unknown;
  issuedAt: string;
}) {
  return {
    schema_version: 1 as const,
    command_id: commandId(input.actor.user_id, input.route ?? TRACKING_CREATE_ROUTE, input.idempotencyKey),
    tenant_id: 'ikun-main' as const,
    actor: input.actor,
    operation: 'tracking.create' as const,
    project_id: input.projectId,
    subscription_id: null,
    expected_revision: null,
    payload: {
      name: input.name,
      x_user_id: input.xUserId ?? null,
      x_handle: input.xHandle,
      notes: input.notes ?? '',
      confirmed: true as const,
    },
    issued_at: input.issuedAt,
  };
}

export type TrackingCreateCommand = ReturnType<typeof trackingCreateCommand>;
