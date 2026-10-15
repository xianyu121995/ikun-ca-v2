/** Frozen phase-2 transport types. No business logic, storage or SDK integration. */
import type { ProjectId, Role } from "./index.js";

export const PHASE2_CONTRACT_VERSION = "phase2-v1.0.0" as const;
export const SITE_SCOPE = "ikun-main" as const;
export type SiteScope = typeof SITE_SCOPE;
export type SubscriptionId = string & { readonly __subscriptionId: unique symbol };
export type CommandId = string & { readonly __commandId: unique symbol };
export type ProjectRating = "S" | "A" | "B" | "C" | "D" | null;
export type ProgressStage = "todo" | "researching" | "watching" | "participating" | "completed" | "paused";
export type HomeMembership = "hidden" | "active" | "removed";
export type CommandState = "accepted" | "pending" | "running" | "succeeded" | "failed" | "unknown";
export interface AuthPrincipalV2 { user_id: string; tenant_id: SiteScope; role: Role }
export interface CapabilitiesV2 {
  can_edit_projects: boolean; can_manage_hunter: boolean;
  can_manage_tracking: boolean; can_manage_users: boolean;
}
export interface AuthSessionV2 extends AuthPrincipalV2 {
  username: string; must_change_password: boolean; csrf_token: string;
  capabilities: CapabilitiesV2;
}
export interface AuthUserV2 {
  user_id: string; username: string; role: Role; enabled: boolean;
  must_change_password: boolean; revision: number; created_at: string; updated_at: string;
}
export interface PageV2<T> { items: T[]; next_cursor: string | null }
export interface ProjectFieldsV2 {
  name: string; rating: ProjectRating; description: string;
  website_url: string | null; notes: string; category: string | null;
  progress_stage: ProgressStage; progress_percent: number | null;
  token_date: string | null;
  token_date_status: "confirmed" | "estimated" | "unconfirmed";
}
export interface ProjectRecordV2 extends ProjectFieldsV2 {
  project_id: ProjectId; home_membership: HomeMembership;
  discovered_at: string | null; revision: number; created_at: string; updated_at: string;
}
export interface SubscriptionRecordV2 {
  subscription_id: SubscriptionId; project_id: ProjectId; name: string;
  x_user_id: string | null; x_handle: string; notes: string; revision: number;
  desired_state: "running" | "stopped" | "removed";
  observed_state: "unknown" | "running" | "stopped" | "absent";
  operation_state: CommandState; connection: "unconfigured" | "connecting" | "connected" | "disconnected";
  last_tweet_at: string | null; created_at: string; updated_at: string;
}
export interface HunterDiscoveryV2 {
  discovery_id: string; project_id: ProjectId | null; project: ProjectFieldsV2;
  x_user_id: string | null; x_handle: string; profile_bio: string; followers: number | null;
  signal_count: number; first_seen_at: string | null; last_seen_at: string | null;
  discovered_at: string | null; review_state: "pending" | "reviewed" | "tracking" | "ignored";
  monitoring_state: CommandState | null; revision: number;
}
export interface HunterAccountV2 {
  account_id: string; x_handle: string; label: string; notes: string;
  enabled: boolean; baseline_ready: boolean;
  connection: "unconfigured" | "connecting" | "connected" | "disconnected";
  last_signal_at: string | null; revision: number;
}
export interface TrackingActivityV2 {
  activity_id: string; subscription_id: SubscriptionId; project_id: ProjectId;
  project_name: string; tweet_id: string; x_handle: string; text: string; url: string;
  occurred_at: string | null; received_at: string; source: "wss" | "rest"; generation: number;
}
export interface MonitoringRequestPayloadV2 {
  command_id: CommandId; discovery_id: string; source_entity_key: string; confirmed: true;
  actor: AuthPrincipalV2 & { role: "superadmin" }; project: ProjectFieldsV2;
  x_user_id: string | null; x_handle: string;
}
export interface EventEnvelopeV2<T> {
  schema_version: 1; event_id: string; source: "hunter" | "tracking";
  event_type: string; occurred_at: string | null; received_at: string;
  tenant_id: SiteScope; project_id: ProjectId | null; correlation_id: string; payload: T;
}
export interface EventReceiptV2 {
  event_id: string; project_id: ProjectId | null; receipt_id: string;
  accepted_at: string; duplicate: boolean; command_id: CommandId | null;
}
export interface CommandEnvelopeV2 {
  schema_version: 1; command_id: CommandId; tenant_id: SiteScope;
  actor: AuthPrincipalV2 & { role: "superadmin" }; operation: "tracking.create" | "tracking.start" | "tracking.stop" | "tracking.resume" | "tracking.remove";
  project_id: ProjectId; subscription_id: SubscriptionId | null;
  expected_revision: number | null; payload: Record<string, unknown>; issued_at: string;
}
export interface CommandResultV2 {
  command_id: CommandId; state: CommandState; project_id: ProjectId | null;
  subscription_id: SubscriptionId | null; revision: number | null;
  updated_at: string; error_code: string | null; request_id: string;
}
/** UI owns presentation only; handlers and truthful capability/state come from its caller. */
export interface UiContextV2 {
  mode: "demo" | "live"; role: Role; capabilities: CapabilitiesV2;
  request_id: string | null;
}
