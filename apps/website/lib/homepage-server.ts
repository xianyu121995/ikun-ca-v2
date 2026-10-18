import type {ReactNode} from 'react';
export interface ServerHomepage {
  mainIds:readonly string[];completedIds:readonly string[];otherIds:readonly string[];eventIds:readonly string[];
  total:number;page:number;hasNext:boolean;pageSize?:number;
  xHandles?:Readonly<Record<string,string>>;
  /** Owner 2026-10-19: inline edit of progress / important time; last save wins. Returns an error message or null. */
  onQuickEdit?:(projectId:string,body:{fields?:Record<string,unknown>;milestone?:{date:string|null;hour:string|null;title:string;status:'confirmed'|'estimated'|'unconfirmed'}})=>Promise<string|null>;
  summary:{tracked_total:number;by_rating:{S:number;A:number;B:number};completed_total:number;other_total:number};
  onSort:(value:{key:string;direction:'asc'|'desc'})=>void;
  canPage:(page:number)=>boolean;onPage:(page:number)=>void;onWindow:(window:string)=>void;onDetail:(id:string)=>void;
  completedPagination:ReactNode;otherPagination:ReactNode;
}
