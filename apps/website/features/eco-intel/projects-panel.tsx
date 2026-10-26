'use client';

import { useCallback, useEffect, useState } from 'react';
import { Alert, Badge, Button, DataTable, Dialog, EmptyState, ErrorState, Input, Panel, SearchInput, Select, type TableColumn } from '@ikun/ui';
import { ACCOUNT_TYPES, TRACK_CHAINS, labelOf, type AccountType, type FollowRecord, type SeedRecord, type TrackChain } from '../../lib/eco-intel/types';
import { readItems, writeJson } from './client';
import s from './intel.module.css';

const typeLabel = (row: FollowRecord) => labelOf(ACCOUNT_TYPES, row.account_type);
const chainLabel = (chain: string) => chain ? labelOf(TRACK_CHAINS, chain) : '未定';

export function ProjectsPanel({ csrf, canWrite }: { csrf: string; canWrite: boolean }) {
  const [chain, setChain] = useState<'' | TrackChain>('');
  const [query, setQuery] = useState('');
  const [applied, setApplied] = useState('');
  const [rows, setRows] = useState<FollowRecord[]>([]);
  const [noise, setNoise] = useState<FollowRecord[]>([]);
  const [seeds, setSeeds] = useState<SeedRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [editing, setEditing] = useState<FollowRecord | null>(null);
  const [handle, setHandle] = useState('');
  const [seedHandle, setSeedHandle] = useState('');
  const [accountType, setAccountType] = useState<AccountType>('unclassified');
  const [draftChain, setDraftChain] = useState<'' | TrackChain>('');
  const [bio, setBio] = useState('');
  const [summary, setSummary] = useState('');

  const load = useCallback(async (initial: boolean) => {
    if (initial) setLoading(true); else setRefreshing(true);
    setError(null);
    try {
      const params = new URLSearchParams({ limit: '100', view: 'projects' });
      if (applied) params.set('q', applied);
      if (chain) params.set('chain', chain);
      const noiseParams = new URLSearchParams({ limit: '100', view: 'noise' });
      const [projects, logged] = await Promise.all([
        readItems<FollowRecord>('/api/v1/intel/follows?' + params),
        readItems<FollowRecord>('/api/v1/intel/follows?' + noiseParams),
      ]);
      setRows(projects.items);
      setNoise(logged.items);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '列表不可用');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [applied, chain]);

  useEffect(() => { const timer = setTimeout(() => setApplied(query.trim()), 200); return () => clearTimeout(timer); }, [query]);
  useEffect(() => { void load(true); }, [load]);
  useEffect(() => {
    if (!canWrite) return;
    void readItems<SeedRecord>('/api/v1/intel/seeds?limit=100').then(page => {
      setSeeds(page.items);
      setSeedHandle(current => current || page.items[0]?.x_handle || '');
    }).catch(() => setSeeds([]));
  }, [canWrite]);

  async function track(row: FollowRecord) {
    setPendingId(row.follow_id);
    setNotice(null);
    try {
      const result = await writeJson<{ message: string; delivery: string }>(`/api/v1/intel/follows/${row.follow_id}/track`, 'POST', csrf, { confirmed: true }, row.revision);
      setNotice(result.message);
      await load(false);
    } catch (cause) {
      setNotice(cause instanceof Error ? cause.message : '项目追踪未确认');
    } finally { setPendingId(null); }
  }

  async function saveEdit() {
    if (!editing) return;
    setPendingId(editing.follow_id);
    try {
      await writeJson(`/api/v1/intel/follows/${editing.follow_id}`, 'PATCH', csrf, {
        notes: editing.notes, account_type: editing.account_type, chain: editing.chain,
      }, editing.revision);
      setEditing(null);
      setNotice('分类已按本地规则重算。代币不会进入项目追踪。');
      await load(false);
    } catch (cause) {
      setNotice(cause instanceof Error ? cause.message : '校正未确认');
    } finally { setPendingId(null); }
  }

  async function addFollow() {
    setPendingId('add');
    setNotice(null);
    try {
      await writeJson('/api/v1/intel/follows', 'POST', csrf, {
        x_handle: handle, seed_handle: seedHandle, account_type: accountType, chain: draftChain, bio, recent_summary: summary,
      });
      setHandle(''); setBio(''); setSummary('');
      setNotice('关注已写入。协议、发射台、黑客松且链明确时会出现在上面；代币只留在仅记录。');
      await load(false);
    } catch (cause) {
      setNotice(cause instanceof Error ? cause.message : '保存未确认');
    } finally { setPendingId(null); }
  }

  const columns: TableColumn<FollowRecord>[] = [
    { key: 'name', header: '项目', width: '180px', render: row => <><strong>{row.display_name || row.x_handle}</strong><div>@{row.x_handle}</div></> },
    { key: 'chain', header: '链', width: '140px', render: row => chainLabel(row.chain) },
    { key: 'type', header: '类型', width: '110px', render: row => typeLabel(row) },
    { key: 'seed', header: '来源', width: '130px', render: row => row.seed_handle ? `@${row.seed_handle}` : '—' },
    { key: 'bio', header: '简介', render: row => <span className={s.clamp}>{row.bio || '—'}</span> },
    { key: 'class', header: '判定', width: '100px', render: row => row.classification === 'pending' ? <Badge tone="warning">待定</Badge> : <Badge tone="success">项目</Badge> },
    { key: 'actions', header: '操作', width: '220px', render: row => canWrite ? <span className={s.actions}>
      <Button size="sm" variant="primary" pending={pendingId === row.follow_id} disabled={row.track_state === 'submitted'} onClick={() => void track(row)}>
        {row.track_state === 'submitted' ? '已提交追踪' : row.track_state === 'queued' ? '重试项目追踪' : '项目追踪'}
      </Button>
      <Button size="sm" onClick={() => setEditing({ ...row })}>校正</Button>
    </span> : <span>只读</span> },
  ];

  const noiseColumns: TableColumn<FollowRecord>[] = [
    { key: 'name', header: '账号', width: '180px', render: row => <><strong>@{row.x_handle}</strong><div>{row.display_name}</div></> },
    { key: 'type', header: '类型', width: '110px', render: row => typeLabel(row) },
    { key: 'chain', header: '链', width: '140px', render: row => chainLabel(row.chain) },
    { key: 'bio', header: '简介', render: row => <span className={s.clamp}>{row.bio || '—'}</span> },
    { key: 'why', header: '处理', width: '120px', render: () => <Badge tone="neutral">仅记录</Badge> },
    { key: 'actions', header: '操作', width: '90px', render: row => canWrite ? <Button size="sm" onClick={() => setEditing({ ...row })}>校正</Button> : <span>只读</span> },
  ];

  return <>
    <Alert tone="info" title="什么会出现在这里">协议、发射台、黑客松，并且能对应 BSC / Solana / ETH / Base / Robinhood Chain。代币不会自动进入项目追踪。简介不清楚的记为待定，可以手工点项目追踪，但不会自动加入猎手。</Alert>
    {notice && <Alert tone="info" title="项目追踪">{notice}</Alert>}
    <div className={s.filters} role="group" aria-label="按链筛选">
      <button type="button" aria-pressed={chain === ''} onClick={() => setChain('')}>全部</button>
      {TRACK_CHAINS.map(item => <button key={item.id} type="button" aria-pressed={chain === item.id} onClick={() => setChain(item.id)}>{item.label}</button>)}
    </div>
    <SearchInput label="搜索项目" value={query} onValueChange={setQuery} placeholder="搜索账号、种子或简介" />
    <DataTable caption="创始人关注的项目" columns={columns} rows={rows} rowKey={row => row.follow_id} loading={loading} refreshing={refreshing} minWidth={980}
      error={error ? <ErrorState title="项目列表不可用" description={error} onRetry={() => void load(false)} pending={refreshing} /> : undefined}
      empty={<EmptyState title="这条筛选下还没有项目" description="待定账号在「全部」里。代币、KOL 和交易所只出现在下方的仅记录。" />} />
    <details className={s.admin}>
      <summary>仅记录（不进入项目追踪） · {noise.length}</summary>
      <DataTable caption="仅记录的新关注" columns={noiseColumns} rows={noise} rowKey={row => row.follow_id} loading={loading} minWidth={720}
        empty={<EmptyState title="没有仅记录的关注" description="代币、KOL、媒体、交易所、个人和空投会留在这里。" />} />
    </details>
    {canWrite && <details className={s.admin}>
      <summary>补录关注（管理员）</summary>
      <Panel title="补录一条新关注" description="TODO(6551)：正式数据应来自种子账号的关注事件。类型和链按本地规则分类，不会自动加入猎手。">
        <div className={s.form}>
          <Input label="新账号" value={handle} maxLength={16} placeholder="@handle" onChange={event => setHandle(event.target.value)} />
          <Select label="哪个种子关注了 ta" value={seedHandle} onChange={event => setSeedHandle(event.target.value)}>{seeds.map(seed => <option key={seed.seed_id} value={seed.x_handle}>@{seed.x_handle}</option>)}</Select>
          <Select label="类型" value={accountType} onChange={event => setAccountType(event.target.value as AccountType)}>{ACCOUNT_TYPES.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</Select>
          <Select label="链" value={draftChain} onChange={event => setDraftChain(event.target.value as '' | TrackChain)}>
            <option value="">未定</option>
            {TRACK_CHAINS.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}
          </Select>
          <Input label="简介" value={bio} maxLength={1000} onChange={event => setBio(event.target.value)} />
          <Input label="近期推文摘要" value={summary} maxLength={2000} onChange={event => setSummary(event.target.value)} />
          <Button variant="primary" pending={pendingId === 'add'} onClick={() => void addFollow()}>添加关注</Button>
        </div>
      </Panel>
    </details>}
    <Dialog open={!!editing} onOpenChange={open => { if (!open) setEditing(null); }} title="校正分类" pending={!!pendingId} footer={<>
      <Button data-dialog-cancel onClick={() => setEditing(null)}>取消</Button>
      <Button variant="primary" pending={!!pendingId} onClick={() => void saveEdit()}>保存</Button>
    </>}>
      {editing && <div className={s.form}>
        <Input label="账号" value={`@${editing.x_handle}`} readOnly />
        <Select label="类型" value={editing.account_type} onChange={event => setEditing({ ...editing, account_type: event.target.value as AccountType })}>{ACCOUNT_TYPES.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</Select>
        <Select label="链" value={editing.chain} onChange={event => setEditing({ ...editing, chain: event.target.value as TrackChain | '' })}>
          <option value="">未定</option>
          {TRACK_CHAINS.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}
        </Select>
        <Input label="备注" value={editing.notes} maxLength={2000} onChange={event => setEditing({ ...editing, notes: event.target.value })} />
      </div>}
    </Dialog>
  </>;
}
