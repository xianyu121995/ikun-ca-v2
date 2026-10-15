#!/usr/bin/env python3
"""Production Next/B1/Tracking metadata with browser-only silent speech/time/SSE mocks."""
import json
import hashlib
import os
from pathlib import Path
import secrets
import signal
import subprocess
import tempfile
import time
import uuid
import httpx
from c0_test_fixture import ROOT, NODE, PYTHON, environment, provision, migrate_projects, cli
from accept_b4_site import port, wait_ready, login

OUT=ROOT/'release-integration/.runtime/night-voice'
TRACKING_PYTHON=ROOT/'release-integration/.runtime/night-b3/venv/bin/python'
CHECKS=[]
SHOTS=OUT
def check(value,name):
    CHECKS.append({'check':name,'result':'PASS' if value else 'FAIL'})
    if not value: raise AssertionError(name)

MOCK=r"""(() => {
 const NativeDate=Date,NativeEventSource=EventSource,nativeFetch=fetch.bind(window);
 const state=window.__silentVoice={now:NativeDate.parse('2026-10-16T04:00:00Z'),spoken:[],cancels:0,sources:[],reads:[],hold:false,holdMetadata:false,releaseMetadata:null};
 window.Date=class extends NativeDate {constructor(...args){super(...(args.length?args:[state.now]));}static now(){return state.now;}};
 window.SpeechSynthesisUtterance=class{constructor(text){this.text=text;}};
 Object.defineProperty(window,'speechSynthesis',{configurable:true,value:{getVoices:()=>[{localService:true,lang:'zh-CN',default:true}],addEventListener(){},removeEventListener(){},speak(utterance){state.spoken.push(utterance.text);state.active=utterance;utterance.onstart?.();if(!state.hold)queueMicrotask(()=>utterance.onend?.());},cancel(){state.cancels++;sessionStorage.setItem('silent-voice-cancels',String(state.cancels));state.active=null;}}});
 window.EventSource=class extends EventTarget{
  constructor(url,options){super();this.url=String(url);this.closed=false;this.forwarded=new Set();this.real=new NativeEventSource(url,options);if(this.url==='/api/v1/tracking/events')state.sources.push(this);}
  addEventListener(type,listener,options){super.addEventListener(type,listener,options);if(!this.forwarded.has(type)){this.forwarded.add(type);this.real.addEventListener(type,e=>this.dispatchEvent(type==='open'||type==='error'?new Event(type):new MessageEvent(type,{data:e.data,lastEventId:e.lastEventId})));}}
  close(){this.closed=true;this.real.close();}get readyState(){return this.real.readyState;}
 };
 window.fetch=async(...args)=>{const path=String(args[0]);const response=await nativeFetch(...args);if(/^\/api\/v1\/tracking\/subscriptions\/sub_|^\/api\/v1\/projects\/prj_/.test(path)){state.reads.push({path,status:response.status});if(state.holdMetadata&&path.includes('/subscriptions/')){state.holdMetadata=false;await new Promise(resolve=>state.releaseMetadata=resolve);}}return response;};
 state.emit=(data,event_id)=>state.sources.filter(s=>!s.closed).forEach(s=>s.dispatchEvent(new MessageEvent('tracking.feed.activity.created.v1',{lastEventId:event_id,data:JSON.stringify({data,request_id:'voice_browser_mock'})})));
 state.connection=type=>state.sources.filter(s=>!s.closed).forEach(s=>s.dispatchEvent(new Event(type)));
})();"""

def emit(page,sid,pid,**patch):
    data={'activity_id':'act_'+str(uuid.uuid4()),'subscription_id':sid,'project_id':pid,'tweet_kind':'original',
          'source':'wss','is_live_new':True,'replay':False,'notes':'不得使用的事件备注','rating':'S','text':'不得播报的正文',**patch}
    event='evt_'+str(uuid.uuid4())
    page.evaluate("([data,id])=>{data.received_at=new Date(Date.now()).toISOString();window.__silentVoice.emit(data,id);}",[data,event])
    return data,event

