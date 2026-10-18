'use client';
/** Owner decision 2026-10-19: upcoming milestones as a horizontal timeline (S/A/B colors, live "now" marker). */
import { useEffect, useMemo, useState, type CSSProperties } from 'react';
import type { ProjectView } from '../../features/homepage/types';
import type { ProjectMilestone } from '../../features/homepage/reference-types';

type Row = { project: ProjectView; event: ProjectMilestone };
const HOUR = 3600_000, DAY = 24 * HOUR, MAX_STACK = 4;
const COLORS: Record<string, string> = { S: '#f5c451', A: '#f59e5b', B: '#60a5fa' };
// Beijing wall-clock → epoch ms.
const at = (date: string, hour: string | null) => Date.parse(`${date}T${hour ?? '12'}:00:00+08:00`);
const pad = (n: number) => String(n).padStart(2, '0');
const bj = (ms: number) => new Date(ms + 8 * HOUR);

export function EventTimeline({ rows, days, onOpen }: { rows: readonly Row[]; days: number | null; onOpen: (key: string) => void }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 30_000); return () => clearInterval(t); }, []);
  const items = useMemo(() => rows.filter(r => r.event.date && ['S', 'A', 'B'].includes(r.project.record.rating ?? ''))
    .map(r => ({ ...r, t: at(r.event.date!, r.event.hour) })).filter(r => Number.isFinite(r.t) && r.t >= now - HOUR)
    .sort((a, b) => a.t - b.t), [rows, now]);
  const start = now;
  const last = items.length ? items[items.length - 1].t : now;
  const end = days ? now + days * DAY : Math.max(now + 7 * DAY, last + 12 * HOUR);
  const span = end - start;
  const pos = (t: number) => Math.min(100, Math.max(0, ((t - start) / span) * 100));
  const groups = new Map<string, typeof items>();
  for (const it of items) { if (it.t > end) continue; const key = `${it.event.date}-${it.event.hour ?? 'x'}`; groups.set(key, [...(groups.get(key) ?? []), it]); }
  const trackHeight = Math.max(70, Math.max(0, ...[...groups.values()].map(list => Math.min(list.length, MAX_STACK))) * 36 + 22);
  const ticks: number[] = [];
  const firstDay = Date.parse(`${bj(now).toISOString().slice(0, 10)}T00:00:00+08:00`) + DAY;
  const step = span > 40 * DAY ? 7 * DAY : span > 14 * DAY ? 2 * DAY : DAY;
  for (let t = firstDay; t < end; t += step) ticks.push(t);
  const nowLabel = `${pad(bj(now).getUTCHours())}:${pad(bj(now).getUTCMinutes())}`;
  return <div className="hpv2-timeline" style={{"--hpv2-track-height": `${trackHeight}px`} as CSSProperties} role="list" aria-label="近期重要时间线">
    <div className="hpv2-tl-track">
      {ticks.map(t => <span key={t} className="hpv2-tl-tick" style={{ left: `${pos(t)}%` }}><i />{`${bj(t).getUTCMonth() + 1}/${bj(t).getUTCDate()}`}</span>)}
      <span className="hpv2-tl-now" style={{ left: '0%' }} title="现在（北京时间）"><b>现在 {nowLabel}</b></span>
      {[...groups.entries()].map(([key, list]) => <div key={key} className="hpv2-tl-stack" data-right={pos(list[0].t) > 72 || undefined} style={{ left: `${pos(list[0].t)}%` }}>
        {list.slice(0, list.length > MAX_STACK ? MAX_STACK - 1 : MAX_STACK).map(it => {
          const e = it.event, d = bj(it.t);
          const label = `${it.project.record.name} · ${e.title || '重要事件'} · ${d.getUTCMonth() + 1}/${d.getUTCDate()} ${e.hour ? e.hour + '时' : '（未定小时）'} · ${e.status === 'confirmed' ? '已确认' : '预计'}`;
          return <button key={it.project.key} type="button" role="listitem" className="hpv2-tl-dot" data-hourless={!e.hour || undefined}
            style={{ '--tl-color': COLORS[it.project.record.rating!] } as CSSProperties} title={label} aria-label={label} onClick={() => onOpen(it.project.key)}>
            <i>{it.project.record.name.slice(0, 1)}</i><span>{it.project.record.name}</span>{e.hour ? <small>{e.hour}时</small> : null}</button>;
        })}
        {list.length > MAX_STACK && <span className="hpv2-tl-more" title={list.slice(MAX_STACK - 1).map(it => it.project.record.name).join('、')}>+{list.length - MAX_STACK + 1}</span>}
      </div>)}
    </div>
    {!groups.size && <p className="hpv2-tl-empty">{days ? `未来 ${days} 天` : '目前'}没有已定日期的重要事件</p>}
    <div className="hpv2-tl-legend"><span><i style={{ background: COLORS.S }} />S</span><span><i style={{ background: COLORS.A }} />A</span><span><i style={{ background: COLORS.B }} />B</span><small>虚线圈 = 只定了日期、未定小时</small></div>
  </div>;
}
