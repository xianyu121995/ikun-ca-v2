'use client';
import { useEffect, useMemo, useState, useRef, type FormEvent } from 'react';
import { Alert, Button, Dialog, Input, Panel } from '@ikun/ui';
import { LogoutButton } from './auth/forms';
import { TrackingPage } from '../features/tracking/final/tracking-page';
import { emptyFilters, type Account, type Post, type Filters } from '../features/tracking/final/model';
import {clearClientSession,invalidateClientData,keyedRefresh,peekClientData,readClientData,saveClientData} from '../lib/client-session-cache';
import {loadTrackingSubscriptions,invalidateTrackingSubscriptions} from '../lib/tracking-subscriptions-cache';
import {subscribeTrackingEvents} from '../lib/tracking-events-client';
import { TrackingHomeEditor, type EditTarget } from './tracking-home-editor';
import { useSiteVoice } from './voice-dock';
import type { VoiceSession } from '@ikun/ui';
type Subscription = {
    subscription_id: string;
    project_id: string;
    name: string;
    x_handle: string;
    notes: string;
    revision: number;
    desired_state: string;
    observed_state: string;
    error_code?: string;
    rating?: 'S'|'A'|'B'|null;
    operation_state: string;
    connection: string;
};
type Activity = {translation_zh?:Post['translation_zh'];quoted_tweet?:Post['quoted_tweet'];tweet_kind?:string;activity_id:string;subscription_id:string;project_id:string;name:string;x_handle:string;notes:string;rating:'S'|'A'|'B';rating_revision:number;text:string;occurred_at:string|null;received_at:string;sort_at:string;sort_basis:string;url:string};
type Totals={matchedTotal:number;subscriptionCounts:{S:number;A:number;B:number}};
type Snapshot={subs:Subscription[];accounts:Account[];historyAccounts:Account[];posts:Post[];cursor:string|null;totals:Totals;filters:Filters;windowFrom:string|null;page:number;cursors:(string|null)[];queryView:string};
export function TrackingLive({ csrf, canManage, username, voiceSession, fixture = false }: {
    csrf: string;
    canManage: boolean;
    username: string;
    voiceSession: VoiceSession;
    fixture?:boolean;
}) {
    // Voice now lives in the site-wide dock (root layout); this page only shows its settings.
    const scope=voiceSession.user_id,snapshot=useRef(peekClientData<Snapshot>(scope,'tracking:view')).current;
    const site = useSiteVoice();
    const voice = useMemo(() => ({ controller: site, connected: (_state: boolean) => {}, consume: (_event: MessageEvent) => {},
        verifyIdentity: async () => {}, revoke: () => { site?.setSession(null); } }), [site]);
    const queryView=useRef(snapshot?.queryView??'qv1_'+crypto.randomUUID());
    const pull = useRef<() => Promise<void>>(async () => { });
    const refreshRef = useRef<ReturnType<typeof keyedRefresh> | null>(null);
    if (!refreshRef.current)
        refreshRef.current = keyedRefresh(() => pull.current(),()=>latestView.current);
    const refresh = refreshRef.current;
    const [historyAccounts, setHistoryAccounts] = useState<Account[]>(snapshot?.historyAccounts??[]);
    const [homeEdit, setHomeEdit] = useState<EditTarget | null>(null);
    // Owner 2026-10-19: 取消追踪 from a tweet = remove the subscription (also drops ikun's 6551 Watch); homepage untouched, old tweets stay.
    const [untrack, setUntrack] = useState<Subscription | null>(null);
    const [subs, setSubs] = useState<Subscription[]>(snapshot?.subs??[]), [accounts, setAccounts] = useState<Account[]>(snapshot?.accounts??[]), [posts, setPosts] = useState<Post[]>(snapshot?.posts??[]);
    const [loading, setLoading] = useState(!snapshot), [error, setError] = useState(''), [cursor, setCursor] = useState<string | null>(snapshot?.cursor??null), [cursors, setCursors] = useState<(string | null)[]>(snapshot?.cursors??[null]), [page, setPage] = useState(snapshot?.page??0), [busy, setBusy] = useState(false);
    const [edit, setEdit] = useState<Subscription | null>(null), [editName, setEditName] = useState(''), [editNotes, setEditNotes] = useState(''), [command, setCommand] = useState('');
    const [add, setAdd] = useState({ name: '', x_handle: '', notes: '', rating: 'B', confirmed: false });
    const [filters,setFilters]=useState<Filters>(snapshot?.filters??emptyFilters);
    const [windowFrom,setWindowFrom]=useState<string|null>(snapshot?.windowFrom??null);
    const [totals,setTotals]=useState<Totals|null>(snapshot?.totals??null);
    const query=new URLSearchParams({profile:'published-v1',limit:'20',q:filters.query,ratings:filters.grade==='all'?'S,A,B':filters.grade});
    if(windowFrom)query.set('from_at',windowFrom);
    const viewKey = JSON.stringify([page, cursors[page], csrf,query.toString()]);
    function changeFilters(next:Filters){setFilters(next);setWindowFrom(next.hours==='all'?null:new Date(Date.now()-Number(next.hours)*3600000).toISOString());setPage(0);setCursors([null]);setLoading(true);}
    const latestView = useRef(viewKey);
    const mounted=useRef(true),readAt=useRef(Date.now());
    useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);
    latestView.current = viewKey;
    async function api(path: string, method = 'GET', body?: unknown, row?: Subscription) {
        const response = await fetch('/api/v1/' + path, { method, credentials: 'same-origin', cache: 'no-store', signal: AbortSignal.timeout(12000), headers: { 'content-type': 'application/json', 'x-csrf-token': csrf,...(path.startsWith('tracking/latest?')&&queryView.current?{'x-tracking-query-view':queryView.current}:{}), ...(method === 'GET' ? {} : { 'idempotency-key': crypto.randomUUID() }), ...(row ? { 'if-match': `"rev-${row.revision}"` } : {}) }, ...(body !== undefined ? { body: JSON.stringify(body) } : {}) });
        const value = await response.json();
        if (!response.ok) {
            if(response.status===403)clearClientSession();
            if (response.status === 401) {
                clearClientSession();
                voice.revoke();
                location.assign('/login?next=/tracking');
            }
            throw Error((value.error?.code || 'ERROR') + ' · ' + (value.error?.message || '请求失败') + ' · ' + value.request_id);
        }
        if(method!=='GET')invalidateClientData(scope);
        return value.data;
    }
    pull.current = async () => {
        const key = viewKey;
        try {
            const started=Date.now(),path='tracking/latest?'+query.toString()+(cursors[page]?'&cursor='+encodeURIComponent(cursors[page]!):'');
            const [rows,data]=await Promise.all([loadTrackingSubscriptions(scope,true),readClientData(scope,path+'|'+queryView.current,()=>api(path),750)]);
            const visible = rows.filter(r => !(r.desired_state === 'removed' && r.observed_state === 'absent' && r.operation_state === 'succeeded'));
            if (!mounted.current||latestView.current !== key)return;
            if(data.items.some((item:Activity)=>!rows.some(row=>row.subscription_id===item.subscription_id)))throw Error("VERSION_CONFLICT · 订阅投影已变化，请刷新");
            const grades=new Map<string,Activity['rating']>(data.items.map((item:Activity)=>[item.subscription_id,item.rating]));
            const accountRows:Account[]=rows.map(row=>({ui_key:row.subscription_id,name:row.name,handle:row.x_handle,note:row.error_code ? row.notes+' · 失败原因：'+row.error_code : row.notes,grade:row.rating===undefined?grades.get(row.subscription_id)??null:row.rating,avatar:row.name.slice(0,1),status:row.error_code||row.operation_state==='failed'?'failed':row.desired_state==='running'&&row.observed_state==='running'&&row.connection==='connected'?'running':row.operation_state==='unknown'||row.observed_state==='unknown'?'unknown':row.desired_state!=='running'?(row.observed_state==='absent'?'stopped':'stopping'):row.operation_state==='succeeded'&&row.observed_state==='running'&&row.connection==='connected'?'running':'starting'}));
            const postRows:Post[]=data.items.map((item:Activity)=>({ui_key:item.activity_id,account_key:item.subscription_id,published_at:item.occurred_at,received_at:item.received_at,body:item.text,translation_zh:item.translation_zh??null,quoted_tweet:item.quoted_tweet??null,tweet_kind:item.tweet_kind,important:null,comments:'未知',reposts:'未知',likes:'未知',media:null,media_available:false,original_url:item.url}));setPosts(postRows);
            setTotals({matchedTotal:data.matched_total,subscriptionCounts:data.subscription_counts_by_rating});
            setCursor(data.next_cursor);
            setSubs(rows);
            setAccounts(accountRows.filter(account=>visible.some(row=>row.subscription_id===account.ui_key)));
            setHistoryAccounts(accountRows);
            readAt.current=started;saveClientData(scope,'tracking:view',{subs:rows,posts:postRows,accounts:accountRows.filter(account=>visible.some(row=>row.subscription_id===account.ui_key)),historyAccounts:accountRows,cursor:data.next_cursor,totals:{matchedTotal:data.matched_total,subscriptionCounts:data.subscription_counts_by_rating},filters,windowFrom,page,cursors,queryView:queryView.current});
            setError('');
        }
        catch (e) {
            if (!mounted.current||latestView.current !== key)
                return;
            const message=(e as Error).message;
            if(message.startsWith('VERSION_CONFLICT')&&page>0){setPage(0);setCursors([null]);}
            setError(message+' · 当前显示上次成功结果');
            setAccounts(previous => previous.map(row => ({ ...row, status: 'unknown' })));
        }
        finally {
            if (mounted.current&&latestView.current === key)
                setLoading(false);
        }
    };
    useEffect(() => { const timer=setTimeout(()=>void refresh(),filters.query?200:0);return()=>clearTimeout(timer); }, [viewKey, refresh]);
    useEffect(() => {
        const timer = setInterval(() => void refresh(), 15000);
        let eventTimer:ReturnType<typeof setTimeout>|undefined;
        const reload = (event: Event) => {
            if(event.type==='open'||event.type==='error')return;
            if(event.type.startsWith('tracking.feed.activity.')){try{if(JSON.parse((event as MessageEvent).data).data?.replay===true)return;}catch{return;}}
            try{const value=JSON.parse((event as MessageEvent).data).data;const at=Date.parse(value.updated_at||value.received_at||'');if(Number.isFinite(at)&&at<=readAt.current)return;}catch{return;}
            if (event.type === 'command.updated') {
                try {
                    const value = JSON.parse((event as MessageEvent).data).data;
                    setCommand(value.command_id + ' · ' + value.state + (value.error_code ? ' · ' + (value.error_code === 'quota_exhausted' ? 'NEW_TWEET名额不足（600），请人工删减' : value.error_code) : ''));
                }
                catch { }
            }
            clearTimeout(eventTimer);eventTimer=setTimeout(()=>void refresh(),250);
            // The 15s poll picks up translations; no extra 5s/12s reload for every individual tweet.
        };
        const unsubscribe=subscribeTrackingEvents(reload);
        return () => { clearInterval(timer);clearTimeout(eventTimer);unsubscribe(); };
    }, [refresh]);
    async function refreshAfterWrite(){await refresh.settled();invalidateClientData(scope);await refresh();}
    async function operate(row: Subscription, operation: string) {
        if (busy)
            return;
        setBusy(true);
        try {
            const fresh=await api('tracking/subscriptions/'+row.subscription_id);
            const value = await api('tracking/subscriptions/' + row.subscription_id + (operation === 'remove' ? '' : '/' + operation), operation === 'remove' ? 'DELETE' : 'POST', undefined, fresh);
            setCommand(value.command_id + ' · ' + value.state + '（受理不等于远端成功）');
            await refreshAfterWrite();
            return true;
        }
        catch (e) {
            setError((e as Error).message);
            return false;
        }
        finally {
            setBusy(false);
        }
    }
    // 2026-10-17: superadmin can promote a tracked project (possibly hidden) onto the homepage.
    async function addToHome(row: Subscription) {
        if (busy)
            return;
        setBusy(true);
        try {
            const project = await api('projects/' + row.project_id);
            if (project.home_membership === 'active') {
                setCommand('「' + (project.name || row.name) + '」已在主页');
                return;
            }
            await api('projects/' + row.project_id + '/home-membership', 'POST', { action: 'add' }, { revision: project.revision } as unknown as Subscription);
            setCommand('「' + (project.name || row.name) + '」已加入主页');
        }
        catch (e) {
            setError((e as Error).message);
        }
        finally {
            setBusy(false);
        }
    }
    async function create(event: FormEvent, close: () => void) {
        event.preventDefault();
        if (busy || !add.confirmed)
            return;
        setBusy(true);
        try {
            const value = await api('tracking/subscriptions', 'POST', { ...add, x_user_id: null });
            setCommand(value.command_id + ' · ' + value.state);
            close();
            setAdd({ name: '', x_handle: '', notes: '', rating: 'B', confirmed: false });
            await refreshAfterWrite();
        }
        catch (e) {
            setError((e as Error).message);
        }
        finally {
            setBusy(false);
        }
    }
    async function save() {
        if (!edit || busy)
            return;
        setBusy(true);
        try {
            const fresh=await api('tracking/subscriptions/'+edit.subscription_id);
            await api('tracking/subscriptions/' + edit.subscription_id, 'PATCH', { name: editName, notes: editNotes }, fresh);
            setEdit(null);
            await refreshAfterWrite();
        }
        catch (e) {
            setError((e as Error).message);
        }
        finally {
            setBusy(false);
        }
    }
    const connected=subs.some(row=>row.connection==='connected');
    return <>{!connected && !fixture && <Alert tone='warning' title='实时来源未连接' />}{fixture&&!connected&&<Alert title='本地模式 · 尚未连接实时来源' />}{error && <Alert tone='danger' title={error}/>} {command && (!command.startsWith('cmd_') || command.includes('名额不足')) && <Alert title={command.startsWith('cmd_') ? command.replace(/^cmd_\S+\s·\s/, '') : command}/>}<TrackingPage mode='live' accounts={accounts} posts={posts} loading={loading} onAdd={async () => { throw Error('使用人工确认项目表单'); }} onRemove={async (id) => {
            const row = subs.find(r => r.subscription_id === id);
            if (row && !(await operate(row, 'remove')))
                throw Error('移除未确认');
        }} live={{ connected,historyAccounts,server:{filters,onFiltersChange:changeFilters,matchedTotal:totals?.matchedTotal??null,subscriptionCounts:totals?.subscriptionCounts??null},accountMenu: <details><summary>{username}</summary><a href='/auth/password' onClick={voice.revoke}>修改本人密码</a><span onClickCapture={voice.revoke}><LogoutButton /></span></details>, canManage: canManage && !error && !busy, refresh: () => void refresh(), onOpenPost: post => {
                if (post.original_url && /^https:\/\/x\.com\/[A-Za-z0-9_]+\/status\/[0-9]+$/.test(post.original_url))
                    window.open(post.original_url, '_blank', 'noopener,noreferrer');
            },
            postActions: post => {
                const row = subs.find(r => r.subscription_id === post.account_key);
                return row ? <><Button size='sm' variant='ghost' disabled={busy} title='把这个项目放到主页“正在做”' onClick={() => void addToHome(row)}>加入主页</Button>{canManage && <Button size='sm' variant='ghost' disabled={busy} title='直接编辑主页上的重要时间、进度和备注' onClick={() => setHomeEdit({ project_id: row.project_id, name: row.name, tweet: post.translation_zh?.text ? post.translation_zh.text + '\n原文：' + post.body : post.body, quote: post.quoted_tweet?.text ?? null, received_at: post.received_at })}>编辑主页</Button>}{canManage && row.desired_state !== 'removed' && <Button size='sm' variant='ghost' disabled={busy} title='彻底移除这个账号的追踪（主页不变，旧推文保留）' onClick={() => setUntrack(row)}>取消追踪</Button>}</> : null;
            },
            manageActions: account => {
                const row = subs.find(r => r.subscription_id === account.ui_key);
                if (!row)
                    return null;
                return <><Button size='sm' disabled={busy} onClick={() => { setEdit(row); setEditName(row.name); setEditNotes(row.notes); }}>编辑</Button><Button size='sm' disabled={busy || row.operation_state === 'unknown' && row.observed_state !== 'running'} title={row.operation_state === 'unknown' && row.observed_state !== 'running' ? '结果待核实，禁止盲目重试' : undefined} onClick={() => void operate(row, row.desired_state === 'running' ? 'stop' : 'resume')}>{row.desired_state === 'running' ? '停止' : '恢复'}</Button><Button size='sm' disabled={busy} title='把这个项目放到主页“正在做”' onClick={() => void addToHome(row)}>加入主页</Button></>;
            },
            addForm: close => <form method='post' action='/tracking' onSubmit={event => void create(event, close)}>{error && <Alert tone='danger' title={error}/>}<Input label='项目名称' value={add.name} required maxLength={120} onChange={e => setAdd(v => ({ ...v, name: e.target.value }))}/><Input label='X 用户名（不含 @）' value={add.x_handle} required pattern='[A-Za-z0-9_]{1,15}' onChange={e => setAdd(v => ({ ...v, x_handle: e.target.value }))}/><Input label='监控备注' value={add.notes} maxLength={4000} onChange={e => setAdd(v => ({ ...v, notes: e.target.value }))}/><label>评分<select value={add.rating} onChange={e=>setAdd(v=>({...v,rating:e.target.value}))}>{['S','A','B'].map(r=><option key={r}>{r}</option>)}</select></label><label><input type='checkbox' checked={add.confirmed} onChange={e => setAdd(v => ({ ...v, confirmed: e.target.checked }))} required/>我已人工确认项目与 X 账号</label><Button type='submit' pending={busy}>确认加入监控</Button><Button onClick={close}>取消</Button></form>,
            pagination: <Panel><span>服务端发布时间排序 · 第 {page + 1} 页 · 匹配 {totals?.matchedTotal??"—"} 条 · 本页 {posts.length} 条</span><Button disabled={page === 0 || busy} onClick={() => { setLoading(true); setPage(v => v - 1); }}>上一页</Button><Button disabled={!cursor || busy} onClick={() => { setLoading(true); setCursors(v => [...v.slice(0, page + 1), cursor]); setPage(v => v + 1); }}>下一页</Button></Panel> }}/>
 <Dialog open={!!edit} title='编辑监控资料' onOpenChange={open => {
            if (!open && !busy)
                setEdit(null);
        }} pending={busy}><Input label='项目名称' value={editName} onChange={e => setEditName(e.target.value)}/><Input label='监控备注' value={editNotes} onChange={e => setEditNotes(e.target.value)}/><Button onClick={() => void save()} pending={busy}>保存资料</Button></Dialog>
 <TrackingHomeEditor target={homeEdit} csrf={csrf} canManage={canManage} onClose={() => setHomeEdit(null)} onSaved={message => setCommand(message)} />
 <Dialog open={!!untrack} title='取消追踪' destructive onOpenChange={open => { if (!open && !busy) setUntrack(null); }} pending={busy}><p>确定取消追踪「{untrack?.name}」{untrack?.x_handle ? ' @' + untrack.x_handle : ''} 吗？</p><p>会从追踪列表彻底移除，不再接收新推文；主页上的项目不变，之前的推文继续显示。以后要追踪需要重新添加。</p><div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}><Button disabled={busy} onClick={() => setUntrack(null)}>取消</Button><Button variant='danger' pending={busy} onClick={() => { const row = untrack; if (row) void operate(row, 'remove').then(ok => { if (ok) { setUntrack(null); setCommand('已取消追踪「' + row.name + '」'); } }); }}>确定取消追踪</Button></div></Dialog></>;
}
