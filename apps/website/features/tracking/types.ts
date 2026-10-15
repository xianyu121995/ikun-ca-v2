/** UI-only structural projections of phase2-v1.0.0. Shared type propagation awaits B0. */
export type OperationState = "accepted" | "pending" | "running" | "succeeded" | "failed" | "unknown";
export interface SubscriptionDTO {
  subscription_id: string; project_id: string; name: string;
  x_user_id: string | null; x_handle: string; notes: string; revision: number;
  desired_state: "running" | "stopped" | "removed";
  observed_state: "unknown" | "running" | "stopped" | "absent";
  operation_state: OperationState;
  connection: "unconfigured" | "connecting" | "connected" | "disconnected";
  last_tweet_at: string | null; created_at: string; updated_at: string;
}
export interface ActivityDTO {
  activity_id: string; subscription_id: string; project_id: string;
  project_name: string; tweet_id: string; x_handle: string; text: string; url: string;
  occurred_at: string | null; received_at: string; source: "wss" | "rest"; generation: number;
}
export interface CommandDTO {
  command_id: string; state: OperationState; project_id: string | null;
  subscription_id: string | null; revision: number | null; updated_at: string;
  error_code: string | null; request_id: string;
}
export interface PublicError { code: string; message: string; retryable: boolean; request_id: string }
export interface ProjectChoice { project_id: string; name: string; x_handle: string }
export type MonitorOperation = "start" | "stop" | "resume" | "remove";
export interface ActionInput { subscription_id: string; project_id: string; operation: MonitorOperation; revision: number }
export interface AddInput { project_id: string; name: string; x_handle: string; x_user_id: null; notes: string; confirmed: true }
export interface TrackingProps {
  mode: "demo" | "live";
  role?: "user" | "superadmin";
  capabilities?: { can_manage_tracking?: boolean };
  subscriptions: SubscriptionDTO[];
  activities: ActivityDTO[];
  projects?: ProjectChoice[];
  loading?: boolean; refreshing?: boolean; error?: PublicError | null;
  onRefresh?: () => Promise<void>;
  onAction?: (input: ActionInput) => Promise<CommandDTO>;
  onAdd?: (input: AddInput) => Promise<CommandDTO>;
  onReconcile?: (subscription_id: string, command_id: string | null) => Promise<void>;
  onReconcileAdd?: (project_id: string, command_id: string | null) => Promise<void>;
  /** Caller supplies page actions; the single shared AppShell stays outside this view. */
  toolbarSlot?: import("react").ReactNode;
}
