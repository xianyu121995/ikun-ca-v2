'use client';

import { useCallback, useEffect, useState } from 'react';
import { Alert, Badge, Button, DataTable, Dialog, EmptyState, ErrorState, Input, Panel, SearchInput, Select, type TableColumn } from '@ikun/ui';
import { ECOSYSTEMS, labelOf, type Ecosystem, type SeedRecord } from '../../lib/eco-intel/types';
import { readItems, writeJson } from './client';
import s from './intel.module.css';

const sourceLabel: Record<SeedRecord['source'], string> = { fixture: '夹具', manual: '手工', promoted: '升格' };

export function SeedsPanel({ csrf, canWrite }: { csrf: string; canWrite: boolean }) {
  const [query, setQuery] = useState('');
  const [applied, setApplied] = useState('');
  const [rows, setRows] = useState<SeedRecord[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [handle, setHandle] = useState('');
  const [ecosystem, setEcosystem] = useState<Ecosystem>('bsc');
  const [role, setRole] = useState('官方');
  const [notes, setNotes] = useState('');
  const [editing, setEditing] = useState<SeedRecord | null>(null);
  const [removing, setRemoving] = useState<SeedRecord | null>(null);

  const load = useCallback(async (initial: boolean, next?: string) => {
    if (initial && !next) setLoading(true); else setRefreshing(true);
    setError(null);
    try {
      const params = new URLSearchParams({ limit: '100' });
      if (applied) params.set('q', applied);
      if (next) params.set('cursor', next);
      const page = await readItems<SeedRecord>('/api/v1/intel/seeds?' + params);
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

  async function addSeed() {
    setPending(true); setNotice(null);
    try {
      await writeJson('/api/v1/intel/seeds', 'POST', csrf, { x_handle: handle, ecosystem, role_label: role, notes, enabled: true });
      setHandle(''); setNotes(''); setNotice('种子已保存到本地 intel.db。');
      await load(false);
    } catch (cause) {
      setNotice(cause instanceof Error ? cause.message : '保存未确认');
    } finally { setPending(false); }
  }

  async function saveEdit() {
    if (!editing) return;
    setPending(true);
    try {
      await writeJson(`/api/v1/intel/seeds/${editing.seed_id}`, 'PATCH', csrf, {
        ecosystem: editing.ecosystem, role_label: editing.role_label, notes: editing.notes, enabled: editing.enabled,
      }, editing.revision);
      setEditing(null); setNotice('种子已更新。');
      await load(false);
    } catch (cause) {
      setNotice(cause instanceof Error ? cause.message : '更新未确认');
    } finally { setPending(false); }
  }

  async function remove() {
    if (!removing) return;
    setPending(true);
    try {
      await writeJson(`/api/v1/intel/seeds/${removing.seed_id}`, 'DELETE', csrf, {}, removing.revision);
      setRemoving(null); setNotice('种子已移除。相关推文仍保留账号名。');
      await load(false);
    } catch (cause) {
      setNotice(cause instanceof Error ? cause.message : '移除未确认');
    } finally { setPending(false); }
  }

  const columns: TableColumn<SeedRecord>[] = [
    { key: 'handle', header: 'X 账号', width: '160px', render: row => <strong>@{row.x_handle}</strong> },
    { key: 'ecosystem', header: '生态', width: '110px', render: row => labelOf(ECOSYSTEMS, row.ecosystem) },
    { key: 'role', header: '角色', width: '120px', render: row => row.role_label || '—' },
    { key: 'enabled', header: '状态', width: '90px', render: row => <Badge tone={row.enabled ? 'success' : 'neutral'}>{row.enabled ? '启用' : '停用'}</Badge> },
    { key: 'source', header: '来源', width: '80px', render: row => sourceLabel[row.source] },
    { key: 'notes', header: '备注', render: row => <span className={s.clamp}>{row.notes || '—'}</span> },
    { key: 'actions', header: '操作', width: '180px', render: row => canWrite ? <span className={s.actions}>
      <Button size="sm" onClick={() => setEditing({ ...row })}>编辑</Button>
      <Button size="sm" variant="danger" onClick={() => setRemoving(row)}>移除</Button>
    </span> : <span>只读</span> },
  ];

  return <>
    {notice && <Alert tone="info" title="种子账号">{notice}</Alert>}
    {!canWrite && <Alert tone="warning" title="只读">当前账号不能修改种子列表。</Alert>}
    <SearchInput label="搜索种子" value={query} onValueChange={setQuery} placeholder="搜索用户名、角色或备注" />
    {canWrite && <Panel title="添加种子" description="只写入本地 intel.db，不会调用 6551 或改动猎手 Watch。">
      <div className={s.form}>
        <Input label="X 用户名" value={handle} maxLength={16} placeholder="@handle" onChange={event => setHandle(event.target.value)} />
        <Select label="生态" value={ecosystem} onChange={event => setEcosystem(event.target.value as Ecosystem)}>{ECOSYSTEMS.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</Select>
        <Input label="角色" value={role} maxLength={40} placeholder="官方 / 创始人 / 发射台" onChange={event => setRole(event.target.value)} />
        <Input label="备注" value={notes} maxLength={2000} onChange={event => setNotes(event.target.value)} />
        <Button variant="primary" pending={pending} onClick={() => void addSeed()}>添加种子</Button>
      </div>
    </Panel>}
    <DataTable caption="种子账号" columns={columns} rows={rows} rowKey={row => row.seed_id} loading={loading} refreshing={refreshing} minWidth={920}
      error={error ? <ErrorState title="种子列表不可用" description={error} onRetry={() => void load(false)} pending={refreshing} /> : undefined}
      empty={<EmptyState title="还没有种子" description="超级管理员可以添加 X 账号。默认夹具会在首次建库时写入。" />} />
    {cursor && <div className={s.more}><Button onClick={() => void load(false, cursor)} pending={refreshing}>加载更多</Button></div>}
    <Dialog open={!!editing} onOpenChange={open => { if (!open) setEditing(null); }} title="编辑种子" pending={pending} footer={<>
      <Button data-dialog-cancel onClick={() => setEditing(null)}>取消</Button>
      <Button variant="primary" pending={pending} onClick={() => void saveEdit()}>保存</Button>
    </>}>
      {editing && <div className={s.form}>
        <Input label="X 用户名" value={`@${editing.x_handle}`} readOnly />
        <Select label="生态" value={editing.ecosystem} onChange={event => setEditing({ ...editing, ecosystem: event.target.value as Ecosystem })}>{ECOSYSTEMS.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</Select>
        <Input label="角色" value={editing.role_label} maxLength={40} onChange={event => setEditing({ ...editing, role_label: event.target.value })} />
        <Select label="启用" value={editing.enabled ? 'yes' : 'no'} onChange={event => setEditing({ ...editing, enabled: event.target.value === 'yes' })}><option value="yes">启用</option><option value="no">停用</option></Select>
        <Input label="备注" value={editing.notes} maxLength={2000} onChange={event => setEditing({ ...editing, notes: event.target.value })} />
      </div>}
    </Dialog>
    <Dialog open={!!removing} destructive onOpenChange={open => { if (!open) setRemoving(null); }} title="移除种子" description="只从生态情报种子列表删除，不会停止猎手监控或项目追踪。" pending={pending} footer={<>
      <Button data-dialog-cancel onClick={() => setRemoving(null)}>取消</Button>
      <Button variant="danger" pending={pending} onClick={() => void remove()}>确认移除</Button>
    </>}>
      <p>移除 @{removing?.x_handle}。已收录的推文会保留账号名。</p>
    </Dialog>
  </>;
}
