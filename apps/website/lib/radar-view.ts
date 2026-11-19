/** Pure radar view model. Payloads are untrusted. No network, no speech, no storage writes. */

export const RADAR_READ_API = [/^\/api\/v1\/radar\/(?:snapshot|events)$/] as const;
export const RADAR_READ_PAGES = [/^\/radar$/, /^\/prototypes\/radar$/] as const;

const HOSTS = ['bscscan.com', 'testnet.bscscan.com', 'github.com', 'docs.flap.sh', 'four-meme.gitbook.io', 'raw.githubusercontent.com'];
const BLOCKED_PORTS = new Set(['80', '443', '8443', '4000', '8545', '3311', '3322']);
const SECRET = /bearer\s+[a-z0-9._-]{8,}|bot\d{5,}:[A-Za-z0-9_-]{10,}|sk-[A-Za-z0-9]{8,}|wss:\/\/\S+|https?:\/\/[^\s/]+:[^\s@]+@\S+/gi;

export type RadarLevel = 'info' | 'warn' | 'crit';
export type RadarKind = 'new' | 'changed' | 'gone' | 'baseline';
export type RadarLink = 'live' | 'stale' | 'disconnected' | 'unconfigured' | 'disabled' | 'partial' | 'configured' | 'unavailable';

export interface RadarEventView {
  id: number;
  ts: number;
  time: string;
  source: string;
  key: string;
  kind: RadarKind;
  level: RadarLevel;
  title: string;
  detail: string;
  href: string;
  project: string;
  motion: string;
}

export interface RadarCard {
  id: string;
  project: string;
  kind: string;
  state: RadarLink;
  label: string;
  summary: string;
  limit: string;
}

export interface RadarPageModel {
  sample: boolean;
  bridge: 'ok' | 'not_configured' | 'disconnected' | 'unavailable';
  bridgeLabel: string;
  generatedAt: string;
  cards: RadarCard[];
  events: RadarEventView[];
  latestEventId: number;
  footnote: string;
}

const FOUR_EVENT_LIMIT = 'four.meme 事件枚举未接入：没有官方事件签名，log 订阅也不含 TokenManager。不能把它看成完整监控。';
const FOOTNOTE = '链上只走 WSS 的 newHeads/logs。没有 WSS 就显示未配置，不用 HTTP 轮询代替。文档和仓库是限速检查，第一次只建基线。本页不交易、不签名。';

export function radarBridgeConfig(env: object = process.env): { origin: string; token: string } | null {
  const read = (key: string) => {
    if (!(key in env)) return undefined;
    const value = (env as Record<string, unknown>)[key];
    return typeof value === 'string' ? value : undefined;
  };
  const token = read('IKUN_RADAR_TOKEN');
  if (!token || token.length < 32 || /\s/.test(token)) return null;
  const raw = read('IKUN_RADAR_ORIGIN') ?? 'http://127.0.0.1:3921';
  let url: URL;
  try { url = new URL(raw); } catch { return null; }
  const host = url.hostname.toLowerCase();
  if (url.protocol !== 'http:' || !['127.0.0.1', 'localhost', '[::1]'].includes(host)) return null;
  if (url.username || url.password || url.pathname !== '/' || url.search || url.hash) return null;
  if (BLOCKED_PORTS.has(url.port)) return null;
  return { origin: url.origin, token };
}

type Assert<T extends true> = T;
type _processEnvFits = Assert<NodeJS.ProcessEnv extends Parameters<typeof radarBridgeConfig>[0] ? true : never>;
type _emptyEnvFits = Assert<Record<string, never> extends Parameters<typeof radarBridgeConfig>[0] ? true : never>;

export function displayText(value: unknown, max = 240): string {
  if (typeof value !== 'string') return '';
  return value.replace(SECRET, '[已隐藏]').replace(/[\u0000-\u001f\u007f]/g, '').replace(/\s+/g, ' ').trim().slice(0, max);
}

export function safeHref(value: unknown): string {
  if (typeof value !== 'string' || value.length > 500) return '';
  let url: URL;
  try { url = new URL(value); } catch { return ''; }
  if (url.protocol !== 'https:' || url.username || url.password) return '';
  const host = url.hostname.toLowerCase();
  if (!HOSTS.some(item => host === item || host.endsWith('.' + item))) return '';
  return url.toString();
}

