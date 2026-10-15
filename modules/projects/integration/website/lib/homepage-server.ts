import type {ReactNode} from 'react';
export interface ServerHomepage {
  mainIds:readonly string[];completedIds:readonly string[];otherIds:readonly string[];eventIds:readonly string[];
  total:number;page:number;hasNext:boolean;
  summary:{tracked_total:number;by_rating:{S:number;A:number;B:number};completed_total:number;other_total:number};
  onSort:(value:{key:string;direction:'asc'|'desc'})=>void;
  onPage:(page:number)=>void;onWindow:(window:string)=>void;onDetail:(id:string)=>void;
  completedPagination:ReactNode;otherPagination:ReactNode;
}
