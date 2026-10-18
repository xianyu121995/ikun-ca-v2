'use client';
/** Site-wide tweet voice (owner decision 2026-10-18, option 2): lives in the root layout so it keeps
 *  speaking while the owner moves between pages with client-side navigation. */
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { VoiceControls, type TrackingVoiceController, type VoiceSession } from '@ikun/ui';
import { useTrackingVoice } from './tracking-voice';

const VoiceContext = createContext<TrackingVoiceController | null>(null);
export const useSiteVoice = () => useContext(VoiceContext);

type Me = { user_id: string; role: 'superadmin' | 'user'; must_change_password: boolean };

export function VoiceDock({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<VoiceSession | null>(null);
  useEffect(() => {
    let stopped = false;
    fetch('/api/v1/auth/me', { credentials: 'same-origin', cache: 'no-store', signal: AbortSignal.timeout(5000) })
      .then(r => r.ok ? r.json() : null).then(v => {
        const me: Me | undefined = v?.data;
        if (!stopped && me && typeof me.user_id === 'string' && !me.must_change_password && (me.role === 'superadmin' || me.role === 'user'))
          setSession({ user_id: me.user_id, role: me.role, epoch: crypto.randomUUID() });
      }).catch(() => { /* signed out or offline: no voice */ });
    return () => { stopped = true; };
  }, []);
  return session ? <Live session={session}>{children}</Live> : <>{children}</>;
}

function Live({ session, children }: { session: VoiceSession; children: ReactNode }) {
  const voice = useTrackingVoice(session);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const events = new EventSource('/api/v1/tracking/events');
    const opened = () => voice.connected(true);
    const disconnected = () => { voice.connected(false); void voice.verifyIdentity(); };
    const created = (event: Event) => voice.consume(event as MessageEvent);
    events.addEventListener('open', opened);
    events.addEventListener('error', disconnected);
    events.addEventListener('tracking.feed.activity.created.v1', created);
    return () => { voice.connected(false); events.close(); };
  }, [voice.connected, voice.consume, voice.verifyIdentity]);
  const controller = voice.controller;
  const [status, setStatus] = useState('');
  useEffect(() => {
    if (!controller) return;
    const update = () => { const s = controller.getSnapshot(); setStatus(!s.enabled ? 'off' : s.armed ? 'on' : 'locked'); };
    update(); return controller.subscribe(update);
  }, [controller]);
  return <VoiceContext.Provider value={controller}>{children}
    {controller && <div className="ikun-voice-dock" data-state={status}>
      {open && <div className="ikun-voice-panel"><VoiceControls controller={controller} /></div>}
      <button type="button" className="ikun-voice-fab" aria-expanded={open} title="实时推文语音"
        onClick={event => { if (status === 'locked') controller.enableFromGesture(event.nativeEvent); else setOpen(o => !o); }}>
        {status === 'on' ? '🔊' : status === 'locked' ? '🔈' : '🔇'}<span className="ikun-voice-label">{status === 'on' ? ' 语音开' : status === 'locked' ? ' 点我恢复语音' : ' 语音关'}</span>
      </button>
    </div>}
  </VoiceContext.Provider>;
}
