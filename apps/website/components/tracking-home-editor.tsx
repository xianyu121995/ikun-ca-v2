'use client';
/** Owner decision 2026-10-19: edit a project's homepage info (important time, progress, notes) straight from a tweet. */
import { useState } from 'react';
import { Alert, Button, Dialog, Input } from '@ikun/ui';
import { referenceStageLabels } from '../features/homepage/reference-model';

type Milestone = { date: string | null; hour: string | null; title: string; status: 'confirmed' | 'estimated' | 'unconfirmed' };
type Loaded = { project: { project_id: string; name: string; revision: number; notes: string; progress_stage: keyof typeof referenceStageLabels; home_membership?: string }; milestone: Milestone; completion: unknown };
export type EditTarget = { project_id: string; name: string; tweet: string; quote?: string | null; received_at?: string };

const hours = Array.from({ length: 24 }, (_, h) => String(h).padStart(2, '0'));

export function TrackingHomeEditor({ target, csrf, onClose, onSaved }: { target: EditTarget | null; csrf: string; onClose: () => void; onSaved: (message: string) => void }) {
  const [loaded, setLoaded] = useState<Loaded | null>(null), [error, setError] = useState(''), [busy, setBusy] = useState(false), [aiBusy, setAiBusy] = useState(false);
  const [date, setDate] = useState(''), [hour, setHour] = useState(''), [title, setTitle] = useState(''), [status, setStatus] = useState<'confirmed' | 'estimated'>('estimated');
  const [stage, setStage] = useState<keyof typeof referenceStageLabels>('todo'), [notes, setNotes] = useState(''), [openedFor, setOpenedFor] = useState<string | null>(null);
  const api = async (path: string, init: RequestInit = {}) => {
    const response = await fetch(path, { cache: 'no-store', credentials: 'same-origin', ...init, headers: { 'content-type': 'application/json', 'x-csrf-token': csrf, ...(init.headers || {}) } });
    const value = await response.json(); if (!response.ok) throw new Error(value.error?.message || '操作未完成'); return value.data;
  };
  if (target && openedFor !== target.project_id) {
    setOpenedFor(target.project_id); setLoaded(null); setError('');
    void api(`/api/v1/projects/${target.project_id}?view=home-v1`).then((data: Loaded) => {
      setLoaded(data); const m = data.milestone;
      setDate(m.date ?? ''); setHour(m.hour ?? ''); setTitle(m.title ?? ''); setStatus(m.status === 'confirmed' ? 'confirmed' : 'estimated');
      setStage(data.project.progress_stage); setNotes(data.project.notes ?? '');
    }).catch(e => setError((e as Error).message));
  }
  if (!target && openedFor) { setOpenedFor(null); }
  async function aiFill() {
    if (!target) return; setAiBusy(true); setError('');
    try {
      let r = await api('/api/v1/ai/extract-time', { method: 'POST', headers: { 'idempotency-key': crypto.randomUUID() }, body: JSON.stringify({ text: target.tweet, quote: target.quote ?? null, received_at: target.received_at ?? null }) });
      const job = r.job;
      const deadline = Date.now() + 250_000;
      while (r.pending) {
        if (Date.now() > deadline) throw new Error('AI 识别超时，请稍后再试');
        await new Promise(resolve => setTimeout(resolve, 2000));
        r = await api('/api/v1/ai/extract-time?job=' + encodeURIComponent(job));
      }
      if (!r.date) setError('AI 没有在这条推文里找到明确的时间'); else { setDate(r.date); setHour(r.hour ?? ''); if (r.title) setTitle(r.title); setStatus(r.status === 'confirmed' ? 'confirmed' : 'estimated'); }
    } catch (e) { setError((e as Error).message); } finally { setAiBusy(false); }
  }
  async function save() {
    if (!target || !loaded) return;
    if (date && !title.trim()) { setError('填了日期就要写一句事件说明'); return; }
    setBusy(true); setError('');
    try {
      const milestone: Milestone = date ? { date, hour: hour || null, title: title.trim(), status } : { date: null, hour: null, title: title.trim(), status: 'unconfirmed' };
      await api(`/api/v1/projects/${target.project_id}?view=home-v1`, { method: 'PATCH', headers: { 'idempotency-key': crypto.randomUUID(), 'if-match': `"rev-${loaded.project.revision}"` },
        body: JSON.stringify({ fields: { progress_stage: stage, notes }, milestone }) });
      // Owner: saving here also puts the project on the homepage.
      const fresh: Loaded = await api(`/api/v1/projects/${target.project_id}?view=home-v1`);
      let added = false;
      if (fresh.project.home_membership !== 'active' && !fresh.completion) {
        await api(`/api/v1/projects/${target.project_id}/home-membership`, { method: 'POST', headers: { 'idempotency-key': crypto.randomUUID(), 'if-match': `"rev-${fresh.project.revision}"` }, body: JSON.stringify({ action: 'add' }) });
        added = true;
      }
      onSaved(`「${target.name}」主页信息已保存${added ? '，并已加入主页' : ''}`); onClose();
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  return <Dialog open={!!target} title={`编辑主页信息 · ${target?.name ?? ''}`} onOpenChange={open => { if (!open && !busy) onClose(); }} pending={busy}>
    {error && <Alert tone='danger' title={error} />}
    {target && <p className='tracking-edit-tweet'>{target.tweet}</p>}
    {!loaded && !error ? <p>正在读取主页资料…</p> : <>
      <div className='tracking-edit-row'><Input label='重要时间 · 日期（北京时间）' type='date' value={date} onChange={e => setDate(e.target.value)} />
        <label className='tracking-edit-field'>小时<select value={hour} onChange={e => setHour(e.target.value)}><option value=''>未定</option>{hours.map(h => <option key={h} value={h}>{h}:00</option>)}</select></label>
        <label className='tracking-edit-field'>状态<select value={status} onChange={e => setStatus(e.target.value as 'confirmed' | 'estimated')}><option value='estimated'>预计</option><option value='confirmed'>已确认</option></select></label>
        <Button size='sm' disabled={aiBusy || busy} pending={aiBusy} onClick={() => void aiFill()} title='让 AI 从这条推文里识别时间并换算成北京时间（约 20 秒）'>AI 识别时间</Button></div>
      <Input label='事件说明' value={title} maxLength={240} placeholder='例如：TGE / 白名单开放 / 主网上线' onChange={e => setTitle(e.target.value)} />
      <label className='tracking-edit-field'>进度<select value={stage} onChange={e => setStage(e.target.value as keyof typeof referenceStageLabels)}>{Object.entries(referenceStageLabels).filter(([k]) => k !== 'completed').map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
      <label className='tracking-edit-field'>备注<textarea rows={3} maxLength={4000} value={notes} onChange={e => setNotes(e.target.value)} /></label>
      <Button variant='primary' pending={busy} disabled={!loaded} onClick={() => void save()}>保存并同步到主页</Button></>}
  </Dialog>;
}
