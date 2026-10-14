/** Foundation contract v1. No storage, provider SDK or browser credentials here. */
export const API_VERSION = "v1" as const;
export type ServiceName = "website" | "hunter" | "tracking";
export type StoreName = "projects" | "auth" | "hunter" | "tracking";
export type Role = "superadmin" | "user";
export type ProjectId = string & { readonly __projectId: unique symbol };
export type ErrorCode =
  | "VALIDATION_ERROR" | "UNAUTHENTICATED" | "FORBIDDEN" | "NOT_FOUND"
  | "CONFLICT" | "IDEMPOTENCY_CONFLICT" | "VERSION_CONFLICT" | "RATE_LIMITED"
  | "UPSTREAM_TIMEOUT" | "UPSTREAM_UNAVAILABLE" | "DB_UNAVAILABLE"
  | "AUTH_NOT_CONFIGURED" | "NOT_IMPLEMENTED" | "INTERNAL_ERROR";
export interface ApiError {
  error: { code: ErrorCode; message: string; retryable: boolean };
  request_id: string;
}
export interface ApiSuccess<T> { data: T; request_id: string }
export interface Page<T> { items: T[]; next_cursor: string | null }
export interface Principal { user_id: string; tenant_id: string; role: Role }
/** Sanitized DTO, never include individual Hunter identities or raw payloads. */
export interface ProjectSummary {
  project_id: ProjectId; name: string; status: "active" | "archived";
  revision: number; updated_at: string;
}
/** Transport envelope only. Business schemas remain the owning module's work. */
export interface EventEnvelope<T> {
  schema_version: 1; event_id: string; source: "hunter" | "tracking";
  event_type: string; occurred_at: string; received_at: string;
  tenant_id: string; project_id: ProjectId | null;
  correlation_id: string; payload: T;
}
export function parseProjectId(value: string): ProjectId {
  if (!/^prj_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(value)) {
    throw new TypeError("Invalid project_id");
  }
  return value as ProjectId;
}
export function newProjectId(): ProjectId {
  return parseProjectId(`prj_${globalThis.crypto.randomUUID()}`);
}
