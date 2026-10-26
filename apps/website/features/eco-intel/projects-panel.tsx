'use client';

import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { Badge, Button, DataTable, Dialog, EmptyState, ErrorState, Input, SearchInput, Select, ToastViewport, type TableColumn, type ToastMessage } from '@ikun/ui';
import { ACCOUNT_TYPES, TRACK_CHAINS, labelOf, type AccountType, type FollowRecord, type SeedRecord, type TrackChain } from '../../lib/eco-intel/types';
import { readItems, writeJson } from './client';
import { ProjectDrawer, draftDirty, draftFromFollow, formatTime, type EcoDraft } from './project-drawer';

const PER = 10;
const typeLabel = (row: FollowRecord) => labelOf(ACCOUNT_TYPES, row.account_type);
const chainLabel = (chain: string) => chain ? labelOf(TRACK_CHAINS, chain) : '未定';

function statusView(row: FollowRecord): { className: string; label: string } {
  if (row.track_state === 'submitted') return { className: 'joined', label: '已提交追踪' };
  if (row.track_state === 'queued') return { className: 'reviewed', label: '已排队' };
  if (row.classification === 'pending') return { className: 'reviewed', label: '待定' };
  if (row.classification === 'noise') return { className: '', label: '仅记录' };
  return { className: 'joined', label: '项目' };
}

