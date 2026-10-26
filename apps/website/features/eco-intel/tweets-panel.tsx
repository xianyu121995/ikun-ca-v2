'use client';

import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { Badge, Button, Dialog, EmptyState, Icon, Input, PageHeader, Panel, SearchInput, Select, Skeleton, ToastViewport, Toolbar, type ToastMessage } from '@ikun/ui';
import { TWEET_TOPICS, labelOf, type FollowRecord, type SeedRecord, type TweetRecord, type TweetTopic } from '../../lib/eco-intel/types';
import { classifyFollow, suggestFollow } from '../../lib/eco-intel/rules';
import { displayTime, relativeTime } from '../tracking/final/model';
import s from '../tracking/final/tracking-page.module.css';
import { readItems, writeJson } from './client';
import { SeedsPanel } from './seeds-panel';
import { ProjectDrawer, draftDirty, draftFromFollow, type EcoDraft } from './project-drawer';

const PAGE_SIZE = 20;

function followOf(row: TweetRecord, follows: FollowRecord[]): FollowRecord | undefined {
  return follows.find(item => item.x_handle.toLowerCase() === row.x_handle.toLowerCase());
}

function tweetTrackable(row: TweetRecord, follows: FollowRecord[]): boolean {
  const existing = followOf(row, follows);
  if (existing) return existing.track_eligible;
  return classifyFollow({ accountType: 'unclassified', chain: '', bio: row.text, recentSummary: '' }).classification !== 'noise';
}

function monitorLabel(row: TweetRecord, follows: FollowRecord[]): string {
  const state = followOf(row, follows)?.track_state;
  if (state === 'submitted') return '已加入监控';
  if (state === 'queued') return '重试加入监控';
  return '加入猎手项目监控';
}