def user_login(page,origin,account):
    page.goto(origin+'/login')
    page.locator('input[name=username]').fill(account['username']);page.locator('input[name=password]').fill(account['password'])
    page.locator('button[type=submit]').click();page.wait_for_url(origin+'/',timeout=15000)
    page.goto(origin+'/tracking')
    page.get_by_role('region',name='推文语音设置').wait_for(timeout=15000)
    page.wait_for_function('window.__silentVoice.sources.length===1&&window.__silentVoice.sources[0].readyState===1')

def browser_checks(browser,origin,accounts,sid,pid,data):
    for role in ('admin','user'):
        context=browser.new_context();context.add_init_script(MOCK);page=context.new_page()
        try:
            user_login(page,origin,accounts[role]);settings=page.get_by_role('region',name='推文语音设置')
            check(settings.get_by_text('语音已关闭',exact=True).count()==1,role+'_default_off_no_sound')
            check(page.evaluate('__silentVoice.spoken.length')==0,role+'_no_initial_speech')
            check(settings.get_by_role('button',name='启用本页语音').is_enabled(),role+'_personal_voice_control_available')
            check(page.evaluate('__silentVoice.sources.length')==1,role+'_one_existing_Tracking_EventSource')
            page.get_by_text('暂无符合条件的推文',exact=True).wait_for()
            check(True,role+'_real_feed_empty_no_page_metadata_fallback')
            settings.get_by_role('button',name='启用本页语音').click()
            packet,event_id=emit(page,sid,pid)
            page.wait_for_function('__silentVoice.spoken.length===1')
            check(page.evaluate('__silentVoice.spoken[0]')=='语音验收备注，A级。',role+'_mock_speech_uses_real_B1_metadata')
            reads=page.evaluate('__silentVoice.reads')
            check(any(x['path']=='/api/v1/tracking/subscriptions/'+sid and x['status']==200 for x in reads) and any(x['path']=='/api/v1/projects/'+pid and x['status']==200 for x in reads),role+'_two_actual_authenticated_metadata_reads')
            page.evaluate('([d,id])=>__silentVoice.emit({...d,received_at:new Date(Date.now()).toISOString()},id)',[packet,event_id])
            emit(page,sid,pid,replay=True,is_live_new=False)
            page.wait_for_timeout(300)
            check(page.evaluate('__silentVoice.spoken.length')==1,role+'_duplicate_and_replay_rejected')
            checkbox=settings.locator('input[type=checkbox]');checkbox.wait_for();check(checkbox.is_enabled(),role+'_personal_subscription_toggle_available')
            checkbox.uncheck();emit(page,sid,pid);page.wait_for_timeout(200)
            check(page.evaluate('__silentVoice.spoken.length')==1,role+'_subscription_mute_drops_new_event')
            checkbox.check();emit(page,sid,pid,tweet_kind='quote');page.wait_for_function('__silentVoice.spoken.length===2')
            check(True,role+'_quote_uses_same_authoritative_metadata')
            uid=page.evaluate("async()=>{const r=await fetch('/api/v1/auth/me');return(await r.json()).data.user_id;}")
            preference=page.evaluate('(key)=>localStorage.getItem(key)','ikun.voice.v1.'+__import__('urllib.parse',fromlist=['quote']).quote(uid,safe="~()*!.'-"))
            check(preference is not None and '语音验收备注' not in preference and '正文' not in preference,role+'_preferences_key_real_user_id_no_content')
            page.evaluate("__silentVoice.connection('error')")
            page.wait_for_function("document.querySelector('[aria-label=推文语音设置]').textContent.includes('实时连接已断开')")
            page.evaluate("__silentVoice.connection('open')");emit(page,sid,pid);page.wait_for_timeout(200)
            check(page.evaluate('__silentVoice.spoken.length')==2,role+'_reconnect_requires_new_gesture')
            settings.get_by_role('button',name='启用本页语音').click()
            page.evaluate('__silentVoice.holdMetadata=true');emit(page,sid,pid)
            page.wait_for_function('typeof __silentVoice.releaseMetadata===\'function\'')
            page.evaluate("__silentVoice.connection('error');__silentVoice.releaseMetadata();__silentVoice.releaseMetadata=null")
            page.wait_for_timeout(300)
            check(page.evaluate('__silentVoice.spoken.length')==2,role+'_late_metadata_after_disconnect_discarded')
            page.evaluate("__silentVoice.connection('open')");settings.get_by_role('button',name='启用本页语音').click()
            page.evaluate('__silentVoice.hold=true');emit(page,sid,pid)
            page.wait_for_function('__silentVoice.spoken.length===3')
            cancels=page.evaluate('__silentVoice.cancels')
            page.evaluate("__silentVoice.now=Date.parse('2026-10-16T14:00:00Z');document.dispatchEvent(new Event('visibilitychange'))")
            page.wait_for_function("document.querySelector('[aria-label=推文语音设置]').textContent.includes('当前静音')")
            emit(page,sid,pid);check(page.evaluate('__silentVoice.cancels')>cancels,role+'_22_boundary_cancels_active_mock')
            page.evaluate("__silentVoice.now=Date.parse('2026-10-17T00:00:00Z');document.dispatchEvent(new Event('visibilitychange'))")
            page.wait_for_timeout(200)
            check(page.evaluate('__silentVoice.spoken.length')==3,role+'_08_does_not_replay_quiet_queue')
            settings.get_by_role('button',name='关闭语音').click();emit(page,sid,pid);page.wait_for_timeout(200)
            check(page.evaluate('__silentVoice.spoken.length')==3,role+'_global_off_drops_events')
            for width in (1440,390):
                page.set_viewport_size({'width':width,'height':1000})
                page.evaluate('async()=>{await document.fonts.ready;await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));}')
                check(page.evaluate('document.documentElement.scrollWidth<=innerWidth'),f'voice_layout_{role}_{width}')
                page.screenshot(path=str(SHOTS/f'voice-{role}-{width}.png'),full_page=True)
            if role=='user':
                page.get_by_role('button',name='监控账号总数 1').click()
                check(page.get_by_text('已加入追踪的 X 账号 · 只读视图',exact=True).count()==1,'ordinary_business_drawer_still_readonly')
                page.get_by_role('button',name='关闭弹窗').click()
            page.locator('summary').filter(has_text=accounts[role]['username']).click()
            page.get_by_role('button',name='退出登录',exact=True).click();page.wait_for_url('**/login')
            check(int(page.evaluate("sessionStorage.getItem('silent-voice-cancels')||'0'"))>0,role+'_logout_cancels_voice_and_navigates_login')
        finally:context.close()
    context=browser.new_context();context.add_init_script(MOCK);page=context.new_page()
    try:
        user_login(page,origin,accounts['forced']);settings=page.get_by_role('region',name='推文语音设置')
        settings.get_by_role('button',name='启用本页语音').click();page.evaluate('__silentVoice.hold=true');emit(page,sid,pid)
        page.wait_for_function('__silentVoice.spoken.length===1');before=page.evaluate('__silentVoice.cancels')
        cli(data,origin,'disable',accounts['forced']['username'])
        page.wait_for_function("document.querySelector('[aria-label=推文语音设置]')?.textContent.includes('登录后可启用语音')",timeout=7000)
        check(page.evaluate('__silentVoice.cancels')>before,'real_B1_disable_quiet_SSE_cancels_active_mock')
        page.evaluate("__silentVoice.connection('open')");emit(page,sid,pid);page.wait_for_timeout(200)
        check(page.evaluate('__silentVoice.spoken.length')==1,'late_open_after_revocation_cannot_revive_old_epoch')
        check(page.evaluate("async()=> (await fetch('/api/v1/tracking/subscriptions')).status")==401,'revoked_voice_user_real_API401')
    finally:context.close()


