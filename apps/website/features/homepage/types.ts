// Page-owned projection of phase2-v1.0.0. Replace with approved shared type imports
// only after B0 propagation; this module has no runtime or transport dependency.
export const SITE_SCOPE = 'ikun-main' as const;
export const ratings = ['S', 'A', 'B'] as const;
export type ProjectRating = typeof ratings[number] | null;
export const progressStages = ['todo', 'researching', 'watching', 'participating', 'completed', 'paused'] as const;
export type ProgressStage = typeof progressStages[number];
export type HomeMembership = 'hidden' | 'active' | 'removed';
export interface ProjectFieldsProjection {
  name: string;
  rating: ProjectRating;
  description: string;
  website_url: string | null;
  notes: string;
  category: string | null;
  progress_stage: ProgressStage;
  progress_percent: number | null;
  token_date: string | null;
  token_date_status: 'confirmed' | 'estimated' | 'unconfirmed';
}
export interface ProjectRecordProjection extends ProjectFieldsProjection {
  project_id: string; // Supplied by Projects. UI never creates canonical IDs.
  home_membership: HomeMembership;
  discovered_at: string | null;
  revision: number;
  created_at: string;
  updated_at: string;
}
export interface PublicError {
  code: string;
  message: string;
  retryable: boolean;
  request_id: string | null;
}
export interface HomepageContext {
  mode: 'demo' | 'live';
  role?: 'user' | 'superadmin';
  capabilities?: {can_edit_projects?: boolean};
  request_id?: string | null;
}
export interface HomepageData {
  status: 'loading' | 'ready' | 'empty' | 'error';
  items: readonly ProjectRecordProjection[];
  next_cursor: string | null;
  refreshing?: boolean;
  error?: PublicError | null;
}
export interface ProjectRef {project_id: string; revision: number}
export type OperationState = 'accepted' | 'pending' | 'running' | 'succeeded' | 'failed' | 'unknown';
export interface OperationResult {
  state: OperationState;
  request_id: string | null;
  command_id?: string | null; // Caller-supplied only, never fabricated by UI.
  error?: PublicError | null;
}
export interface HomepageCallbacks {
  onCreate?: (fields: ProjectFieldsProjection) => Promise<OperationResult>;
  onUpdate?: (target: ProjectRef, fields: ProjectFieldsProjection) => Promise<OperationResult>;
  onMembership?: (target: ProjectRef, action: 'add' | 'remove') => Promise<OperationResult>;
  onDelete?: (target: ProjectRef) => Promise<OperationResult>; // DELETE means removed, never hard delete.
  onReconcile?: (operation: OperationResult) => Promise<OperationResult>;
  onQueryChange?: (query: HomepageQuery) => void;
  onNextPage?: (cursor: string) => void;
  onReload?: () => void;
}
export interface HomepageQuery {
  q: string;
  rating: 'all' | 'unrated' | typeof ratings[number];
  progress_stage: 'all' | ProgressStage;
  home_membership: HomeMembership;
}
export const initialQuery: HomepageQuery = {q:'', rating:'all', progress_stage:'all', home_membership:'active'};
export interface ProjectView {
  key: string;
  record: ProjectRecordProjection;
  discoveredLabel: string;
  progressLabel: string;
  percentLabel: string;
  tokenLabel: string;
  website: string | null;
}
