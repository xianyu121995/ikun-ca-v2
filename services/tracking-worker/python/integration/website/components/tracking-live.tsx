'use client';
import { useEffect, useState, useRef, type FormEvent } from 'react';
import { Alert, Button, Dialog, Input, Panel } from '@ikun/ui';
import { LogoutButton } from './auth/forms';
import { TrackingPage } from '../features/tracking/final/tracking-page';
import { emptyFilters, type Account, type Post, type Filters } from '../features/tracking/final/model';
import { coalescedRefresh } from '../lib/coalesced-refresh';
type Subscription = {
    subscription_id: string;
    project_id: string;
    name: string;
    x_handle: string;
    notes: string;
    revision: number;
    desired_state: string;
    observed_state: string;
    operation_state: string;
    connection: string;
};
type Activity = {activity_id:string;subscription_id:string;project_id:string;name:string;x_handle:string;notes:string;rating:'S'|'A'|'B';rating_revision:number;text:string;occurred_at:string|null;received_at:string;sort_at:string;sort_basis:string;url:string};
export function TrackingLive({ csrf, canManage, username, fixture = false }: {
    csrf: string;
    canManage: boolean;
    username: string;
    fixture?:boolean;
}) {
    const pull = useRef<() => Promise<void>>(async () => { });
    const refreshRef = useRef<ReturnType<typeof coalescedRefresh> | null>(null);
    if (!refreshRef.current)
        refreshRef.current = coalescedRefresh(() => pull.current());
    const refresh = refreshRef.current;
    const [subs, setSubs] = useState<Subscription[]>([]), [accounts, setAccounts] = useState<Account[]>([]), [posts, setPosts] = useState<Post[]>([]);
    const [loading, setLoading] = useState(true), [error, setError] = useState(''), [cursor, setCursor] = useState<string | null>(null), [cursors, setCursors] = useState<(string | null)[]>([null]), [page, setPage] = useState(0), [busy, setBusy] = useState(false);
    const [edit, setEdit] = useState<Subscription | null>(null), [editName, setEditName] = useState(''), [editNotes, setEditNotes] = useState(''), [command, setCommand] = useState('');
    const [add, setAdd] = useState({ project_id: '', name: '', x_handle: '', notes: '', confirmed: false });
    const [filters,setFilters]=useState<Filters>(emptyFilters);
    const [windowFrom,setWindowFrom]=useState<string|null>(null);
    const [totals,setTotals]=useState<{matchedTotal:number;subscriptionCounts:{S:number;A:number;B:number}}|null>(null);
    const query=new URLSearchParams({profile:'published-v1',limit:'6',q:filters.query,ratings:filters.grade==='all'?'S,A,B':filters.grade});
    if(windowFrom)query.set('from_at',windowFrom);
    const viewKey = JSON.stringify([page, cursors[page], csrf,query.toString()]);
    function changeFilters(next:Filters){setFilters(next);setWindowFrom(next.hours==='all'?null:new Date(Date.now()-Number(next.hours)*3600000).toISOString());setPage(0);setCursors([null]);setLoading(true);}
    const latestView = useRef(viewKey);
    latestView.current = viewKey;
    async function api(path: string, method = 'GET', body?: unknown, row?: Subscription) {
        const response = await fetch('/api/v1/' + path, { method, credentials: 'same-origin', cache: 'no-store', signal: AbortSignal.timeout(12000), headers: { 'content-type': 'application/json', 'x-csrf-token': csrf, ...(method === 'GET' ? {} : { 'idempotency-key': crypto.randomUUID() }), ...(row ? { 'if-match': `"rev-${row.revision}"` } : {}) }, ...(body !== undefined ? { body: JSON.stringify(body) } : {}) });
        const value = await response.json();
        if (!response.ok) {
            if (response.status === 401)
                location.assign('/login?next=/tracking');
            throw Error((value.error?.code || 'ERROR') + ' · ' + (value.error?.message || '请求失败') + ' · ' + value.request_id);
        }
        return value.data;
    }
    pull.current = async () => {
        const key = viewKey;
        try {
            const rows: Subscription[] = [];
            let next: string | null = null;
            do {
                const data = await api('tracking/subscriptions?limit=100&include_removed=true' + (next ? '&cursor=' + encodeURIComponent(next) : ''));
                rows.push(...data.items);
                next = data.next_cursor;
                if (rows.length > 1000)
                    throw Error('列表超过本地预览上限');
            } while (next);
            const visible = rows.filter(r => !(r.desired_state === 'removed' && r.observed_state === 'absent' && r.operation_state === 'succeeded'));
            const data = await api('tracking/latest?'+query.toString()+(cursors[page]?'&cursor='+encodeURIComponent(cursors[page]!):''));
            if (latestView.current !== key)return;
            if(data.items.some((item:Activity)=>!visible.some(row=>row.subscription_id===item.subscription_id)))throw Error("VERSION_CONFLICT · 订阅投影已变化，请刷新");
            const grades=new Map<string,Activity['rating']>(data.items.map((item:Activity)=>[item.subscription_id,item.rating]));
            const accountRows:Account[]=visible.map(row=>({ui_key:row.subscription_id,name:row.name,handle:row.x_handle,note:row.notes,grade:grades.get(row.subscription_id)??null,avatar:row.name.slice(0,1),status:row.operation_state==='unknown'||row.observed_state==='unknown'?'unknown':row.operation_state==='failed'?'failed':row.desired_state!=='running'?(row.observed_state==='absent'?'stopped':'stopping'):row.operation_state==='succeeded'&&row.observed_state==='running'&&row.connection==='connected'?'running':'starting'}));
            setPosts(data.items.map((item:Activity)=>({ui_key:item.activity_id,account_key:item.subscription_id,published_at:item.occurred_at,received_at:item.received_at,body:item.text,important:null,comments:'未知',reposts:'未知',likes:'未知',media:null,media_available:false,original_url:item.url})));
            setTotals({matchedTotal:data.matched_total,subscriptionCounts:data.subscription_counts_by_rating});
            setCursor(data.next_cursor);
            setSubs(rows);
            setAccounts(accountRows);
            setError('');
        }
        catch (e) {
            if (latestView.current !== key)
                return;
            const message=(e as Error).message;
            if(message.startsWith('VERSION_CONFLICT')&&page>0){setPage(0);setCursors([null]);}
            setError(message+' · 当前显示上次成功结果');
            setAccounts(previous => previous.map(row => ({ ...row, status: 'unknown' })));
        }
        finally {
            if (latestView.current === key)
                setLoading(false);
        }
    };
    useEffect(() => { const timer=setTimeout(()=>void refresh(),250);return()=>clearTimeout(timer); }, [viewKey, refresh]);
    useEffect(() => {
        const timer = setInterval(() => void refresh(), 15000);
        const events = new EventSource('/api/v1/events/stream');
        let eventTimer:ReturnType<typeof setTimeout>|undefined;
        const reload = (event: Event) => {
            if(event.type.startsWith('tracking.feed.activity.')){try{if(JSON.parse((event as MessageEvent).data).data?.replay===true)return;}catch{return;}}
            if (event.type === 'command.updated') {
                try {
                    const value = JSON.parse((event as MessageEvent).data).data;
                    setCommand(value.command_id + ' · ' + value.state + (value.error_code ? ' · ' + (value.error_code === 'quota_exhausted' ? 'NEW_TWEET名额不足（600），请人工删减' : value.error_code) : ''));
                }
                catch { }
            }
            clearTimeout(eventTimer);eventTimer=setTimeout(()=>void refresh(),250);
        };
        for (const type of ['tracking.feed.activity.created.v1','tracking.feed.activity.updated.v1', 'tracking.subscription.updated', 'command.updated'])
            events.addEventListener(type, reload);
        return () => { clearInterval(timer);clearTimeout(eventTimer); events.close(); };
    }, [refresh]);
    async function operate(row: Subscription, operation: string) {
        if (busy)
            return;
        setBusy(true);
        try {
            const value = await api('tracking/subscriptions/' + row.subscription_id + (operation === 'remove' ? '' : '/' + operation), operation === 'remove' ? 'DELETE' : 'POST', undefined, row);
            setCommand(value.command_id + ' · ' + value.state + '（受理不等于远端成功）');
            await refresh();
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
    async function create(event: FormEvent, close: () => void) {
        event.preventDefault();
        if (busy || !add.confirmed)
            return;
        setBusy(true);
        try {
            const value = await api('tracking/subscriptions', 'POST', { ...add, x_user_id: null });
            setCommand(value.command_id + ' · ' + value.state);
            close();
            setAdd({ project_id: '', name: '', x_handle: '', notes: '', confirmed: false });
            await refresh();
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
            await api('tracking/subscriptions/' + edit.subscription_id, 'PATCH', { name: editName, notes: editNotes }, edit);
            setEdit(null);
            await refresh();
        }
        catch (e) {
            setError((e as Error).message);
        }
        finally {
            setBusy(false);
        }
    }
    return <><Alert title='未连接真实来源' />{fixture&&<Alert title='本地验收夹具 · 合成数据仅供测试' />}{error && <Alert tone='danger' title={error}/>} {command && <Alert title={command}/>}<TrackingPage mode='live' accounts={accounts} posts={posts} loading={loading} onAdd={async () => { throw Error('使用人工确认项目表单'); }} onRemove={async (id) => {
            const row = subs.find(r => r.subscription_id === id);
            if (row && !(await operate(row, 'remove')))
                throw Error('移除未确认');
        }} live={{ server:{filters,onFiltersChange:changeFilters,matchedTotal:totals?.matchedTotal??null,subscriptionCounts:totals?.subscriptionCounts??null},accountMenu: <details><summary>{username}</summary><a href='/auth/password'>修改本人密码</a><LogoutButton /></details>, canManage: canManage && !error && !busy, refresh: () => void refresh(), onOpenPost: post => {
                if (post.original_url && /^https:\/\/x\.com\/[A-Za-z0-9_]+\/status\/[0-9]+$/.test(post.original_url))
                    window.open(post.original_url, '_blank', 'noopener,noreferrer');
            },
            manageActions: account => {
                const row = subs.find(r => r.subscription_id === account.ui_key);
                if (!row)
                    return null;
                return <><Button size='sm' disabled={busy} onClick={() => { setEdit(row); setEditName(row.name); setEditNotes(row.notes); }}>编辑</Button><Button size='sm' disabled={busy || row.operation_state === 'unknown'} title={row.operation_state === 'unknown' ? '结果待核实，禁止盲目重试' : undefined} onClick={() => void operate(row, row.desired_state === 'running' ? 'stop' : 'resume')}>{row.desired_state === 'running' ? '停止' : '恢复'}</Button></>;
            },
            addForm: close => <form method='post' action='/tracking' onSubmit={event => void create(event, close)}>{error && <Alert tone='danger' title={error}/>}<Input label='已注册项目 ID' value={add.project_id} required onChange={e => setAdd(v => ({ ...v, project_id: e.target.value }))}/><Input label='项目名称' value={add.name} required maxLength={120} onChange={e => setAdd(v => ({ ...v, name: e.target.value }))}/><Input label='X 用户名（不含 @）' value={add.x_handle} required pattern='[A-Za-z0-9_]{1,15}' onChange={e => setAdd(v => ({ ...v, x_handle: e.target.value }))}/><Input label='监控备注' value={add.notes} maxLength={4000} onChange={e => setAdd(v => ({ ...v, notes: e.target.value }))}/><label><input type='checkbox' checked={add.confirmed} onChange={e => setAdd(v => ({ ...v, confirmed: e.target.checked }))} required/>我已人工确认项目与 X 账号</label><Button type='submit' pending={busy}>确认加入监控</Button><Button onClick={close}>取消</Button></form>,
            pagination: <Panel><span>服务端发布时间排序 · 第 {page + 1} 页 · 匹配 {totals?.matchedTotal??"—"} 条 · 本页 {posts.length} 条</span><Button disabled={page === 0 || busy} onClick={() => { setLoading(true); setPage(v => v - 1); }}>上一页</Button><Button disabled={!cursor || busy} onClick={() => { setLoading(true); setCursors(v => [...v.slice(0, page + 1), cursor]); setPage(v => v + 1); }}>下一页</Button></Panel> }}/>
 <Dialog open={!!edit} title='编辑监控资料' onOpenChange={open => {
            if (!open && !busy)
                setEdit(null);
        }} pending={busy}><Input label='项目名称' value={editName} onChange={e => setEditName(e.target.value)}/><Input label='监控备注' value={editNotes} onChange={e => setEditNotes(e.target.value)}/><Button onClick={() => void save()} pending={busy}>保存资料</Button></Dialog></>;
}
