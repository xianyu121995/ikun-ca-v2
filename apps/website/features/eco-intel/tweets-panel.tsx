'use client';

import { useCallback, useEffect, useState } from 'react';
import { Alert, Badge, Button, DataTable, EmptyState, ErrorState, Input, Panel, SearchInput, Select, type TableColumn } from '@ikun/ui';
import { TWEET_TOPICS, labelOf, type SeedRecord, type TweetRecord } from '../../lib/eco-intel/types';
import { readItems, writeJson } from './client';
import s from './intel.module.css';
import { SeedsPanel } from './seeds-panel';

export function TweetsPanel({ csrf, canWrite }: { csrf: string; canWrite: boolean }) {
  const [query, setQuery] = useState('');
  const [applied, setApplied] = useState('');
  const [rows, setRows] = useState<TweetRecord[]>([]);
  const [seeds, setSeeds] = useState<SeedRecord[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [handle, setHandle] = useState('');
  const [text, setText] = useState('');
  const [url, setUrl] = useState('');

  const load = useCallback(async (initial: boolean, next?: string) => {
    if (initial && !next) setLoading(true); else setRefreshing(true);
    setError(null);
    try {
      const params = new URLSearchParams({ limit: '100' });
      if (applied) params.set('q', applied);
      if (next) params.set('cursor', next);
      const page = await readItems<TweetRecord>('/api/v1/intel/tweets?' + params);
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
      setHandle(current => current || page.items[0]?.x_handle || '');
    }).catch(() => setSeeds([]));
  }, [canWrite]);

  async function addTweet() {
    setPending(true); setNotice(null);
    try {
      await writeJson('/api/v1/intel/tweets', 'POST', csrf, { x_handle: handle, text, url });
      setText(''); setUrl(''); setNotice('推文已按关键词规则归档。6551 WSS 仍未接入。');
      await load(false);
    } catch (cause) {
      setNotice(cause instanceof Error ? cause.message : '保存未确认');
    } finally { setPending(false); }
  }

  const columns: TableColumn<TweetRecord>[] = [
    { key: 'time', header: '时间 (UTC)', width: '190px', render: row => row.occurred_at ?? row.received_at },
    { key: 'handle', header: '种子', width: '140px', render: row => <strong>@{row.x_handle}</strong> },
    { key: 'text', header: '内容', render: row => <span className={s.clamp}>{row.text}</span> },
    { key: 'topics', header: '命中', width: '180px', render: row => row.topics.length ? row.topics.map(topic => labelOf(TWEET_TOPICS, topic)).join('、') : '—' },
    { key: 'feed', header: '情报流', width: '110px', render: row => <Badge tone={row.push_to_feed ? 'success' : 'neutral'}>{row.push_to_feed ? '推送' : '仅存档'}</Badge> },
    { key: 'source', header: '来源', width: '80px', render: row => row.source === 'stub' ? '夹具' : row.source === 'manual' ? '手工' : row.source },
  ];

  return <>
    <Alert tone="warning" title="推文管道未接通">TODO(6551)：这里应接收种子和创始人账号的 WSS 推文。当前只有本地夹具和手工补录。提到黑客松、上线、新协议、发射或融资的文本会标成可推送。</Alert>
    {notice && <Alert tone="info" title="种子推文">{notice}</Alert>}
    <SearchInput label="搜索推文" value={query} onValueChange={setQuery} placeholder="搜索账号或正文" />
    {canWrite && <Panel title="补录一条推文" description="用于验收页面。不会向 X 或 6551 拉取。">
      <div className={s.form}>
        <Select label="种子账号" value={handle} onChange={event => setHandle(event.target.value)}>{seeds.map(seed => <option key={seed.seed_id} value={seed.x_handle}>@{seed.x_handle}</option>)}</Select>
        <Input label="正文" value={text} maxLength={2000} onChange={event => setText(event.target.value)} />
        <Input label="https 链接" value={url} placeholder="可留空" onChange={event => setUrl(event.target.value)} />
        <Button variant="primary" pending={pending} disabled={!handle} onClick={() => void addTweet()}>保存推文</Button>
      </div>
    </Panel>}
    <DataTable caption="种子推文" columns={columns} rows={rows} rowKey={row => row.tweet_id} loading={loading} refreshing={refreshing} minWidth={860}
      error={error ? <ErrorState title="推文列表不可用" description={error} onRetry={() => void load(false)} pending={refreshing} /> : undefined}
      empty={<EmptyState title="还没有推文" description="WSS 未接入。超级管理员可以手工补录，或等待首次建库写入夹具。" />} />
    {cursor && <div className={s.more}><Button onClick={() => void load(false, cursor)} pending={refreshing}>加载更多</Button></div>}
    <details className={s.admin}>
      <summary>种子名单（管理员）</summary>
      <SeedsPanel csrf={csrf} canWrite={canWrite} />
    </details>
  </>;
}
