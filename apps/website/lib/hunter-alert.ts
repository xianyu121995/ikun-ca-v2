/** Frontend-only hunter discovery sound/title alerts. Never trusts raw SSE alone — only discovered_at vs watermark. */
export type SoundKind = 'dingdong' | 'bell' | 'soft';
export type AlertSettings = {enabled: boolean; sound: SoundKind; volume: number};
export type DiscoveryCue = {discovery_id: string; discovered_at: string | null | undefined; x_handle?: string | null};
export type AlertBatch = {count: number; handles: string[]; newestAt: number; toast: string};

export const SETTINGS_KEY = 'ikun-hunter-alert-settings';
export const WATERMARK_KEY = 'ikun-hunter-alert-watermark';
export const LOCK_NAME = 'ikun.hunter.alert.v1';
export const SOUND_OPTIONS: {id: SoundKind; label: string}[] = [
  {id: 'dingdong', label: '叮咚'},
  {id: 'bell', label: '清脆铃'},
  {id: 'soft', label: '柔和双音'},
];

export const DEFAULT_SETTINGS: AlertSettings = {enabled: false, sound: 'dingdong', volume: 0.7};

type StorageLike = Pick<Storage, 'getItem' | 'setItem'>;
type LockLike = {request: (name: string, callback: (lock: unknown) => Promise<unknown>) => Promise<unknown>};

export function parseDiscoveredAt(value: string | null | undefined): number | null {
  if (!value || typeof value !== 'string') return null;
  const at = Date.parse(value);
  return Number.isFinite(at) ? at : null;
}

export function normalizeSettings(raw: unknown): AlertSettings {
  const base = {...DEFAULT_SETTINGS};
  if (!raw || typeof raw !== 'object') return base;
  const o = raw as Record<string, unknown>;
  if (typeof o.enabled === 'boolean') base.enabled = o.enabled;
  if (o.sound === 'dingdong' || o.sound === 'bell' || o.sound === 'soft') base.sound = o.sound;
  if (typeof o.volume === 'number' && Number.isFinite(o.volume)) base.volume = Math.min(1, Math.max(0, o.volume));
  return base;
}

export function loadSettings(storage: StorageLike): AlertSettings {
  try {
    const raw = storage.getItem(SETTINGS_KEY);
    return normalizeSettings(raw ? JSON.parse(raw) : null);
  } catch {
    return {...DEFAULT_SETTINGS};
  }
}

export function saveSettings(storage: StorageLike, settings: AlertSettings): void {
  storage.setItem(SETTINGS_KEY, JSON.stringify(normalizeSettings(settings)));
}

export function loadWatermark(storage: StorageLike): number | null {
  try {
    const raw = storage.getItem(WATERMARK_KEY);
    if (raw == null || raw === '') return null;
    const n = Number(raw);
    return Number.isFinite(n) ? n : null;
  } catch {
    return null;
  }
}

export function saveWatermark(storage: StorageLike, ms: number): void {
  storage.setItem(WATERMARK_KEY, String(ms));
}

/** Items strictly newer than watermark, newest first. Drops cues without a parseable discovered_at. */
export function pickNewerThan(cues: DiscoveryCue[], watermarkMs: number): DiscoveryCue[] {
  return cues
    .map(c => ({cue: c, at: parseDiscoveredAt(c.discovered_at)}))
    .filter((x): x is {cue: DiscoveryCue; at: number} => x.at != null && x.at > watermarkMs)
    .sort((a, b) => b.at - a.at || a.cue.discovery_id.localeCompare(b.cue.discovery_id))
    .map(x => x.cue);
}

export function maxDiscoveredAt(cues: DiscoveryCue[]): number | null {
  let max: number | null = null;
  for (const c of cues) {
    const at = parseDiscoveredAt(c.discovered_at);
    if (at != null && (max == null || at > max)) max = at;
  }
  return max;
}

export function formatAlertToast(cues: DiscoveryCue[]): string {
  const handles = [...new Set(cues.map(c => (c.x_handle || '').replace(/^@/, '').trim()).filter(Boolean))];
  const shown = handles.slice(0, 3).map(h => '@' + h);
  const extra = handles.length > 3 ? ` 等 ${handles.length} 个` : '';
  const list = shown.length ? shown.join('、') + extra : '（无 handle）';
  return `新发现 ${cues.length} 个项目：${list}`;
}

export type ConsiderResult = {batch: AlertBatch | null; initialized: boolean; fired: boolean};

/**
 * Advance watermark from cues. First call (no watermark) only seeds — never fires.
 * When enabled and newer items exist, returns one batch (one sound / one toast worth).
 * Always advances watermark past any seen discoveries (even when disabled) so enabling later does not flood.
 */
export function considerCuesSync(
  cues: DiscoveryCue[],
  storage: StorageLike,
  settings: AlertSettings,
  nowMs: number = Date.now(),
): ConsiderResult {
  const watermark = loadWatermark(storage);
  const newest = maxDiscoveredAt(cues);

  if (watermark == null) {
    saveWatermark(storage, newest ?? nowMs);
    return {batch: null, initialized: true, fired: false};
  }

  const newer = pickNewerThan(cues, watermark);
  if (!newer.length) return {batch: null, initialized: false, fired: false};

  const newestAt = maxDiscoveredAt(newer)!;
  saveWatermark(storage, Math.max(watermark, newestAt));

  if (!settings.enabled) return {batch: null, initialized: false, fired: false};

  const batch: AlertBatch = {
    count: newer.length,
    handles: newer.map(c => (c.x_handle || '').replace(/^@/, '')).filter(Boolean),
    newestAt,
    toast: formatAlertToast(newer),
  };
  return {batch, initialized: false, fired: true};
}

