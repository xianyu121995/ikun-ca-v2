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
/** Page-only row from the tracking timeline pass. Not a Projects DTO. */
export interface AiTimelineEntry {
  entry_id:string;
  project_id:string;
  project_name:string;
  rating:'S'|'A'|'B'|'C'|'D'|null;
  event_type:string;
  title:string;
  date:string;
  hour:string|null;
  status:'confirmed'|'estimated';
  source_url:string|null;
  source_tweet_id:string;
  confidence:number;
}
export interface AiTimelinePatch {date:string;hour:string|null;title:string;status:'confirmed'|'estimated'}
export interface EditorDraft {fields:ProjectFieldsProjection;milestone:Omit<ProjectMilestone,'project_id'>;archive_after_save:boolean}
export interface ArchiveNote {project_id:string;previous_stage:ProgressStage;completed_on:string|null}
export interface ReferenceCallbacks extends HomepageCallbacks {
  onCreateDraft?:(draft:EditorDraft)=>Promise<OperationResult>;
  onUpdateDraft?:(target:ProjectRef,draft:EditorDraft)=>Promise<OperationResult>;
  // Explicit UI intent. A future domain adapter must implement its own authorized operation.
  onArchive?:(targets:readonly ProjectRef[])=>Promise<OperationResult>;
  onRestore?:(target:ProjectRef)=>Promise<OperationResult>;
  onDiscoveryDateChange?:(date:string|null)=>void; // Page-only calendar filter, not a frozen API field.
  onAiUpdate?:(entry:AiTimelineEntry,patch:AiTimelinePatch)=>Promise<string|null>;
  onAiDelete?:(entry:AiTimelineEntry)=>Promise<string|null>;
}
export interface ReferenceHomepageProps {
  server?:ServerHomepage;
  context:HomepageContext;
  data:HomepageData;
  callbacks?:ReferenceCallbacks;
  milestones?:readonly ProjectMilestone[];
  aiEntries?:readonly AiTimelineEntry[];
  archiveNotes?:readonly ArchiveNote[];
  asOfDate?:string; // Supplied calendar date; no fabricated live clock or dates.
}
