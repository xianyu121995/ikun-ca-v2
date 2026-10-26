import { submitTrackingCreate } from '../tracking';
import type { TrackingHandoff, TrackingHandoffResult } from './tracking';

/**
 * 「项目追踪」uses the same projects tracking_register + tracking.create command as
 * POST /api/v1/tracking/subscriptions. Hunter's confirmed monitoring request becomes
 * that same command after projects ingest; this calls the website function that builds it.
 * TODO(6551): do not open a provider socket here. Live monitors stay inside the tracking worker.
 */
export async function submitIntelTracking(input: TrackingHandoff): Promise<TrackingHandoffResult> {
  const body: Record<string, unknown> = {
    name: input.body.name,
    x_handle: input.body.x_handle,
    x_user_id: input.body.x_user_id,
    notes: input.body.notes,
    confirmed: true,
  };
  if (input.body.project_id) body.project_id = input.body.project_id;
  const submitted = await submitTrackingCreate(
    { user_id: input.actorId, tenant_id: 'ikun-main', role: 'superadmin' },
    input.requestId,
    input.idempotencyKey,
    body,
    input.signal,
  );
  type TrackingReply = { data?: { state?: unknown }; error?: { message?: unknown } };
  let payload: TrackingReply | null = null;
  try { payload = await submitted.response.clone().json() as TrackingReply; } catch { payload = null; }
  if (submitted.response.ok) {
    const remoteState = typeof payload?.data?.state === 'string' ? payload.data.state : 'accepted';
    return { ok: true, status: submitted.response.status, command: submitted.command, remoteState, error: '' };
  }
  const error = typeof payload?.error?.message === 'string' ? payload.error.message : `追踪投递未完成（${submitted.response.status}）`;
  return { ok: false, status: submitted.response.status, command: submitted.command, remoteState: '', error };
}
