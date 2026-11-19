'use client';

import {useEffect, useState} from 'react';
import {ToastViewport, type ToastMessage} from '@ikun/ui';
import {useSiteVoice} from '../../components/voice-context';
import {maybeSpeak, presentRadar, sealWatermark, seenKey, shouldNotify} from '../../lib/radar-view';
import './radar.css';

export function RadarAlerts({userId}: {userId: string}) {
  const voice = useSiteVoice();
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const [unseen, setUnseen] = useState(0);
  const [link, setLink] = useState('连接中');
  useEffect(() => {
    const key = seenKey(userId);
    if (!key) return;
    let stopped = false;
    let cursor = '';
    let backoff = 1000;
    let disconnectNoted = false;
    const toasted = new Set<number>();
    const spoken = new Set<number>();
    const refreshUnseen = () => {
      const mark = sealWatermark(window.localStorage.getItem(key), Number.MAX_SAFE_INTEGER);
      setUnseen([...toasted].filter(id => id > mark).length);
    };
    const onSeen = () => refreshUnseen();
    window.addEventListener('radar-seen', onSeen);
    window.addEventListener('storage', onSeen);
    const push = (toast: ToastMessage) => setToasts(list => [...list.filter(item => item.id !== toast.id), toast].slice(-3));
    const wait = (ms: number) => new Promise(resolve => window.setTimeout(resolve, ms));
    const handle = (block: string) => {
      let id = '', name = '', data = '';
      for (const line of block.split('\n')) {
        if (line.startsWith('id:')) id = line.slice(3).trim();
        else if (line.startsWith('event:')) name = line.slice(6).trim();
        else if (line.startsWith('data:')) data += line.slice(5).trim();
      }
      if (name === 'hello') {
        try {
          const hello = JSON.parse(data) as {cursor?: number};
          if (!cursor && typeof hello.cursor === 'number') {
            cursor = String(hello.cursor);
            if (window.localStorage.getItem(key) === null) window.localStorage.setItem(key, cursor);
          }
        } catch { /* ignore malformed hello */ }
        return;
      }
      if (name !== 'radar' || !data) return;
      let row: unknown;
      try { row = JSON.parse(data); } catch { return; }
      const model = presentRadar({bridge: 'ok', generated_at: 0, coverage: [], events: [row], latest_event_id: 0, sample: false}, Math.floor(Date.now() / 1000));
      const event = model?.events[0];
      if (!event) return;
      if (/^\d+$/.test(id)) cursor = id;
      const watermark = sealWatermark(window.localStorage.getItem(key), event.id);
      if (!shouldNotify(event, watermark, toasted)) return;
      toasted.add(event.id);
      push({id: `radar-${event.id}`, title: `${event.project} ${event.motion || '有变化'}`, description: event.title, tone: event.level === 'crit' ? 'danger' : event.level === 'warn' ? 'warning' : 'info'});
      const snap = voice?.getSnapshot();
      const quiet = snap?.status === 'quiet-hours' || snap?.status === 'speaking' || snap?.status === 'starting';
      void maybeSpeak({
        event, armed: snap?.armed === true, enabled: snap?.enabled === true, quiet, available: snap?.available === 'available', spoken,
        speak: text => {
          const say = () => {
            if (window.speechSynthesis.speaking) return;
            const utterance = new SpeechSynthesisUtterance(text);
            utterance.lang = 'zh-CN';
            window.speechSynthesis.speak(utterance);
          };
          if (!navigator.locks) { if (document.visibilityState === 'visible') say(); return; }
          void navigator.locks.request('ikun.radar.speaker.v1', {ifAvailable: true}, async lock => { if (lock) say(); });
        },
      });
      refreshUnseen();
    };
    const run = async () => {
      while (!stopped) {
        const headers: Record<string, string> = {};
        if (cursor) headers['last-event-id'] = cursor;
        try {
          const response = await fetch('/api/v1/radar/events', {headers, credentials: 'same-origin', cache: 'no-store'});
          if (response.status === 401 || response.status === 403) { setLink('未登录'); return; }
          if (response.status === 503) {
            const body = await response.json().catch(() => null);
            setLink(body?.error?.code === 'RADAR_NOT_CONFIGURED' ? '未配置' : '已断连');
            await wait(30000);
            continue;
          }
          if (!response.ok || !response.body) throw new Error('down');
          setLink('已连接');
          disconnectNoted = false;
          backoff = 1000;
          const reader = response.body.getReader();
          const decoder = new TextDecoder();
          let buffer = '';
          while (!stopped) {
            const part = await reader.read();
            if (part.done) break;
            buffer += decoder.decode(part.value, {stream: true});
            const blocks = buffer.split('\n\n');
            buffer = blocks.pop() ?? '';
            for (const block of blocks) if (block.trim()) handle(block);
          }
        } catch {
          if (stopped) return;
          setLink('已断连');
          if (!disconnectNoted) { disconnectNoted = true; push({id: 'radar-link', title: '模式雷达已断连', tone: 'warning'}); }
          await wait(backoff);
          backoff = Math.min(backoff * 2, 30000);
        }
      }
    };
    void run();
    return () => { stopped = true; window.removeEventListener('radar-seen', onSeen); window.removeEventListener('storage', onSeen); };
  }, [userId, voice]);
  return <>
    <a className="radar-entry" href="/radar" data-hot={unseen > 0 ? '1' : '0'}>模式雷达 <span className="radar-count">{unseen > 0 ? unseen : link}</span></a>
    <div className="radar-toasts"><ToastViewport messages={toasts} onDismiss={id => setToasts(list => list.filter(item => item.id !== id))}/></div>
  </>;
}
