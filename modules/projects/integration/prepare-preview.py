"""Reproducible ignored B2 assembly from pinned objects. Never edits another checkout."""
import difflib
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
PREVIEW=ROOT/'modules/projects/.preview'
PINS=dict(b0='85be3bd6dce25d82033b6cb1a7157aaa39bd571e',auth='28e6aaf4141790fc74ae4ae4429be4b854460955',
          ui='486294ac3255b08fdb13a307ee15f96c571020d9',homepage='eb93ac7739e0ce9d74fa9859f838a7bca294ce3e',
          home_contract='6595c4a05b736889a4649b1d0aa7405601deebc4',collections='379c6e583e487f038629e1ca24d4b2614970ad0c')
PINS.update(spec='9699375c920465b5d802e7acff17b5421203e544',auth_review='c0f86bc20fc7b3ca147da863759b98acced8de44',b2_release='4b2e33b0d4996c93d6df9bd5ef265fe0d2ddcaf5')

def archive(sha,*paths):
    data=subprocess.check_output(['git','archive',sha,*paths],cwd=ROOT)
    subprocess.run(['tar','-x','-C',str(PREVIEW)],input=data,check=True)

def replace(text,old,new,count=1):
    if text.count(old)!=count:raise RuntimeError('PINNED_UI_PATCH_CONTEXT_MISMATCH: '+old[:70])
    return text.replace(old,new)

def patch_homepage():
    path=PREVIEW/'apps/website/components/homepage-ui/reference-homepage.tsx'
    old=path.read_text();text=old
    text=replace(text,'archiveNotes=[],asOfDate}', 'archiveNotes=[],asOfDate,server}')
    text=replace(text,'const active=projection.items.filter(isMain);','const byId=(ids:readonly string[])=>ids.map(id=>projection.items.find(p=>p.key===id)).filter((p):p is ProjectView=>!!p);\n  const active=server?byId(server.mainIds):projection.items.filter(isMain);')
    text=replace(text,"const archived=projection.items.filter(view=>view.record.home_membership==='removed'&&view.record.progress_stage==='completed');","const archived=server?byId(server.completedIds):projection.items.filter(view=>view.record.home_membership==='removed'&&view.record.progress_stage==='completed');")
    text=replace(text,'const other=projection.items.filter(view=>!isMain(view)&&!archived.includes(view));','const other=server?byId(server.otherIds):projection.items.filter(view=>!isMain(view)&&!archived.includes(view));')
    text=replace(text,'const dateActive=active.filter','const dateActive=server?active:active.filter')
    text=replace(text,'const filtered=useMemo(()=>active.filter','const localFiltered=useMemo(()=>server?[]:active.filter')
    text=replace(text,'[projection,query,sort,milestones]','[projection,query,sort,milestones,server]')
    text=replace(text,'const pages=Math.max(1,Math.ceil(filtered.length/pageSize)),currentPage=Math.min(page,pages);','const filtered=server?active:localFiltered;\n  const total=server?server.total:filtered.length;\n  const pages=Math.max(1,Math.ceil(total/pageSize)),currentPage=server?server.page:Math.min(page,pages);')
    text=replace(text,'const shown=filtered.slice((currentPage-1)*pageSize,currentPage*pageSize);','const shown=server?active:filtered.slice((currentPage-1)*pageSize,currentPage*pageSize);')
    text=replace(text,'const events=upcomingProjects(', 'const events=server?byId(server.eventIds).map(project=>({project,event:currentMilestone(project,milestones)})):upcomingProjects(')
    text=replace(text,'function changeQuery(next:typeof query)',"useEffect(()=>{setSelected(new Set());},[server?.page,server?.mainIds.join(',')]);\n  function changeSort(next:TableSort){setSort(next);server?.onSort(next);setPage(1);setSelected(new Set());}\n  function changePage(next:number){setPage(next);server?.onPage(next);setSelected(new Set());}\n  function changeQuery(next:typeof query)")
    text=replace(text,'onClick={()=>setDetail(view.key)}','onClick={()=>{server?.onDetail(view.key);setDetail(view.key);}}',count=1)
    text=replace(text,'onClick={()=>setDetail(row.project.key)}','onClick={()=>{server?.onDetail(row.project.key);setDetail(row.project.key);}}')
    text=replace(text,'onChange={event=>setWindowDays(event.target.value)}','onChange={event=>{setWindowDays(event.target.value);server?.onWindow(event.target.value);}}')
    text=replace(text,'({dateActive.length})','({server?server.summary.tracked_total:dateActive.length})')
    text=replace(text,'已完成记录 ({archived.length})','已完成记录 ({server?server.summary.completed_total:archived.length})')
    text=replace(text,'{other.length>0&&','{(server?server.summary.other_total:other.length)>0&&')
    text=replace(text,'其他项目 ({other.length})','其他项目 ({server?server.summary.other_total:other.length})')
    text=replace(text,"setSort({key:key!,direction:direction as TableSort['direction']});setPage(1);setSelected(new Set());","changeSort({key:key!,direction:direction as TableSort['direction']});")
    text=replace(text,"{grade==='all'?dateActive.length:dateActive.filter(view=>view.record.rating===grade).length}","{server?(grade==='all'?server.summary.tracked_total:server.summary.by_rating[grade as 'S'|'A'|'B']):grade==='all'?dateActive.length:dateActive.filter(view=>view.record.rating===grade).length}")
    text=replace(text,'onSortChange={next=>{setSort(next);setPage(1);setSelected(new Set());}}','onSortChange={changeSort}')
    text=replace(text,'显示 {filtered.length?','显示 {total?')
    text=replace(text,'Math.min(currentPage*pageSize,filtered.length)','Math.min(currentPage*pageSize,total)')
    text=replace(text,'共 {filtered.length} 条','共 {total} 条')
    text=replace(text,'{setPage(currentPage-1);setSelected(new Set());}','{changePage(currentPage-1);}')
    text=replace(text,'{setPage(value);setSelected(new Set());}','{changePage(value);}')
    text=replace(text,'{setPage(currentPage+1);setSelected(new Set());}','{changePage(currentPage+1);}')
    text=replace(text,'disabled={currentPage===1}','disabled={server?!server.canPage(currentPage-1):currentPage===1}')
    text=replace(text,'aria-label={`第 ${value} 页`}', 'disabled={server?!server.canPage(value):false} aria-label={`第 ${value} 页`}')
    text=replace(text,'disabled={currentPage>=pages}','disabled={server?!server.canPage(currentPage+1):currentPage>=pages}')
    text=replace(text,'title={`已完成记录 (${archived.length})`}','title={`已完成记录 (${server?server.summary.completed_total:archived.length})`}')
    text=replace(text,'description="点击表格右侧移除，确认完成后记录保留在这里。"/>}</HomepageDialog>}', 'description="点击表格右侧移除，确认完成后记录保留在这里。"/>}{server?.completedPagination}</HomepageDialog>}')
    text=replace(text,'</div>)}</HomepageDialog>}\n    {deleteTarget', '</div>)}{server?.otherPagination}</HomepageDialog>}\n    {deleteTarget')
    path.write_text(text)
    types=PREVIEW/'apps/website/features/homepage/reference-types.ts'
    original=types.read_text();updated="import type {ServerHomepage} from '../../lib/homepage-server';\n"+original.replace('export interface ReferenceHomepageProps {','export interface ReferenceHomepageProps {\n  server?:ServerHomepage;')
    types.write_text(updated)
    patch=''.join(difflib.unified_diff(old.splitlines(True),text.splitlines(True),fromfile='a/apps/website/components/homepage-ui/reference-homepage.tsx',tofile='b/apps/website/components/homepage-ui/reference-homepage.tsx',n=0))
    patch+=''.join(difflib.unified_diff(original.splitlines(True),updated.splitlines(True),fromfile='a/apps/website/features/homepage/reference-types.ts',tofile='b/apps/website/features/homepage/reference-types.ts',n=0))
    (HERE/'patches').mkdir(exist_ok=True);(HERE/'patches/homepage-server.patch').write_text(patch)
    return hashlib.sha256(patch.encode()).hexdigest()

