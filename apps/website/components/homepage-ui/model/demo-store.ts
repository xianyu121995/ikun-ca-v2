import {demoProjects} from './demo-data';
import {isSnapshot,type HomepageProjectStore,type ProjectSnapshot} from './project';
export const STORAGE_KEY = 'ikun:v2:homepage-ui:demo:v1';
const empty = ():ProjectSnapshot=>({revision:0,items:demoProjects()});
function read():ProjectSnapshot {
  const raw=localStorage.getItem(STORAGE_KEY);
  if(raw===null)return empty();
  let value:unknown;
  try{value=JSON.parse(raw);}catch{throw new Error('演示存储无法读取。可点击“重置演示”恢复初始数据。');}
  if(!isSnapshot(value))throw new Error('演示存储格式不匹配。可点击“重置演示”恢复初始数据。');
  return value;
}
function persist(items:ProjectSnapshot['items'],revision:number):ProjectSnapshot {
  const snapshot={revision,items};
  try{localStorage.setItem(STORAGE_KEY,JSON.stringify(snapshot));}catch{throw new Error('浏览器未允许保存演示数据，本次操作未保存。');}
  return snapshot;
}
export const demoStore:HomepageProjectStore={
  load:read,
  commit(items,expectedRevision){
    const latest=read();
    if(latest.revision!==expectedRevision)throw new Error('演示数据已在另一个标签页更新。请刷新列表后重试。');
    if(!isSnapshot({revision:latest.revision+1,items}))throw new Error('项目字段格式不正确，未保存。');
    return persist(items,latest.revision+1);
  },
  reset(expectedRevision){
    let revision=expectedRevision;
    try{const latest=read();if(latest.revision!==expectedRevision)throw new Error('conflict');revision=latest.revision;}catch(e){if((e as Error).message==='conflict')throw new Error('演示数据已更新。请刷新后再重置。');}
    return persist(demoProjects(),revision+1);
  },
  subscribe(listener){const handle=(event:StorageEvent)=>{if(event.key===STORAGE_KEY){try{listener(read());}catch{/* keep visible data until explicit reload/reset */}}};window.addEventListener('storage',handle);return ()=>window.removeEventListener('storage',handle);}
};