export function formatBeijing(unixSeconds: number): string {
  if (!Number.isFinite(unixSeconds)) return '';
  const parts = new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
  }).formatToParts(new Date(unixSeconds * 1000));
  const pick = (type: string) => parts.find(part => part.type === type)?.value ?? '';
  return `${pick('year')}-${pick('month')}-${pick('day')} ${pick('hour')}:${pick('minute')}:${pick('second')} 北京时间`;
}

export function projectOf(source: string, title = ''): string {
  const blob = `${source} ${title}`.toLowerCase();
  if (blob.includes('fourmeme') || blob.includes('four.meme') || blob.includes('four-meme')) return 'four.meme';
  if (blob.includes('flap') || blob.startsWith('onchain:')) return 'FLAP';
  return '模式雷达';
}

export function motionOf(kind: string): string {
  if (kind === 'gone') return '有删除';
  if (kind === 'changed') return '有变更';
  if (kind === 'new') return '有新变化';
  return '';
}

export function voiceLine(event: { source: string; kind: string; title: string }): string | null {
  if (event.kind === 'baseline' || /基线|心跳/.test(event.title)) return null;
  const motion = motionOf(event.kind);
  if (!motion) return null;
  return `${projectOf(event.source, event.title)}，${motion}`;
}

export function seenKey(userId: string): string | null {
  if (!/^usr_[0-9a-f-]{36}$/i.test(userId)) return null;
  return `ikun.radar.seen.v1.${userId}`;
}

export function sealWatermark(stored: string | null, latestId: number): number {
  if (!Number.isSafeInteger(latestId) || latestId < 0) return 0;
  if (stored === null) return latestId;
  if (!/^\d{1,15}$/.test(stored)) return latestId;
  const value = Number(stored);
  return value > latestId ? latestId : value;
}

export function shouldNotify(event: { id: number; kind: string; title: string }, watermark: number, seen: ReadonlySet<number>): boolean {
  if (!Number.isSafeInteger(event.id) || event.id <= watermark || seen.has(event.id)) return false;
  if (event.kind === 'baseline' || /基线|心跳/.test(event.title)) return false;
  return event.kind === 'new' || event.kind === 'changed' || event.kind === 'gone';
}

export function maybeSpeak(input: {
  event: { id: number; source: string; kind: string; title: string };
  armed: boolean;
  enabled: boolean;
  quiet: boolean;
  available: boolean;
  spoken: Set<number>;
  speak: (text: string) => void;
}): boolean {
  if (!input.armed || !input.enabled || input.quiet || !input.available) return false;
  if (input.spoken.has(input.event.id) || !shouldNotify(input.event, -1, input.spoken)) return false;
  const line = voiceLine(input.event);
  if (!line) return false;
  input.spoken.add(input.event.id);
  input.speak(line);
  return true;
}

const LABELS: Record<string, string> = {
  live: '订阅中', stale: '数据滞后', disconnected: '已断连', unconfigured: '未配置',
  disabled: '已禁用', partial: '部分覆盖', configured: '已配置', unavailable: '服务不可达',
};

function asLink(value: unknown, fallback: RadarLink): RadarLink {
  return typeof value === 'string' && value in LABELS ? value as RadarLink : fallback;
}

function asKind(value: unknown): RadarKind | null {
  return value === 'new' || value === 'changed' || value === 'gone' || value === 'baseline' ? value : null;
}

function asLevel(value: unknown): RadarLevel | null {
  return value === 'info' || value === 'warn' || value === 'crit' ? value : null;
}