export async function withAlertLock<T>(locks: LockLike | undefined, run: () => T | Promise<T>): Promise<T> {
  if (!locks || typeof locks.request !== 'function') return await run();
  try {
    return (await locks.request(LOCK_NAME, async () => run())) as T;
  } catch {
    return await run();
  }
}

export async function considerDiscoveries(
  cues: DiscoveryCue[],
  deps: {
    storage: StorageLike;
    locks?: LockLike;
    settings?: AlertSettings;
    nowMs?: number;
    onFire?: (batch: AlertBatch, settings: AlertSettings) => void | Promise<void>;
  },
): Promise<ConsiderResult> {
  const settings = deps.settings ?? loadSettings(deps.storage);
  return withAlertLock(deps.locks, async () => {
    const result = considerCuesSync(cues, deps.storage, settings, deps.nowMs);
    if (result.fired && result.batch && deps.onFire) await deps.onFire(result.batch, settings);
    return result;
  });
}

let audioCtx: AudioContext | null = null;

export async function unlockAudio(Ctx: typeof AudioContext = AudioContext): Promise<AudioContext | null> {
  try {
    if (!audioCtx) audioCtx = new Ctx();
    if (audioCtx.state === 'suspended') await audioCtx.resume();
    return audioCtx;
  } catch {
    return null;
  }
}

function beep(
  ctx: AudioContext,
  freq: number,
  when: number,
  dur: number,
  volume: number,
  type: OscillatorType = 'sine',
) {
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = type;
  osc.frequency.setValueAtTime(freq, when);
  gain.gain.setValueAtTime(0.0001, when);
  gain.gain.exponentialRampToValueAtTime(Math.max(0.0001, volume), when + 0.015);
  gain.gain.exponentialRampToValueAtTime(0.0001, when + dur);
  osc.connect(gain);
  gain.connect(ctx.destination);
  osc.start(when);
  osc.stop(when + dur + 0.02);
}

/** Web Audio synthesized cues — no bundled files. */
export async function playAlertSound(kind: SoundKind, volume: number, Ctx?: typeof AudioContext): Promise<boolean> {
  const ctx = await unlockAudio(Ctx ?? AudioContext);
  if (!ctx) return false;
  const v = Math.min(1, Math.max(0, volume)) * 0.32;
  const t = ctx.currentTime + 0.02;
  if (kind === 'dingdong') {
    beep(ctx, 880, t, 0.16, v, 'sine');
    beep(ctx, 659.25, t + 0.15, 0.28, v * 0.95, 'sine');
  } else if (kind === 'bell') {
    beep(ctx, 1567.98, t, 0.55, v, 'triangle');
    beep(ctx, 3135.96, t, 0.12, v * 0.35, 'sine');
    beep(ctx, 2093, t + 0.05, 0.35, v * 0.25, 'sine');
  } else {
    beep(ctx, 523.25, t, 0.32, v * 0.85, 'sine');
    beep(ctx, 659.25, t + 0.2, 0.38, v * 0.75, 'sine');
  }
  return true;
}

let flashTimer: ReturnType<typeof setInterval> | null = null;
let savedTitle = '';

export function stopTitleFlash(doc: Pick<Document, 'title'> = typeof document !== 'undefined' ? document : {title: ''}): void {
  if (flashTimer) {
    clearInterval(flashTimer);
    flashTimer = null;
  }
  if (savedTitle) {
    doc.title = savedTitle;
    savedTitle = '';
  }
}

export function startTitleFlash(
  count: number,
  doc: Pick<Document, 'title'> = typeof document !== 'undefined' ? document : {title: ''},
  schedule: typeof setInterval = setInterval,
): void {
  stopTitleFlash(doc);
  savedTitle = doc.title || '项目发现';
  const label = `(${count}) 新项目`;
  let on = true;
  doc.title = label;
  flashTimer = schedule(() => {
    on = !on;
    doc.title = on ? label : savedTitle;
  }, 1000);
}

export function bindTitleFlashLifecycle(
  target: {document: Document; addEventListener: Window['addEventListener']; removeEventListener: Window['removeEventListener']} = window,
): () => void {
  const stop = () => {
    if (!target.document.hidden) stopTitleFlash(target.document);
  };
  const onVis = () => {
    if (!target.document.hidden) stopTitleFlash(target.document);
  };
  target.addEventListener('focus', stop);
  target.document.addEventListener('visibilitychange', onVis);
  return () => {
    target.removeEventListener('focus', stop);
    target.document.removeEventListener('visibilitychange', onVis);
    stopTitleFlash(target.document);
  };
}

/** Used by the live controller after a successful list load or a single SSE discovery frame. */
export async function fireHunterAlert(
  cues: DiscoveryCue[],
  opts: {onToast?: (message: string) => void} = {},
): Promise<ConsiderResult> {
  if (typeof window === 'undefined') return {batch: null, initialized: false, fired: false};
  const settings = loadSettings(window.localStorage);
  return considerDiscoveries(cues, {
    storage: window.localStorage,
    locks: window.navigator?.locks as LockLike | undefined,
    settings,
    onFire: async (batch, s) => {
      void playAlertSound(s.sound, s.volume);
      if (typeof document !== 'undefined' && document.hidden) startTitleFlash(batch.count);
      opts.onToast?.(batch.toast);
    },
  });
}
