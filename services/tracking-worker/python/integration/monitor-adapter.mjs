/** Live adapter candidate for the tracking-ui presentation contract. No simulated state transitions. */
export class LiveMonitorAdapter {
  mode = 'live';
  capabilities = Object.freeze({simulateTweet:false,reset:false,markRead:false,categories:false});
  constructor({confirmProject, fetchImpl=globalThis.fetch, interval=3000}={}) {
    this.confirmProject=confirmProject;this.fetch=fetchImpl;this.interval=interval;
    this.rows=new Map();this.listeners=new Set();this.timer=null;this.closed=false;this.csrf='';
  }
  async request(path,options={}) {
    const response=await this.fetch('/api/v1/tracking'+path,{
      credentials:'same-origin',...options,signal:AbortSignal.timeout(10000),
      headers:{'Content-Type':'application/json','X-CSRF-Token':this.csrf,...(options.headers||{})}
    });
    const envelope=await response.json();
    if(!response.ok)throw Object.assign(new Error(envelope.error?.message||'监控接口不可用'),{code:envelope.error?.code,status:response.status});
    return envelope.data;
  }
  monitor(row) {
    let status;
    if(row.status==='monitoring')status='running';
    else if(row.status==='stopped'||row.status==='removed')status='stopped';
    else if(row.error)status='failed';
    else if(row.desired!=='running')status='stopping';
    else status='starting';
    return {id:row.project_id,name:row.name,handle:row.handle,category:'未分类',status,
      addedAt:Date.parse(row.created_at),updatedAt:Date.parse(row.updated_at),lastTweetAt:row.last_tweet_at?Date.parse(row.last_tweet_at):null,
      tweetCount:row.tweet_count??null,transitionAt:null,error:row.error?{code:row.error,message:'远端结果待恢复，请查看监控详情'}:null,
      revision:row.revision,remoteState:row.remote_state,coverage:row.coverage};
  }
  async list() {
    const me=await this.fetch('/api/tracking/me',{credentials:'same-origin',signal:AbortSignal.timeout(10000)});
    if(!me.ok)throw Object.assign(new Error('请先登录'),{status:me.status});
    this.csrf=(await me.json()).csrf_token||'';
    const rows=[];let cursor=null;
    do {
      const page=await this.request('/subscriptions?limit=100'+(cursor?'&cursor='+encodeURIComponent(cursor):''));
      rows.push(...page.items);cursor=page.next_cursor;
      if(rows.length>10000)throw new Error('监控列表超过单次页面上限');
    }while(cursor);
    this.rows=new Map(rows.map(row=>[row.project_id,row]));
    const latest=await this.request('/latest?limit=100');
    const tweets=latest.items.map(item=>({id:String(item.seq),projectId:item.project_id,projectName:item.project_name,
      handle:item.handle,text:item.text,createdAt:Date.parse(item.created_at),read:false,url:item.url}));
    const projects=rows.map(row=>this.monitor(row));
    this.snapshot={version:1,projects,tweets,events:[],warning:'仅显示已入库动态；分类、已读状态和操作日志面板暂不支持。'};
    return this.snapshot;
  }
  async add(input) {
    if(typeof this.confirmProject!=='function')throw Object.assign(new Error('请先由超级管理员选择并确认项目'),{code:'CONFIRMATION_REQUIRED'});
    const confirmed=await this.confirmProject(input);
    if(confirmed?.humanConfirmed!==true||!/^prj_[0-9a-f-]{36}$/.test(confirmed.projectId||''))throw new Error('缺少人工确认的 canonical project_id');
    const row=await this.request('/subscriptions',{method:'POST',headers:{'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify({
      project_id:confirmed.projectId,name:confirmed.name,handle:confirmed.handle,confirmed:true,notes:confirmed.notes||''})});
    this.rows.set(row.project_id,row);return this.monitor(row);
  }
  async command(projectId,operation) {
    const row=this.rows.get(projectId);
    if(!row)throw new Error('请刷新后再操作');
    const result=await this.request('/subscriptions/'+encodeURIComponent(projectId)+(operation==='remove'?'':'/'+operation),{
      method:operation==='remove'?'DELETE':'POST',headers:{'Idempotency-Key':crypto.randomUUID(),'If-Match':`"rev-${row.revision}"`}});
    this.rows.set(projectId,result);return this.monitor(result);
  }
  stop(id){return this.command(id,'stop');}
  resume(id){return this.command(id,'resume');}
  retry(id){return this.command(id,'resume');}
  async remove(id){await this.command(id,'remove');}
  async markRead(){throw Object.assign(new Error('正式引擎尚未提供已读状态，页面应禁用此操作'),{code:'UNSUPPORTED'});}
  subscribe(listener) {
    this.listeners.add(listener);
    const poll=async()=>{
      if(this.closed||!this.listeners.size)return;
      try{const snapshot=await this.list();for(const fn of this.listeners)fn(snapshot);}catch{
        const stale={...(this.snapshot||{version:1,projects:[],tweets:[],events:[]}),warning:'监控 API 不可用，当前远端状态未核验。'};
        stale.projects=stale.projects.map(row=>({...row,status:'failed',error:{code:'UNVERIFIED',message:'当前远端状态未核验'}}));
        for(const fn of this.listeners)fn(stale);
      }
      if(!this.closed&&this.listeners.size)this.timer=setTimeout(poll,this.interval);
    };
    if(this.listeners.size===1)poll();
    return ()=>{this.listeners.delete(listener);if(!this.listeners.size)clearTimeout(this.timer);};
  }
  destroy(){this.closed=true;clearTimeout(this.timer);this.listeners.clear();}
}