export function presentRadar(input: unknown, nowSec: number): RadarPageModel | null {
  if (!input || typeof input !== 'object' || Array.isArray(input)) return null;
  const wire = input as Record<string, unknown>;
  const bridge = wire.bridge === 'ok' || wire.bridge === 'not_configured' || wire.bridge === 'disconnected' ? wire.bridge : 'unavailable';
  const generated = typeof wire.generated_at === 'number' ? wire.generated_at : nowSec;
  const cards: RadarCard[] = [];
  if (Array.isArray(wire.coverage)) {
    for (const item of wire.coverage) {
      if (!item || typeof item !== 'object') continue;
      const row = item as Record<string, unknown>;
      if (typeof row.id !== 'string' || typeof row.project !== 'string') continue;
      let state = asLink(row.state, 'unavailable');
      let limit = displayText(row.limit, 400);
      if (row.id === 'four-events') { state = 'unconfigured'; limit = FOUR_EVENT_LIMIT; }
      const probes = wire.probes && typeof wire.probes === 'object' ? wire.probes as Record<string, { ok_ts?: unknown; error?: unknown }> : {};
      const chains = wire.chains && typeof wire.chains === 'object' ? wire.chains as Record<string, { link?: unknown; mode?: unknown }> : {};
      const bsc = chains.bsc;
      if (row.id === 'flap-events' || row.id === 'flap-identity' || row.id === 'four-identity') {
        const link = typeof bsc?.link === 'string' ? bsc.link : typeof bsc?.mode === 'string' ? bsc.mode : 'unconfigured';
        if (link === 'unconfigured' || link === 'disabled' || link === 'disconnected' || link === 'stale') state = asLink(link, state);
        else if (link === 'live' && row.id === 'four-identity') state = 'partial';
        else if (link === 'live') state = 'live';
      }
      if ((row.id.endsWith('-docs') || row.id === 'four-github') && state !== 'unconfigured' && state !== 'disabled') {
        const probeName = row.id.includes('github') ? 'github' : 'docs';
        const probe = probes[probeName];
        const ok = typeof probe?.ok_ts === 'number' ? probe.ok_ts : 0;
        if (typeof probe?.error === 'string' && probe.error) state = 'disconnected';
        else if (ok > 0 && nowSec - ok > 3600) state = 'stale';
      }
      cards.push({
        id: displayText(row.id, 40), project: displayText(row.project, 40), kind: displayText(row.kind, 40),
        state, label: LABELS[state] ?? '未知', summary: displayText(row.summary, 280), limit,
      });
    }
  }
  const events: RadarEventView[] = [];
  if (Array.isArray(wire.events)) {
    for (const item of wire.events) {
      if (!item || typeof item !== 'object') continue;
      const row = item as Record<string, unknown>;
      const kind = asKind(row.kind);
      const level = asLevel(row.level);
      if (!kind || !level || typeof row.id !== 'number' || !Number.isSafeInteger(row.id)) continue;
      const title = displayText(row.title, 240);
      const source = displayText(row.source, 80);
      events.push({
        id: row.id, ts: typeof row.ts === 'number' ? row.ts : 0, time: formatBeijing(typeof row.ts === 'number' ? row.ts : 0),
        source, key: displayText(row.key, 180), kind, level, title, detail: displayText(row.detail, 400),
        href: safeHref(row.url), project: projectOf(source, title), motion: motionOf(kind),
      });
    }
  }
  events.sort((a, b) => b.id - a.id);
  const latest = typeof wire.latest_event_id === 'number' && Number.isSafeInteger(wire.latest_event_id)
    ? wire.latest_event_id : events.reduce((max, event) => Math.max(max, event.id), 0);
  const bridgeLabel = bridge === 'ok' ? '服务已连接' : bridge === 'not_configured' ? '未配置' : bridge === 'disconnected' ? '已断连' : '服务不可达';
  return {
    sample: wire.sample === true, bridge, bridgeLabel, generatedAt: formatBeijing(generated),
    cards, events: events.slice(0, 40), latestEventId: latest, footnote: FOOTNOTE,
  };
}

export function unavailableRadar(kind: RadarPageModel['bridge']): RadarPageModel {
  return {
    sample: false,
    bridge: kind,
    bridgeLabel: kind === 'not_configured' ? '未配置' : kind === 'disconnected' ? '已断连' : '服务不可达',
    generatedAt: '',
    cards: [
      { id: 'flap-events', project: 'FLAP', kind: '链上事件', state: 'unconfigured', label: '未配置', summary: '还没有本机雷达服务或 WSS。', limit: '未配置 WSS 时不轮询公共 RPC，也不连接 127.0.0.1:8545。' },
      { id: 'four-events', project: 'four.meme', kind: '链上事件', state: 'unconfigured', label: '未配置', summary: '事件枚举没有接入。', limit: FOUR_EVENT_LIMIT },
    ],
    events: [],
    latestEventId: 0,
    footnote: FOOTNOTE,
  };
}