def main():
    if (PREVIEW/'package.json').exists():raise RuntimeError('PREVIEW_EXISTS: preserve evidence; remove only this disposable directory explicitly before reassembly')
    PREVIEW.mkdir(parents=True,exist_ok=True)
    archive(PINS['b0']);archive(PINS['ui'],'packages/ui');archive(PINS['auth'],'modules/auth/src','modules/auth/tsconfig.json','modules/auth/integration/website','schemas/auth')
    archive(PINS['homepage'],*[f'apps/website/components/homepage-ui/{name}' for name in ['reference-homepage.tsx','reference-editor.tsx','shared-dialog.tsx','reference-homepage.css']],
            *[f'apps/website/features/homepage/{name}.ts' for name in ['types','reference-types','reference-model','view-model']])
    shutil.copytree(PREVIEW/'modules/auth/integration/website',PREVIEW/'apps/website',dirs_exist_ok=True)
    shutil.copytree(HERE/'website',PREVIEW/'apps/website',dirs_exist_ok=True)
    pkg=PREVIEW/'apps/website/package.json';data=json.loads(pkg.read_text());data['dependencies']['@ikun/ui']='workspace:*';pkg.write_text(json.dumps(data,indent=2)+'\n')
    shutil.copyfile(PREVIEW/'config/b0/pnpm-ui-lock.yaml',PREVIEW/'pnpm-lock.yaml')
    patch_hash=patch_homepage()
    manifest={**PINS,'profile':'phase2-v1.0.0+auth-b1-final-v2+projects-home-v1','ui_patch_sha256':patch_hash,
              'lock_sha256':hashlib.sha256((PREVIEW/'pnpm-lock.yaml').read_bytes()).hexdigest(),'preview':str(PREVIEW)}
    (PREVIEW/'b2-inputs.json').write_text(json.dumps(manifest,indent=2)+'\n');print(PREVIEW)

if __name__=='__main__':main()
