export const grades = ['S','A','B','C','待定'] as const;
export const stages = ['研究中','准备中','进行中','已完成','已暂停'] as const;
export const categories = ['基础设施','DeFi','AI × Crypto','游戏','社交','其他'] as const;
export type Grade = typeof grades[number];
export type Stage = typeof stages[number];
export interface ProjectRecord {
  id: string;
  name: string;
  grade: Grade;
  discoveredOn: string; // YYYY-MM-DD; Beijing calendar date, not an instant.
  website: string;
  description: string;
  category: string;
  stage: Stage;
  progress: number;
  notes: string;
  membership: 'active' | 'removed';
  isDemo: boolean;
}
export interface ProjectSnapshot {revision:number;items:ProjectRecord[]}
// Function window can replace this adapter without changing table/editing interactions.
export interface HomepageProjectStore {
  load(): ProjectSnapshot;
  commit(items:ProjectRecord[],expectedRevision:number): ProjectSnapshot;
  reset(expectedRevision:number): ProjectSnapshot;
  subscribe(listener:(snapshot:ProjectSnapshot)=>void): ()=>void;
}
export function safeWebsite(value:string):string|null {
  if (!value.trim()) return null;
  try {const url=new URL(value);return ['https:','http:'].includes(url.protocol)&&!url.username&&!url.password?url.href:null;}catch{return null;}
}
export function isSnapshot(value:unknown):value is ProjectSnapshot {
  if(!value||typeof value!=='object')return false;
  const s=value as ProjectSnapshot;
  return Number.isSafeInteger(s.revision)&&s.revision>=0&&Array.isArray(s.items)&&s.items.length<=5000&&new Set(s.items.map(p=>p?.id)).size===s.items.length&&s.items.every(p=>
    p&&typeof p.id==='string'&&typeof p.name==='string'&&p.name.length>0&&p.name.length<=80&&
    grades.includes(p.grade)&&stages.includes(p.stage)&&typeof p.category==='string'&&
    typeof p.discoveredOn==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(p.discoveredOn)&&
    typeof p.website==='string'&&(!p.website||safeWebsite(p.website)!==null)&&
    typeof p.description==='string'&&typeof p.notes==='string'&&Number.isFinite(p.progress)&&p.progress>=0&&p.progress<=100&&
    ['active','removed'].includes(p.membership)&&p.isDemo===true);
}