export function ProjectsPanel({ csrf, canWrite, switcher }: { csrf: string; canWrite: boolean; switcher?: ReactNode }) {
  const [query, setQuery] = useState('');
  const [time, setTime] = useState('all');
  const [kind, setKind] = useState<'all' | 'project' | 'pending' | 'noise'>('all');
  const [trackFilter, setTrackFilter] = useState<'all' | 'none' | 'queued' | 'submitted'>('all');
  const [page, setPage] = useState(1);
  const [rows, setRows] = useState<FollowRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [messages, setMessages] = useState<ToastMessage[]>([]);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [editing, setEditing] = useState<EcoDraft | null>(null);
  const [source, setSource] = useState<FollowRecord | null>(null);
  const [confirmTrack, setConfirmTrack] = useState(false);
  const [discard, setDiscard] = useState(false);
  const [seeds, setSeeds] = useState<SeedRecord[]>([]);
  const [handle, setHandle] = useState('');
  const [seedHandle, setSeedHandle] = useState('');
  const [accountType, setAccountType] = useState<AccountType>('unclassified');
  const [draftChain, setDraftChain] = useState<'' | TrackChain>('');
  const [bio, setBio] = useState('');
  const [summary, setSummary] = useState('');
  const [adding, setAdding] = useState(false);
  const [now] = useState(() => Date.now());

  const say = (title: string, tone: ToastMessage['tone'] = 'info') => setMessages(current => [...current.slice(-2), { id: `intel-${Date.now()}`, title, tone }]);

  const load = useCallback(async (initial: boolean) => {
    if (initial) setLoading(true); else setRefreshing(true);
    setError(null);
    try {
      const [projects, logged] = await Promise.all([
        readItems<FollowRecord>('/api/v1/intel/follows?limit=100&view=projects'),
        readItems<FollowRecord>('/api/v1/intel/follows?limit=100&view=noise'),
      ]);
      setRows([...projects.items, ...logged.items]);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '列表不可用');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { void load(true); }, [load]);
  useEffect(() => {
    if (!canWrite) return;
    void readItems<SeedRecord>('/api/v1/intel/seeds?limit=100').then(pageResult => {
      setSeeds(pageResult.items);
      setSeedHandle(current => current || pageResult.items[0]?.x_handle || '');
    }).catch(() => setSeeds([]));
  }, [canWrite]);

  const filtered = rows.filter(row => {
    const q = query.trim().toLowerCase();
    if (q && !`${row.display_name} ${row.x_handle} ${row.bio} ${row.notes}`.toLowerCase().includes(q)) return false;
    if (kind !== 'all' && row.classification !== kind) return false;
    if (trackFilter !== 'all' && row.track_state !== trackFilter) return false;
    if (time !== 'all') {
      const at = Date.parse(row.occurred_at ?? row.created_at);
      if (!Number.isFinite(at) || now - at > Number(time) * 3600000) return false;
    }
    return true;
  });
  const pages = Math.max(1, Math.ceil(filtered.length / PER));
  const currentPage = Math.min(page, pages);
  const visible = filtered.slice((currentPage - 1) * PER, currentPage * PER);
  const dirty = !!editing && draftDirty(editing, source);

  function reset() {
    setQuery(''); setTime('all'); setKind('all'); setTrackFilter('all'); setPage(1);
  }

  function requestClose() {
    if (pendingId) return;
    if (dirty) setDiscard(true);
    else { setEditing(null); setSource(null); }
  }

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || !editing || confirmTrack || discard || adding || pendingId) return;
      event.preventDefault();
      if (dirty) setDiscard(true);
      else { setEditing(null); setSource(null); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [editing, confirmTrack, discard, adding, pendingId, dirty]);

  async function track(row: FollowRecord) {
    setPendingId(row.follow_id);
    try {
      const result = await writeJson<{ message: string }>(`/api/v1/intel/follows/${row.follow_id}/track`, 'POST', csrf, { confirmed: true }, row.revision);
      say(result.message);
      setConfirmTrack(false);
      setEditing(null);
      setSource(null);
      await load(false);
    } catch (cause) {
      say(cause instanceof Error ? cause.message : '项目追踪未确认', 'warning');
    } finally { setPendingId(null); }
  }

  async function saveEdit() {
    if (!editing?.follow_id) {
      say('没有对应的关注档案，未写入。', 'warning');
      return;
    }
    setPendingId(editing.follow_id);
    try {
      await writeJson(`/api/v1/intel/follows/${editing.follow_id}`, 'PATCH', csrf, {
        display_name: editing.display_name,
        notes: editing.notes,
        account_type: editing.account_type,
        chain: editing.chain,
      }, editing.revision);
      setEditing(null);
      setSource(null);
      say('项目资料已保存。分类已按本地规则重算。代币不会进入项目追踪。');
      await load(false);
    } catch (cause) {
      say(cause instanceof Error ? cause.message : '保存未确认', 'warning');
    } finally { setPendingId(null); }
  }

  async function addFollow() {
    setPendingId('add');
    try {
      await writeJson('/api/v1/intel/follows', 'POST', csrf, {
        x_handle: handle, seed_handle: seedHandle, account_type: accountType, chain: draftChain, bio, recent_summary: summary,
      });
      setHandle(''); setBio(''); setSummary(''); setAdding(false);
      say('关注已写入。协议、发射台、黑客松且链明确时记为项目；代币只留在仅记录。');
      await load(false);
    } catch (cause) {
      say(cause instanceof Error ? cause.message : '保存未确认', 'warning');
    } finally { setPendingId(null); }
  }

  function openEdit(row: FollowRecord) {
    setSource(row);
    setEditing(draftFromFollow(row));
  }

  const columns: TableColumn<FollowRecord>[] = [
    { key: 'time', header: '发现时间', width: '105px', render: row => <span className="date" data-selected={editing?.follow_id === row.follow_id ? 'true' : undefined}>{formatTime(row.occurred_at ?? row.created_at)}</span> },
    { key: 'name', header: 'X 账号', width: '175px', render: row => <div className="account"><span className="avatar" aria-hidden="true">{(row.display_name || row.x_handle).slice(0, 1)}</span><div className="account-info"><strong title={row.display_name || row.x_handle}>{row.display_name || row.x_handle}</strong><small>@{row.x_handle}</small></div></div> },
    { key: 'bio', header: '主页简介 / 项目线索', render: row => <div className="bio" title={row.bio}>{row.bio || '暂无简介'}</div> },
    { key: 'chain', header: '链', width: '110px', render: row => <span className="hunter-cell"><span className="hunter-number">{chainLabel(row.chain)}</span></span> },
    { key: 'type', header: '类型', width: '88px', render: row => typeLabel(row) },
    { key: 'class', header: '判定', width: '110px', render: row => { const view = statusView(row); return <span className={`status ${view.className}`}><i />{view.label}</span>; } },
    { key: 'actions', header: '操作', width: '168px', align: 'right', render: row => <div className="act">
      <Button size="sm" onClick={() => { const value = row.x_handle.trim().replace(/^@/, ''); if (value) window.open(`https://x.com/${encodeURIComponent(value)}`, '_blank', 'noopener,noreferrer'); }}>X 主页 ↗</Button>
      <Button size="sm" className="soft" disabled={pendingId === row.follow_id} onClick={() => openEdit(row)}>研究 / 编辑</Button>
    </div> },
  ];

  const projectCount = rows.filter(row => row.classification === 'project').length;
  const pendingCount = rows.filter(row => row.classification === 'pending').length;
  const noiseCount = rows.filter(row => row.classification === 'noise').length;
  const trackedCount = rows.filter(row => row.track_state === 'submitted').length;
  const start = filtered.length ? (currentPage - 1) * PER + 1 : 0;
  const end = Math.min(currentPage * PER, filtered.length);

  return <>
    <section className="discovery" aria-label="创始人关注的项目">
      <header className="top">
        <div className="crumb"><div>控制台 &nbsp;/&nbsp; <b>生态情报 · 创始人关注</b></div><Badge tone="warning" className="prototype-chip">本地分类 · 不连接 6551</Badge></div>
        <div className="header-row">
          <div>
            <h1 className="page-title">创始人关注 <span>/ Founder Follows</span></h1>
            <p className="subtitle">协议、发射台、黑客松，并且对应 BSC / Solana / ETH / Base / Robinhood Chain。代币不会自动进入项目追踪。</p>
          </div>
          <div className="title-buttons">{switcher}{canWrite && <Button className="soft" onClick={() => setAdding(true)}>＋ 补录关注</Button>}</div>
        </div>
        <div className="kpis">{[
          ['项目', projectCount, 'teal'],
          ['待定', pendingCount, 'yellow'],
          ['仅记录', noiseCount, ''],
          ['已提交追踪', trackedCount, 'blue'],
        ].map(([label, value, color]) => <div className="kpi" key={String(label)}><div className="kpi-top">{label}</div><strong className={String(color)}>{String(value).padStart(2, '0')}</strong></div>)}</div>
      </header>
      <section className="filters" aria-label="搜索和筛选">
        <div className="search-wrap"><SearchInput label="搜索项目" value={query} onValueChange={value => { setQuery(value); setPage(1); }} placeholder="搜索 X 账号、简介、项目名称…" /></div>
        <Select label="时间筛选" className="filter-select" value={time} onChange={event => { setTime(event.target.value); setPage(1); }}>
          <option value="all">全部时间</option>
          <option value="24">最近 24 小时</option>
          <option value="72">最近 72 小时</option>
          <option value="168">最近 7 天</option>
        </Select>
        <div className="seg" role="group" aria-label="判定筛选">
          {([['all', '全部'], ['project', '项目'], ['pending', '待定'], ['noise', '仅记录']] as const).map(([value, label]) => <Button key={value} aria-pressed={kind === value} className={kind === value ? 'on' : ''} onClick={() => { setKind(value); setPage(1); }}>{label}</Button>)}
        </div>
        <Select label="状态筛选" className="filter-select" value={trackFilter} onChange={event => { setTrackFilter(event.target.value as typeof trackFilter); setPage(1); }}>
          <option value="all">全部状态</option>
          <option value="none">未追踪</option>
          <option value="queued">已排队</option>
          <option value="submitted">已提交追踪</option>
        </Select>
        <Button variant="ghost" size="sm" onClick={reset}>↺ 重置</Button>
        <span className="f-right">{loading ? '—' : filtered.length} 条匹配发现</span>
      </section>
      <div className="table-shell">
        <div className="v3-table" data-mode={error && !rows.length ? 'error' : loading ? 'loading' : 'normal'}>
          <DataTable caption="创始人关注的项目" columns={columns} rows={loading ? [] : visible} rowKey={row => row.follow_id} loading={loading} refreshing={refreshing} minWidth={805}
            error={error ? <ErrorState title="项目列表不可用" description={error} onRetry={() => void load(false)} pending={refreshing} /> : undefined}
            empty={<EmptyState title="这条筛选下还没有项目" description="待定和仅记录可以在判定筛选里分开看。代币不会出现在项目里。" />} />
        </div>
      </div>
      <footer className="table-footer">
        <div>{loading ? '正在读取本地关注…' : `显示 ${start}–${end} / ${filtered.length} 条`}</div>
        <div className="page-controls">
          <span>{loading ? '— / —' : `${currentPage} / ${pages}`}</span>
          <Button size="sm" aria-label="上一页" disabled={loading || currentPage <= 1} onClick={() => setPage(currentPage - 1)}>‹</Button>
          <Button size="sm" aria-label="下一页" disabled={loading || currentPage >= pages} onClick={() => setPage(currentPage + 1)}>›</Button>
        </div>
      </footer>
    </section>
    {editing && <ProjectDrawer draft={editing} pending={!!pendingId} canWrite={canWrite} dirty={dirty} onChange={patch => setEditing(current => current ? { ...current, ...patch } : current)} onClose={requestClose} onSave={() => void saveEdit()} onTrack={() => { if (source?.track_eligible && source.track_state !== 'submitted') setConfirmTrack(true); }} />}
    <Dialog open={confirmTrack} onOpenChange={open => { if (!open && !pendingId) setConfirmTrack(false); }} title="加入项目追踪" pending={!!pendingId} footer={<>
      <Button data-dialog-cancel onClick={() => setConfirmTrack(false)}>取消</Button>
      <Button variant="primary" pending={pendingId === source?.follow_id} disabled={!source} onClick={() => { if (source) void track(source); }}>确认提交</Button>
    </>}>
      <div className="modal-size" data-size="small">
        <p className="modal-desc">确认把「{editing?.display_name || source?.display_name}」提交到现有猎手项目追踪吗？命令与 tracking.create 相同，不会另开一套监控，也不会调用 6551。</p>
      </div>
    </Dialog>
    <Dialog open={discard} destructive onOpenChange={open => { if (!open) setDiscard(false); }} title="放弃未保存的修改？" pending={false} footer={<>
      <Button data-dialog-cancel onClick={() => setDiscard(false)}>继续编辑</Button>
      <Button variant="danger" onClick={() => { setDiscard(false); setEditing(null); setSource(null); }}>放弃修改</Button>
    </>}>
      <div className="modal-size" data-size="small"><p className="modal-desc">当前资料尚未保存。放弃后将丢弃本次修改，包括规则预填。</p></div>
    </Dialog>
    <Dialog open={adding} onOpenChange={open => { if (!open && pendingId !== 'add') setAdding(false); }} title="补录关注" pending={pendingId === 'add'} footer={<>
      <Button data-dialog-cancel onClick={() => setAdding(false)}>取消</Button>
      <Button variant="primary" pending={pendingId === 'add'} onClick={() => void addFollow()}>添加关注</Button>
    </>}>
      <div className="modal-size">
        <p className="modal-desc">只写入本地 intel.db。类型和链按本地规则分类，不会自动加入猎手，也不会调用 6551。</p>
        <Input label="新账号" value={handle} maxLength={16} placeholder="@handle" onChange={event => setHandle(event.target.value)} />
        <Select label="哪个种子关注了 ta" value={seedHandle} onChange={event => setSeedHandle(event.target.value)}>{seeds.map(seed => <option key={seed.seed_id} value={seed.x_handle}>@{seed.x_handle}</option>)}</Select>
        <Select label="类型" value={accountType} onChange={event => setAccountType(event.target.value as AccountType)}>{ACCOUNT_TYPES.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</Select>
        <Select label="链" value={draftChain} onChange={event => setDraftChain(event.target.value as '' | TrackChain)}>
          <option value="">未定</option>
          {TRACK_CHAINS.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}
        </Select>
        <Input label="简介" value={bio} maxLength={1000} onChange={event => setBio(event.target.value)} />
        <Input label="近期推文摘要" value={summary} maxLength={2000} onChange={event => setSummary(event.target.value)} />
      </div>
    </Dialog>
    <ToastViewport messages={messages} onDismiss={id => setMessages(current => current.filter(item => item.id !== id))} />
  </>;
}
