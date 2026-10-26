'use client';

import { useEffect, useRef, type FormEvent } from 'react';
import { Button, Input, Select } from '@ikun/ui';
import { ACCOUNT_TYPES, TRACK_CHAINS, labelOf, type AccountType, type FollowClassification, type FollowRecord, type TrackChain, type TrackState } from '../../lib/eco-intel/types';

/** Same role as hunter `withAi`: the drawer shows the draft. Nothing is written until 保存. */
export interface EcoDraft {
  follow_id: string | null;
  revision: number;
  x_handle: string;
  saved_name: string;
  display_name: string;
  bio: string;
  notes: string;
  account_type: AccountType;
  chain: TrackChain | '';
  occurred_at: string | null;
  created_at: string;
  seed_handle: string;
  classification: FollowClassification;
  track_eligible: boolean;
  track_state: TrackState;
  show_ai: boolean;
  /** Set when the drawer was opened from a seed tweet. Track uses that tweet's tracking.create route. */
  tweet_id: string | null;
}

export function formatTime(value: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '时间未知';
  return new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(date);
}

export function draftFromFollow(row: FollowRecord): EcoDraft {
  const ai = row.ai_suggestion;
  const untouched = !row.notes.trim() || row.notes.startsWith('本地夹具');
  return {
    follow_id: row.follow_id,
    revision: row.revision,
    x_handle: row.x_handle,
    saved_name: row.display_name || row.x_handle,
    display_name: ai.name || row.display_name,
    bio: row.bio,
    notes: untouched ? ai.notes : row.notes,
    account_type: row.account_type === 'unclassified' ? ai.account_type : row.account_type,
    chain: row.chain || ai.chain,
    occurred_at: row.occurred_at,
    created_at: row.created_at,
    seed_handle: row.seed_handle,
    classification: row.classification,
    track_eligible: row.track_eligible,
    track_state: row.track_state,
    show_ai: true,
    tweet_id: null,
  };
}

export function draftDirty(draft: EcoDraft, source: FollowRecord | null): boolean {
  if (!source) return false;
  return draft.display_name !== source.display_name || draft.notes !== source.notes || draft.account_type !== source.account_type || draft.chain !== source.chain;
}

function statusLabel(draft: EcoDraft): string {
  if (draft.track_state === 'submitted') return '已提交追踪';
  if (draft.track_state === 'queued') return '已排队';
  if (draft.classification === 'noise') return '仅记录';
  if (draft.classification === 'pending') return '待定';
  return '项目';
}

export function ProjectDrawer({ draft, pending, canWrite, dirty, onChange, onClose, onSave, onTrack }: {
  draft: EcoDraft;
  pending: boolean;
  canWrite: boolean;
  dirty: boolean;
  onChange: (patch: Partial<EcoDraft>) => void;
  onClose: () => void;
  onSave: () => void;
  onTrack: () => void;
}) {
  const nameRef = useRef<HTMLInputElement>(null);
  useEffect(() => { nameRef.current?.focus(); }, [draft.follow_id, draft.x_handle]);
  const trackLabel = draft.track_state === 'submitted' ? '已加入监控' : draft.track_state === 'queued' ? '重试加入监控' : draft.tweet_id ? '＋ 加入猎手项目监控' : '＋ 项目追踪';
  const canTrack = draft.track_eligible && draft.track_state !== 'submitted' && !!(draft.follow_id || draft.tweet_id);
  return <aside className="drawer" aria-label="项目资料编辑面板">
    <header className="drawer-head">
      <Button variant="ghost" className="drawer-back" disabled={pending} onClick={onClose}>← 收起资料 / 返回全宽表格</Button>
      <div className="drawer-identity">
        <span className="avatar" aria-hidden="true">{(draft.saved_name || draft.x_handle).slice(0, 1)}</span>
        <div>
          <h2>{draft.saved_name}</h2>
          <p>@{draft.x_handle}</p>
        </div>
      </div>
      <div className="drawer-meta">
        <span>发现：{formatTime(draft.occurred_at ?? draft.created_at)}</span>
        <span>·</span>
        <span>{draft.seed_handle ? `种子 @${draft.seed_handle}` : '种子未记录'}</span>
        <span>·</span>
        <span>{statusLabel(draft)}</span>
      </div>
      <div className="drawer-section-title">项目资料{dirty && <span className="dirty-dot"> · 未保存</span>}</div>
    </header>
    <div className="drawer-scroll">
      {draft.show_ai && <div className="drawer-note ai-note">✦ AI 已按简介预填名称、类型、链和备注，请核对修改后点「保存项目资料」。评分不会自动填写。代币不会进入项目追踪。</div>}
      <div className="drawer-note">{draft.follow_id ? '保存只更新生态情报里的这条关注。点「项目追踪」才会提交与猎手相同的 tracking.create。' : '这条推文按本地规则预填。没有对应的关注档案时，保存不会写入列表，也不会调用 6551。'}</div>
      <form noValidate onSubmit={(event: FormEvent) => { event.preventDefault(); onSave(); }} aria-label="项目资料表单">
        <fieldset disabled={pending || !canWrite}>
          <Input label="X 账号" value={`@${draft.x_handle}`} readOnly hint="自动识别 · 不可修改" />
          <Input ref={nameRef} label="项目名称" aria-label="项目名称" value={draft.display_name} required maxLength={80} onChange={event => onChange({ display_name: event.target.value })} />
          <label className="field">X 主页简介<textarea aria-label="X 主页简介" readOnly rows={2} value={draft.bio} /></label>
          <Select label="链" value={draft.chain} onChange={event => onChange({ chain: event.target.value as TrackChain | '' })}>
            <option value="">未定</option>
            {TRACK_CHAINS.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}
          </Select>
          <label className="field">项目介绍 / 研究结论<textarea aria-label="项目介绍 / 研究结论" rows={4} maxLength={2000} value={draft.notes} onChange={event => onChange({ notes: event.target.value })} /></label>
          <Select label="项目类型" value={draft.account_type} onChange={event => onChange({ account_type: event.target.value as AccountType })}>
            {ACCOUNT_TYPES.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}
          </Select>
        </fieldset>
        <div className="drawer-action">
          <Button type="submit" variant="primary" pending={pending} disabled={!canWrite}>▣ 保存项目资料</Button>
          <Button className="soft" disabled={pending || !canWrite || !canTrack} onClick={onTrack}>{trackLabel}</Button>
        </div>
        <p className="help">{draft.track_eligible ? '项目追踪需要二次确认。代币、KOL、媒体、交易所和个人不会进入追踪。' : `当前判定：${labelOf(ACCOUNT_TYPES, draft.account_type)}。这类账号不能项目追踪。`}</p>
      </form>
    </div>
  </aside>;
}
