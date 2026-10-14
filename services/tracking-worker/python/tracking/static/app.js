"use strict";
const $ = id => document.getElementById(id);
let rows = [], role = null, editing = null, selected = null, timer = null, busy = false, siteAuth=false, csrf="";
const labels = {pending:"等待处理",starting:"正在启动",monitoring:"正在接收",recovering:"恢复连接中",running:"远端已启用",stopped:"已停止",removed:"已移除",retrying:"等待重试",blocked:"需要处理",unverified:"等待核验"};
const errors = {remote_not_configured:"独立监控连接尚未配置",ownership_conflict:"该账号已有其他监控配置，未作修改",remote_flags_conflict:"远端事件配置发生变化，请管理员核对",quota_exhausted:"远端监控名额不足，将自动重试",rate_limited:"接口限流，将自动重试",remote_auth_failed:"远端授权失败，请管理员检查",remote_verification_failed:"远端尚未确认操作结果",request_uncertain:"接口未返回确定结果，等待回查",api_failure:"远端接口失败，将自动重试",incomplete_watch_snapshot:"远端监控列表不完整，等待恢复",invalid_watch_snapshot:"远端返回格式待核对"};
function notify(text) { $("notice").textContent=text; $("notice").hidden=!text; }
function node(tag, text, cls) { const el=document.createElement(tag); if(text!==undefined)el.textContent=text; if(cls)el.className=cls; return el; }
function date(value) { return value ? new Date(value*1000).toLocaleString("zh-CN",{timeZone:"Asia/Shanghai",hour12:false}) : "尚未核验"; }
async function api(path, options={}) {
  const controller=new AbortController(), timeout=setTimeout(()=>controller.abort(),15000);
  try {
    const response=await fetch("/api/tracking"+path,{credentials:"same-origin",...options,signal:controller.signal,headers:{"Content-Type":"application/json","X-Tracking-CSRF":"1","X-CSRF-Token":csrf,...(options.headers||{})}});
    const data=await response.json();
    if(response.status===401) { loggedOut(); if(siteAuth)location.assign("/login?next=/tracking"); throw new Error("请先登录"); }
    if(!response.ok) throw new Error(response.status===409?"数据已更新，请刷新后再操作":response.status===403?"此操作需要超级管理员权限":response.status===429?"操作过于频繁，请稍后重试":typeof data.detail==="string"?data.detail:"请检查填写内容");
    return data;
  } catch(e) { if(e.name==="AbortError")throw new Error("请求超时，请刷新核对结果"); throw e; }
  finally {clearTimeout(timeout);}
}
function loggedOut(){role=null;clearTimeout(timer);$("workspace").hidden=true;$("login-panel").hidden=false;$("add").hidden=true;$("logout").hidden=true;$("connection").textContent="未登录";}
async function change(row, action) {
  if(busy)return; busy=true;
  try {
    const path="/projects/"+encodeURIComponent(row.project_id);
    await api(path+(action==="remove"?"":"/"+action),{method:action==="remove"?"DELETE":"POST",headers:{"Idempotency-Key":crypto.randomUUID()},body:JSON.stringify({expected_revision:row.revision})});
    notify("请求已提交，等待后台引擎核验远端结果。"); await refresh();
  }catch(e){notify(e.message);}finally{busy=false;}
}
function button(text, fn, cls){const b=node("button",text,cls);b.onclick=fn;return b;}
function renderProjects(){
  const term=$("search").value.trim().toLowerCase();
  const visible=rows.filter(r=>(r.name+" "+r.handle).toLowerCase().includes(term));
  $("projects").replaceChildren();$("empty").hidden=visible.length>0;
  if(!visible.length)$("empty").textContent=term?"没有匹配的项目。":"还没有监控项目。由超级管理员人工确认后添加。";
  for(const row of visible){
    const tr=node("tr"), identity=node("td");identity.append(node("div",row.name,"project-name"));
    const link=node("a","@"+row.handle);link.href="https://x.com/"+row.handle;link.target="_blank";link.rel="noopener noreferrer";identity.append(link);
    const state=node("td");state.append(node("span",labels[row.status]||row.status,"badge "+(row.status==="monitoring"?"good":["retrying","blocked","unverified"].includes(row.status)?"warn":"")));
    if(row.error)state.append(node("small",errors[row.error]||"连接异常，等待恢复"));
    const remote=node("td");remote.append(node("div",{active:"已启用",absent:"已停用 / 不存在",unknown:"结果待确认"}[row.remote_state]));remote.append(node("small",date(row.observed_at)));
    if(row.desired==="removed"&&row.status!=="removed")state.append(node("small","移除请求处理中"));
    const coverage=node("td",{pending:"等待首次恢复",bounded_latest_100:"最近窗口已核对",possible_gap:"可能存在历史缺口",recovery_failed:"补采失败，稍后重试"}[row.coverage]||row.coverage);
    const operations=node("td"), actions=node("div",undefined,"actions");
    actions.append(button("动态",()=>{selected=row.project_id;refreshFeed().catch(e=>notify(e.message));}));
    if(role==="superadmin") {
      actions.append(button("编辑",()=>openDialog(row)));
      actions.append(button(row.desired==="running"?"停止":"恢复",()=>change(row,row.desired==="running"?"stop":"resume")));
      if(row.desired!=="removed")actions.append(button("移除",()=>change(row,"remove"),"danger"));
    }
    operations.append(actions);tr.append(identity,state,remote,coverage,operations);$("projects").append(tr);
  }
}
async function refreshFeed(){
  const data=await api("/latest?limit=30"+(selected?"&project_id="+encodeURIComponent(selected):""));
  $("feed").replaceChildren();$("feed-empty").hidden=!!data.items.length;$("clear-filter").hidden=!selected;
  for(const item of data.items){const article=node("article",undefined,"feed-item"), top=node("div",undefined,"feed-top");
    top.append(node("strong",item.project_name+" · @"+item.handle),node("time",date(item.created_at)));
    const link=node("a","查看原推文 ↗");link.href=item.url;link.target="_blank";link.rel="noopener noreferrer";
    article.append(top,node("p",item.text||"推文正文待补全"),link);$("feed").append(article);}
}
async function refresh(){
  clearTimeout(timer);
  try{
    const [status,projects]=await Promise.all([api("/status"),api("/projects?include_removed="+$("removed").checked)]);
    rows=projects.items;$("total").textContent=status.projects;$("active").textContent=status.monitoring;$("pending").textContent=status.pending_or_failed;
    $("connection").textContent=!status.engine.alive?"后台引擎离线":status.engine.connection==="connected"?"实时连接有效":"后台引擎正在恢复连接";
    $("connection").className="badge "+(status.engine.connection==="connected"?"good":"warn");
    renderProjects();await refreshFeed();
  }catch(e){notify(e.message);}finally{if(role)timer=setTimeout(refresh,5000);}
}
function openDialog(row){
  editing=row;$("project-form").reset();$("dialog-title").textContent=row?"编辑监控项目":"添加监控项目";
  $("project-id").value=row?.project_id||"";$("project-id").disabled=!!row;
  $("project-handle").value=row?.handle||"";$("project-handle").disabled=!!row;
  $("project-name").value=row?.name||"";$("project-notes").value=row?.notes||"";
  $("confirm-label").hidden=!!row;$("confirmed").required=!row;
  $("save-project").textContent=row?"保存修改":"确认添加并启动";$("project-dialog").showModal();
}
$("project-form").onsubmit=async e=>{
  e.preventDefault();const save=$("save-project");save.disabled=true;
  try{const body={name:$("project-name").value.trim(),notes:$("project-notes").value.trim()};
    if(editing)body.expected_revision=editing.revision;
    else Object.assign(body,{project_id:$("project-id").value.trim(),handle:$("project-handle").value.trim(),confirmed:$("confirmed").checked});
    await api(editing?"/projects/"+encodeURIComponent(editing.project_id):"/projects",{method:editing?"PATCH":"POST",headers:{"Idempotency-Key":crypto.randomUUID()},body:JSON.stringify(body)});
    $("project-dialog").close();notify(editing?"项目资料已保存。":"项目已提交，等待远端确认启动。");await refresh();
  }catch(err){notify(err.message);}finally{save.disabled=false;}
};
async function boot(){try{siteAuth=(await api("/auth-mode")).mode==="site";const me=await api("/me");role=me.role;csrf=me.csrf_token||"";$("login-panel").hidden=true;$("workspace").hidden=false;$("add").hidden=role!=="superadmin";$("logout").hidden=siteAuth;await refresh();}catch(e){loggedOut();}}
$("login-form").onsubmit=async e=>{e.preventDefault();try{await api("/session",{method:"POST",body:JSON.stringify({token:$("access-key").value})});$("access-key").value="";notify("");await boot();}catch(err){notify(err.message);}};
$("logout").onclick=async()=>{try{await api("/session",{method:"DELETE"});loggedOut();}catch(e){notify(e.message);}};
$("add").onclick=()=>openDialog(null);$("close-dialog").onclick=()=>$("project-dialog").close();
$("refresh").onclick=refresh;$("search").oninput=renderProjects;$("removed").onchange=refresh;
$("clear-filter").onclick=()=>{selected=null;refreshFeed().catch(e=>notify(e.message));};
document.addEventListener("visibilitychange",()=>{if(!document.hidden&&role)refresh();});
boot();
