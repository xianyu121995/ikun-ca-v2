'use client';

import { useCallback, useEffect, useState } from 'react';
import { Alert, Badge, Button, DataTable, Dialog, EmptyState, ErrorState, Input, Panel, SearchInput, Select, type TableColumn } from '@ikun/ui';
import { ACCOUNT_TYPES, labelOf, type AccountType, type FollowRecord, type SeedRecord } from '../../lib/eco-intel/types';
import { readItems, writeJson } from './client';
import s from './intel.module.css';

const statusLabel: Record<FollowRecord['status'], string> = { open: '待处理', promoted: '已升种子', dismissed: '已忽略' };

export function FollowsPanel({ csrf, canWrite }: { csrf: string; canWrite: boolean }) {
  const [query, setQuery] = useState('');
  const [applied, setApplied] = useState('');
  const [rows, setRows] = useState<FollowRecord[]>([]);
  const [seeds, setSeeds] = useState<SeedRecord[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [handle, setHandle] = useState('');
  const [seedHandle, setSeedHandle] = useState('');
  const [accountType, setAccountType] = useState<AccountType>('unclassified');
  const [bio, setBio] = useState('');
  const [summary, setSummary] = useState('');
  const [editing, setEditing] = useState<FollowRecord | null>(null);
  const [removing, setRemoving] = useState<FollowRecord | null>(null);

  const load = useCallback(async (initial: boolean, next?: string) => {
    if (initial && !next) setLoading(true); else setRefreshing(true);
    setError(null);
    try {
      const params = new URLSearchParams({ limit: '100' });
      if (applied) params.set('q', applied);
      if (next) params.set('cursor', next);
      const page = await readItems<FollowRecord>('/api/v1/intel/follows?' + params);
      setRows(current => next ? [...current, ...page.items] : page.items);
      setCursor(page.next_cursor);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '列表不可用');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [applied]);

  useEffect(() => { const timer = setTimeout(() => setApplied(query.trim()), 200); return () => clearTimeout(timer); }, [query]);
  useEffect(() => { void load(true); }, [load]);
  useEffect(() => {
    if (!canWrite) return;
    void readItems<SeedRecord>('/api/v1/intel/seeds?limit=100').then(page => {
      setSeeds(page.items);
      setSeedHandle(current => current || page.items[0]?.x_handle || '');
    }).catch(() => setSeeds([]));
  }, [canWrite]);

  async function addFollow() {
    setPending(true); setNotice(null);
    try {
      await writeJson('/api/v1/intel/follows', 'POST', csrf, {
        x_handle: handle, seed_handle: seedHandle, account_type: accountType, bio, recent_summary: summary,
      });
      setHandle(''); setBio(''); setSummary(''); setNotice('新关注已写入本地表。');
      await load(false);
    } catch (cause) {
      setNotice(cause instanceof Error ? cause.message : '保存未确认');
    } finally { setPending(false); }
  }

  async function saveEdit() {
    if (!editing) return;
    setPending(true);
    try {
      await writeJson(`/api/v1/intel/follows/${editing.follow_id}`, 'PATCH', csrf, {
        notes: editing.notes, account_type: editing.account_type, status: editing.status === 'promoted' ? undefined : editing.status,
      }, editing.revision);
      setEditing(null); setNotice('关注记录已更新。类型会重新计算是否建议升为种子。');
      await load(false);
    } catch (cause) {
      setNotice(cause instanceof Error ? cause.message : '更新未确认');
    } finally { setPending(false); }
  }

  async function promote(row: FollowRecord) {
    setPending(true); setNotice(null);
    try {
      await writeJson(`/api/v1/intel/follows/${row.follow_id}/promote`, 'POST', csrf, {}, row.revision);
      setNotice(`@${row.x_handle} 已升为种子。后续推文观察仍等待 6551 WSS。`);
      await load(false);
    } catch (cause) {
      setNotice(cause instanceof Error ? cause.message : '升格未确认');
    } finally { setPending(false); }
  }

  async function remove() {
    if (!removing) return;
    setPending(true);
    try {
      await writeJson(`/api/v1/intel/follows/${removing.follow_id}`, 'DELETE', csrf, {}, removing.revision);
      setRemoving(null); setNotice('关注记录已移除。');
      await load(false);
    } catch (cause) {
      setNotice(cause instanceof Error ? cause.message : '移除未确认');
    } finally { setPending(false); }
  }

  const columns: TableColumn<FollowRecord>[] = [
    { key: 'handle', header: '新关注', width: '150px', render: row => <><strong>@{row.x_handle}</strong><div>{row.display_name}</div></> },
    { key: 'seed', header: '来源种子', width: '130px', render: row => row.seed_handle ? `@${row.seed_handle}` : '—' },
    { key: 'type', header: '类型', width: '130px', render: row => labelOf(ACCOUNT_TYPES, row.account_type) },
    { key: 'bio', header: '简介 / 近期', render: row => <span className={s.clamp}>{row.bio || '—'}{row.recent_summary ? ` / ${row.recent_summary}` : ''}</span> },
    { key: 'advice', header: '建议', width: '140px', render: row => row.promote_suggested ? <Badge tone="success">升为种子并看推文</Badge> : <Badge tone="neutral">仅记录</Badge> },
    { key: 'status', header: '状态', width: '100px', render: row => statusLabel[row.status] },
    { key: 'notes', header: '备注', width: '160px', render: row => <span className={s.clamp}>{row.notes || '—'}</span> },
    { key: 'actions', header: '操作', width: '220px', render: row => canWrite ? <span className={s.actions}>
      <Button size="sm" onClick={() => setEditing({ ...row })}>编辑</Button>
      {row.status !== 'promoted' && <Button size="sm" variant="primary" pending={pending} onClick={() => void promote(row)}>升为种子</Button>}
      {row.status !== 'promoted' && <Button size="sm" variant="danger" onClick={() => setRemoving(row)}>移除</Button>}
    </span> : <span>只读</span> },
  ];

  return <>
    <Alert tone="info" title="分类规则">新协议、发射台、黑客松项目会建议升为种子并继续看推文。创始人个人、新币和无关只记录。AI 判断尚未接入，类型目前来自夹具或手工选择。</Alert>
    {notice && <Alert tone="info" title="新关注">{notice}</Alert>}
    <SearchInput label="搜索新关注" value={query} onValueChange={setQuery} placeholder="搜索账号、种子、简介或备注" />
    {canWrite && <Panel title="补录一条新关注" description="TODO(6551)：正式数据应来自种子账号的关注事件，而不是手工录入。">
      <div className={s.form}>
        <Input label="新账号" value={handle} maxLength={16} placeholder="@handle" onChange={event => setHandle(event.target.value)} />
        <Select label="哪个种子关注了 ta" value={seedHandle} onChange={event => setSeedHandle(event.target.value)}>{seeds.map(seed => <option key={seed.seed_id} value={seed.x_handle}>@{seed.x_handle}</option>)}</Select>
        <Select label="类型" value={accountType} onChange={event => setAccountType(event.target.value as AccountType)}>{ACCOUNT_TYPES.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</Select>
        <Input label="简介" value={bio} maxLength={1000} onChange={event => setBio(event.target.value)} />
        <Input label="近期推文摘要" value={summary} maxLength={2000} onChange={event => setSummary(event.target.value)} />
        <Button variant="primary" pending={pending} onClick={() => void addFollow()}>添加关注</Button>
      </div>
    </Panel>}
    <DataTable caption="新关注" columns={columns} rows={rows} rowKey={row => row.follow_id} loading={loading} refreshing={refreshing} minWidth={1100}
      error={error ? <ErrorState title="新关注列表不可用" description={error} onRetry={() => void load(false)} pending={refreshing} /> : undefined}
      empty={<EmptyState title="还没有新关注" description="WSS 未接入。可以手工补录，或使用建库时写入的夹具。" />} />
    {cursor && <div className={s.more}><Button onClick={() => void load(false, cursor)} pending={refreshing}>加载更多</Button></div>}
    <Dialog open={!!editing} onOpenChange={open => { if (!open) setEditing(null); }} title="编辑新关注" pending={pending} footer={<>
      <Button data-dialog-cancel onClick={() => setEditing(null)}>取消</Button>
      <Button variant="primary" pending={pending} onClick={() => void saveEdit()}>保存</Button>
    </>}>
      {editing && <div className={s.form}>
        <Input label="账号" value={`@${editing.x_handle}`} readOnly />
        <Select label="类型" value={editing.account_type} onChange={event => setEditing({ ...editing, account_type: event.target.value as AccountType })}>{ACCOUNT_TYPES.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</Select>
        {editing.status !== 'promoted' && <Select label="状态" value={editing.status} onChange={event => setEditing({ ...editing, status: event.target.value as FollowRecord['status'] })}>
          <option value="open">待处理</option>
          <option value="dismissed">忽略</option>
        </Select>}
        <Input label="备注" value={editing.notes} maxLength={2000} onChange={event => setEditing({ ...editing, notes: event.target.value })} />
      </div>}
    </Dialog>
    <Dialog open={!!removing} destructive onOpenChange={open => { if (!open) setRemoving(null); }} title="移除新关注" pending={pending} footer={<>
      <Button data-dialog-cancel onClick={() => setRemoving(null)}>取消</Button>
      <Button variant="danger" pending={pending} onClick={() => void remove()}>确认移除</Button>
    </>}>
      <p>移除 @{removing?.x_handle} 的关注记录。这不会改动猎手名单。</p>
    </Dialog>
  </>;
}