def main():
    global SHOTS
    OUT.mkdir(mode=0o700,parents=True,exist_ok=True);scratch=Path(tempfile.mkdtemp(prefix='ikun-voice-',dir='/private/tmp'));data=scratch/'data'
    SHOTS=OUT/('run-'+str(time.time_ns()));SHOTS.mkdir(mode=0o700)
    origin='http://127.0.0.1:'+str(port());tracking_origin='http://127.0.0.1:'+str(port())
    accounts=provision(data,origin,scratch/'accounts.private.json');migrate_projects(data)
    cfg=scratch/'tracking.json';cfg.write_text(json.dumps({'db_path':str(data/'tracking/tracking.db'),'remote_enabled':False,'dedicated_account':False,'port':int(tracking_origin.rsplit(':',1)[1])}));cfg.chmod(0o600)
    init=subprocess.run([str(TRACKING_PYTHON),str(ROOT/'services/tracking-worker/python/entry.py'),'init','--config',str(cfg)],env=environment(data,origin),capture_output=True);check(init.returncode==0,'explicit_new_local_Tracking_init')
    env=environment(data,origin);env.update(IKUN_RELEASE_SHA=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),PROJECTS_PYTHON=str(PYTHON),PORT=origin.rsplit(':',1)[1],TRACKING_API_URL=tracking_origin,TRACKING_API_TOKEN=secrets.token_urlsafe(32),IKUN_TRACKING_FIXTURE='1')
    worker_env={**env,'IKUN_TRACKING_CONFIG':str(cfg),'IKUN_TRACKING_PYTHON':str(TRACKING_PYTHON),'IKUN_TRACKING_EXTERNAL_IO_DISABLED':'1'}
    processes=[];report={'state':'RUNNING','checks':CHECKS,'real_sound':False,'SSE_frames':'browser synthetic only; existing real EventSource and B1 metadata used','real_provider_calls':0,'build_id':(ROOT/'apps/website/.next/BUILD_ID').read_text().strip()}
    log=open(OUT/('site-'+str(time.time_ns())+'.log'),'ab',buffering=0)
    try:
        for argv,proc_env,endpoint in [([str(NODE),'services/tracking-worker/dist/main.js'],worker_env,tracking_origin),([str(NODE),'scripts/start-c0-lite.mjs'],env,origin)]:
            process=subprocess.Popen(argv,cwd=ROOT,env=proc_env,stdout=log,stderr=log,start_new_session=True);processes.append(process);wait_ready(endpoint,process)
        with httpx.Client(base_url=origin,trust_env=False,timeout=10) as admin:
            me=login(admin,origin,accounts['admin'])
            for role in ('user','forced'):
                with httpx.Client(base_url=origin,trust_env=False,timeout=10) as client:login(client,origin,accounts[role])
            headers={'Origin':origin,'X-CSRF-Token':me['csrf_token'],'Idempotency-Key':str(uuid.uuid4())}
            body={'name':'语音本地验收','rating':'A','description':'','website_url':None,'notes':'项目备注不能代替订阅备注','category':None,'progress_stage':'watching','progress_percent':None,'token_date':None,'token_date_status':'unconfirmed'}
            created=admin.post('/api/v1/projects',json=body,headers=headers);check(created.status_code==201,'real_Project_canonical_creation')
            pid=created.json()['data']['project_id'];headers['Idempotency-Key']=str(uuid.uuid4())
            created=admin.post('/api/v1/tracking/subscriptions',json={'project_id':pid,'name':'语音本地验收','x_handle':'voicefixture','x_user_id':None,'notes':'语音验收备注','confirmed':True},headers=headers);check(created.status_code==202,'real_Tracking_subscription_creation')
            sid=created.json()['data']['subscription_id']
            from playwright.sync_api import sync_playwright
            with sync_playwright() as runtime:
                browser=runtime.chromium.launch(channel='chrome',headless=True)
                try:browser_checks(browser,origin,accounts,sid,pid,data)
                finally:browser.close()
            check(admin.get('/api/v1/auth/me').status_code==200,'local_admin_unaffected_by_voice_user_revocation')
        report['state']='PASS_VOICE_LOCAL_PRODUCTION_SILENT'
    except Exception as error:
        report['state']='FAIL';report['error_type']=type(error).__name__;report['error']=str(error)[:300] if isinstance(error,(AssertionError,RuntimeError)) else 'inspect task-private log';raise
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.send_signal(signal.SIGTERM)
                try:process.wait(timeout=12)
                except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5)
        log.close();report['screenshots']={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(SHOTS.glob('*.png'))};path=OUT/('site-acceptance-'+str(time.time_ns())+'.json');path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');path.chmod(0o600)
        print(json.dumps({'state':report['state'],'checks':len(CHECKS),'receipt':str(path)},ensure_ascii=False))


if __name__=='__main__':main()