export function TweetsPanel({ csrf, canWrite, username, switcher }: { csrf: string; canWrite: boolean; username: string; switcher?: ReactNode }) {
  const [query, setQuery] = useState('');
  const [topic, setTopic] = useState<'all' | TweetTopic>('all');
  const [hours, setHours] = useState<'all' | '24' | '168'>('all');
  const [important, setImportant] = useState(false);
  const [page, setPage] = useState(1);
  const [rows, setRows] = useState<TweetRecord[]>([]);
  const [follows, setFollows] = useState<FollowRecord[]>([]);
  const [seeds, setSeeds] = useState<SeedRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [messages, setMessages] = useState<ToastMessage[]>([]);
  const [pending, setPending] = useState(false);
  const [handle, setHandle] = useState('');
  const [text, setText] = useState('');
  const [url, setUrl] = useState('');
  const [adding, setAdding] = useState(false);
  const [manager, setManager] = useState(false);
  const [editing, setEditing] = useState<EcoDraft | null>(null);
  const [source, setSource] = useState<FollowRecord | null>(null);
  const [discard, setDiscard] = useState(false);
  const [monitorTweet, setMonitorTweet] = useState<TweetRecord | null>(null);
  const [now, setNow] = useState<number | null>(null);

  const say = (title: string, tone: ToastMessage['tone'] = 'info') => setMessages([{ id: 'intel-tweets', title, tone }]);

  const load = useCallback(async (initial: boolean) => {
    if (initial) setLoading(true); else setRefreshing(true);
    setError(null);
    try {
      const [tweets, projects, noise] = await Promise.all([
        readItems<TweetRecord>('/api/v1/intel/tweets?limit=100'),
        readItems<FollowRecord>('/api/v1/intel/follows?limit=100&view=projects'),
        readItems<FollowRecord>('/api/v1/intel/follows?limit=100&view=noise'),
      ]);
      setRows(tweets.items);
      setFollows([...projects.items, ...noise.items]);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '列表不可用');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { void load(true); }, [load]);
  useEffect(() => { setNow(Date.now()); const timer = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer); }, []);
  useEffect(() => {
    if (!canWrite) return;
    void readItems<SeedRecord>('/api/v1/intel/seeds?limit=100').then(pageResult => {
      setSeeds(pageResult.items);
      setHandle(current => current || pageResult.items[0]?.x_handle || '');
    }).catch(() => setSeeds([]));
  }, [canWrite]);

  const filtered = rows.filter(row => {
    const q = query.trim().toLowerCase();
    if (q && !`${row.x_handle} ${row.text}`.toLowerCase().includes(q)) return false;
    if (topic !== 'all' && !row.topics.includes(topic)) return false;
    if (important && !row.push_to_feed) return false;
    if (hours !== 'all') {
      const at = Date.parse(row.occurred_at ?? row.received_at);
      if (!Number.isFinite(at) || !now || now - at > Number(hours) * 3600000 || at > now) return false;
    }
    return true;
  });
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, pages);
  const visible = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);
  const dirty = !!editing && (source ? draftDirty(editing, source) : false);

  function reset() {
    setQuery(''); setTopic('all'); setHours('all'); setImportant(false); setPage(1);
  }

  function requestClose() {
    if (pending) return;
    if (dirty) setDiscard(true);
    else { setEditing(null); setSource(null); }
  }

  function openTweet(row: TweetRecord) {
    const follow = follows.find(item => item.x_handle.toLowerCase() === row.x_handle.toLowerCase()) ?? null;
    if (follow) {
      setSource(follow);
      setEditing({ ...draftFromFollow(follow), tweet_id: row.tweet_id });
      return;
    }
    const ai = suggestFollow({ handle: row.x_handle, displayName: row.x_handle, bio: row.text, recentSummary: '' });
    const guessed = classifyFollow({ accountType: 'unclassified', chain: '', bio: row.text, recentSummary: '' });
    setSource(null);
    setEditing({
      follow_id: null,
      revision: 0,
      x_handle: row.x_handle,
      saved_name: ai.name || row.x_handle,
      display_name: ai.name || row.x_handle,
      bio: row.text,
      notes: ai.notes,
      account_type: ai.account_type,
      chain: ai.chain,
      occurred_at: row.occurred_at,
      created_at: row.received_at,
      seed_handle: row.x_handle,
      classification: guessed.classification,
      track_eligible: guessed.track_eligible,
      track_state: 'none',
      show_ai: true,
      tweet_id: row.tweet_id,
    });
  }

  async function saveEdit() {
    if (!editing?.follow_id) {
      say('这条推文没有对应的关注档案。预填只留在抽屉里，不会写入列表。', 'warning');
      return;
    }
    setPending(true);
    try {
      await writeJson(`/api/v1/intel/follows/${editing.follow_id}`, 'PATCH', csrf, {
        display_name: editing.display_name,
        notes: editing.notes,
        account_type: editing.account_type,
        chain: editing.chain,
      }, editing.revision);
      setEditing(null);
      setSource(null);
      say('项目资料已保存。分类已按本地规则重算。');
      await load(false);
    } catch (cause) {
      say(cause instanceof Error ? cause.message : '保存未确认', 'warning');
    } finally { setPending(false); }
  }

  async function monitor(row: TweetRecord) {
    setPending(true);
    try {
      const result = await writeJson<{ message: string }>(`/api/v1/intel/tweets/${row.tweet_id}/track`, 'POST', csrf, { confirmed: true });
      say(result.message);
      setMonitorTweet(null);
      setEditing(null);
      setSource(null);
      await load(false);
    } catch (cause) {
      say(cause instanceof Error ? cause.message : '加入猎手项目监控未确认', 'warning');
    } finally { setPending(false); }
  }

  async function addTweet() {
    setPending(true);
    try {
      await writeJson('/api/v1/intel/tweets', 'POST', csrf, { x_handle: handle, text, url });
      setText(''); setUrl(''); setAdding(false);
      say('推文已按关键词规则归档。6551 WSS 仍未接入。');
      await load(false);
    } catch (cause) {
      say(cause instanceof Error ? cause.message : '保存未确认', 'warning');
    } finally { setPending(false); }
  }

  const pushed = rows.filter(row => row.push_to_feed).length;
  return <div style={{ position: 'relative', display: 'flex', flex: '1 1 auto', minHeight: 0, minWidth: 0 }}>
    <section className={s.page} aria-label="种子推文" style={editing ? { marginRight: 410 } : undefined}>
      <div className={s.topbar}><span>控制台　/　<strong>生态情报 · 种子推文</strong></span><div><span className={s.liveDot} />本地规则 · 不连接 6551<time>{now ? new Date(now).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }) : '—'}</time><span className={s.admin} aria-label="当前账号">{username.slice(0, 1).toUpperCase()}</span></div></div>
      <div className={s.content}>
        <PageHeader title="种子推文" description="种子账号的推文。提到黑客松、上线、新协议、发射或融资的文本标成可推送。WSS 仍未接入。" actions={<>
          <Badge tone="warning">本地夹具 · 不连接 6551</Badge>
          {switcher}
          {canWrite && <Button onClick={() => setAdding(true)}>＋ 补录推文</Button>}
          <Button disabled={loading} icon={<Icon name="refresh" />} onClick={() => { reset(); void load(false); }}>刷新</Button>
        </>} />
        <div className={s.stats} aria-label="推文统计">
          <Panel className={s.stat}><span>匹配推文</span><strong className={s.today}>{loading ? '—' : filtered.length}</strong></Panel>
          <Panel className={s.stat}><span>可推送</span><strong>{loading ? '—' : pushed}</strong></Panel>
          <Panel className={s.stat}><span>仅存档</span><strong>{loading ? '—' : rows.length - pushed}</strong></Panel>
          <Panel className={s.stat}><span>本页</span><strong>{loading ? '—' : visible.length}</strong></Panel>
          <Button className={s.manageStat} aria-label={`种子账号 ${seeds.length || '未加载'}`} aria-haspopup="dialog" onClick={() => setManager(true)}><span>种子账号</span><strong>{seeds.length || '—'}</strong><Icon name="chevron" /></Button>
        </div>
        <Toolbar className={s.filters} aria-label="推文搜索与筛选">
          <div className={s.search}><SearchInput label="搜索推文" value={query} onValueChange={value => { setQuery(value); setPage(1); }} placeholder="搜索备注、项目、X 账号、推文内容…" /></div>
          <div className={s.segment} role="group" aria-label="主题筛选">
            <Button size="sm" variant={topic === 'all' ? 'primary' : 'ghost'} aria-pressed={topic === 'all'} onClick={() => { setTopic('all'); setPage(1); }}>全部</Button>
            {TWEET_TOPICS.map(item => <Button key={item.id} size="sm" variant={topic === item.id ? 'primary' : 'ghost'} aria-pressed={topic === item.id} onClick={() => { setTopic(item.id); setPage(1); }}>{item.label}</Button>)}
          </div>
          <Select label="时间范围" className={s.timeSelect} value={hours} onChange={event => { setHours(event.target.value as typeof hours); setPage(1); }}>
            <option value="all">全部时间</option>
            <option value="24">最近 24 小时</option>
            <option value="168">最近 7 天</option>
          </Select>
          <label className={s.check}><input type="checkbox" checked={important} onChange={event => { setImportant(event.target.checked); setPage(1); }} />只看重要推文</label>
          <Button variant="ghost" onClick={reset}>重置筛选</Button>
        </Toolbar>
        {error && <Panel><EmptyState title="推文列表不可用" description={error} action={<Button onClick={() => void load(false)} pending={refreshing}>重试</Button>} /></Panel>}
        <section className={s.feedSection} aria-labelledby="intel-feed-title">
          <div className={s.feedHeading}><h2 id="intel-feed-title">最新推文动态 <small>· 每页 {PAGE_SIZE} 条</small></h2><span>匹配 {filtered.length} 条推文 · 按收录时间排列</span></div>
          <div className={s.feed}>
            {loading ? <Panel><Skeleton label="正在加载种子推文" lines={6} /></Panel> : visible.map(row => <article key={row.tweet_id} className={s.tweetCompact} aria-label={`@${row.x_handle} 的种子推文`}>
              <div className={s.compactHead}>
                <Badge tone={row.push_to_feed ? 'success' : 'neutral'}>{row.push_to_feed ? '推送' : '存档'}</Badge>
                <strong className={s.compactNote} title={row.topics.map(item => labelOf(TWEET_TOPICS, item)).join('、') || row.x_handle}>{row.topics.length ? row.topics.map(item => labelOf(TWEET_TOPICS, item)).join('、') : '未命中主题'}</strong>
                <span className={s.compactWho}>@{row.x_handle}</span>
                <span className={s.freshDot} data-old={!now || !Number.isFinite(Date.parse(row.occurred_at ?? row.received_at)) || now - Date.parse(row.occurred_at ?? row.received_at) >= 86400000 ? 'true' : 'false'} />
                <time className={s.compactTime} dateTime={row.occurred_at ?? row.received_at}>{relativeTime(row.occurred_at ?? row.received_at, now ?? Date.now())} · {displayTime(row.occurred_at ?? row.received_at)}</time>
                <span className={s.compactActions}>
                  {canWrite && <Button variant="ghost" size="sm" disabled={pending || followOf(row, follows)?.track_state === 'submitted' || !tweetTrackable(row, follows)} title={tweetTrackable(row, follows) ? '确认后提交与猎手相同的 tracking.create' : '代币、KOL、媒体、交易所和个人不会进入猎手项目监控'} onClick={() => setMonitorTweet(row)}>{monitorLabel(row, follows)}</Button>}
                  <Button variant="ghost" size="sm" onClick={() => openTweet(row)}>编辑</Button>
                  {row.url.startsWith('https://') && <Button variant="ghost" size="sm" className={s.openPost} aria-label={`查看 @${row.x_handle} 原文`} title="打开链接" onClick={() => window.open(row.url, '_blank', 'noopener,noreferrer')}><Icon name="arrow" /></Button>}
                </span>
              </div>
              <p className={s.compactBody} title={row.text}>{row.text}</p>
            </article>)}
            {!loading && !error && !visible.length && <div className={s.empty}><EmptyState title="暂无符合条件的推文" description="试着调整关键词、主题或时间。WSS 未接入时只有夹具和手工补录。" action={<Button onClick={reset}>清空筛选</Button>} /></div>}
          </div>
          <Panel><span>本地规则排序 · 第 {currentPage} 页 · 匹配 {filtered.length} 条 · 本页 {visible.length} 条</span><Button disabled={currentPage <= 1} onClick={() => setPage(currentPage - 1)}>上一页</Button><Button disabled={currentPage >= pages} onClick={() => setPage(currentPage + 1)}>下一页</Button></Panel>
        </section>
        <footer className={s.footer}><span>本地 intel.db · 不代表 6551 已接通</span><span>加入猎手项目监控走现有 tracking.create。编辑仍打开右侧项目资料。</span></footer>
      </div>
    </section>
    {editing && <div className="hunter-v3" style={{ position: 'absolute', top: 0, right: 0, bottom: 0, width: 410, height: '100%', minHeight: 0, background: 'transparent', zIndex: 4 }}>
      <div className="main" style={{ height: '100%', minHeight: 0 }}>
        <ProjectDrawer draft={editing} pending={pending} canWrite={canWrite} dirty={dirty} onChange={patch => setEditing(current => current ? { ...current, ...patch } : current)} onClose={requestClose} onSave={() => void saveEdit()} onTrack={() => { const row = editing.tweet_id ? rows.find(item => item.tweet_id === editing.tweet_id) : undefined; if (row) setMonitorTweet(row); }} />
      </div>
    </div>}
    <div className={s.managerScope}>
      <Dialog open={manager} title="种子账号" description="生态情报的种子名单。不会修改猎手监控或主页。" onOpenChange={open => { if (!open && !pending) setManager(false); }} closeOnBackdrop>
        <SeedsPanel csrf={csrf} canWrite={canWrite} />
      </Dialog>
    </div>
    <Dialog open={!!monitorTweet} title="加入猎手项目监控" pending={pending} onOpenChange={open => { if (!open && !pending) setMonitorTweet(null); }} footer={<>
      <Button data-dialog-cancel onClick={() => setMonitorTweet(null)}>取消</Button>
      <Button variant="primary" pending={pending} disabled={!monitorTweet} onClick={() => { if (monitorTweet) void monitor(monitorTweet); }}>确认加入</Button>
    </>}>
      <p className="modal-desc">确认把 @{monitorTweet?.x_handle} 提交到现有猎手项目监控吗？命令与「加入猎手项目监控」相同，走 tracking.create。不会另开监控，也不会调用 6551。代币不会进入。</p>
    </Dialog>
    <Dialog open={discard} destructive title="放弃未保存的修改？" onOpenChange={open => { if (!open) setDiscard(false); }} footer={<>
      <Button data-dialog-cancel onClick={() => setDiscard(false)}>继续编辑</Button>
      <Button variant="danger" onClick={() => { setDiscard(false); setEditing(null); setSource(null); }}>放弃修改</Button>
    </>}>
      <p>当前资料尚未保存。</p>
    </Dialog>
    <Dialog open={adding} onOpenChange={open => { if (!open && !pending) setAdding(false); }} title="补录一条推文" pending={pending} footer={<>
      <Button data-dialog-cancel onClick={() => setAdding(false)}>取消</Button>
      <Button variant="primary" pending={pending} disabled={!handle} onClick={() => void addTweet()}>保存推文</Button>
    </>}>
      <p className="modal-desc">只写入本地 intel.db。不会向 X 或 6551 拉取。</p>
      <Select label="种子账号" value={handle} onChange={event => setHandle(event.target.value)}>{seeds.map(seed => <option key={seed.seed_id} value={seed.x_handle}>@{seed.x_handle}</option>)}</Select>
      <Input label="正文" value={text} maxLength={2000} onChange={event => setText(event.target.value)} />
      <Input label="https 链接" value={url} placeholder="可留空" onChange={event => setUrl(event.target.value)} />
    </Dialog>
    <ToastViewport messages={messages} onDismiss={() => setMessages([])} />
  </div>;
}
