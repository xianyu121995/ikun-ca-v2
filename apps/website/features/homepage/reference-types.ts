import type {ServerHomepage} from '../../lib/homepage-server';
import type {HomepageCallbacks,HomepageContext,HomepageData,OperationResult,ProgressStage,ProjectFieldsProjection,ProjectRef} from './types';

// Page-only presentation inputs. These do not extend the frozen Projects API/DTO.
export interface ProjectMilestone {
  project_id:string;
  date:string|null;
  hour:string|null; // Zero-padded 00..23, Asia/Shanghai; null stays unknown.
  title:string;
  status:'confirmed'|'estimated'|'unconfirmed';
}
export interface EditorDraft {fields:ProjectFieldsProjection;milestone:Omit<ProjectMilestone,'project_id'>;archive_after_save:boolean}
export interface ArchiveNote {project_id:string;previous_stage:ProgressStage;completed_on:string|null}
export interface ReferenceCallbacks extends HomepageCallbacks {
  onCreateDraft?:(draft:EditorDraft)=>Promise<OperationResult>;
  onUpdateDraft?:(target:ProjectRef,draft:EditorDraft)=>Promise<OperationResult>;
  // Explicit UI intent. A future domain adapter must implement its own authorized operation.
  onArchive?:(targets:readonly ProjectRef[])=>Promise<OperationResult>;
  onRestore?:(target:ProjectRef)=>Promise<OperationResult>;
  onDiscoveryDateChange?:(date:string|null)=>void; // Page-only calendar filter, not a frozen API field.
}
export interface ReferenceHomepageProps {
  server?:ServerHomepage;
  context:HomepageContext;
  data:HomepageData;
  callbacks?:ReferenceCallbacks;
  milestones?:readonly ProjectMilestone[];
  archiveNotes?:readonly ArchiveNote[];
  asOfDate?:string; // Supplied calendar date; no fabricated live clock or dates.
}
