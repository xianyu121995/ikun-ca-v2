'use client';
/** Site-wide tweet voice (owner decision 2026-10-18, option 2): lives in the root layout so it keeps
 *  speaking while the owner moves between pages with client-side navigation. */
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { VoiceControls, type TrackingVoiceController, type VoiceSession } from '@ikun/ui';
import {loadTrackingSubscriptions} from '../lib/tracking-subscriptions-cache';
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
  const [subs, setSubs] = useState<{ subscription_id: string; label: string }[]>([]);
  // Per-account voice switches (moved here from the tracking page; owner decision 2026-10-19).
  useEffect(() => { if (!open) return; let stopped=false;
    loadTrackingSubscriptions(session.user_id).then(rows=>{if(!stopped)setSubs(rows.filter(row=>row.desired_state!=='removed').map(row=>({subscription_id:row.subscription_id,label:(row.name||row.x_handle)+(row.x_handle?' @'+row.x_handle:'')})));}).catch(()=>{});
    return()=>{stopped=true;};},[open,session.user_id]);
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
  // Owner 2026-10-19: voice is ON by default and only off when the user turns it off. Browsers only allow audio
  // after a real click, so the first click anywhere on the site arms it — unless this account turned voice off
  // (tracked with an explicit opt-out flag, set when 语音 goes on→off and cleared when it goes back on).
  // Night quiet hours (22–08) are switched off once per account (owner: 常开); they can be re-enabled in the panel.
  useEffect(() => {
    if (!controller) return;
    const uid = encodeURIComponent(session.user_id), optKey = 'ikun.voice.optout.' + uid, quietKey = 'ikun.voice.quietoff.' + uid;
    const get = (k: string) => { try { return window.localStorage.getItem(k); } catch { return null; } };
    const set = (k: string, v: string | null) => { try { if (v === null) window.localStorage.removeItem(k); else window.localStorage.setItem(k, v); } catch { /* per-browser convenience only */ } };
    const first = controller.getSnapshot();
    if (!get(quietKey)) { if (first.quiet_hours.enabled) controller.setQuietHours({ ...first.quiet_hours, enabled: false }); set(quietKey, '1'); }
    let wasEnabled = controller.getSnapshot().enabled;
    const unsubscribe = controller.subscribe(() => {
      const snapshot = controller.getSnapshot();
      // Page teardown clears the session; it is not a user's mute decision.
      if (snapshot.status === 'signed-out') return;
      const now = snapshot.enabled;
      if (wasEnabled && !now) set(optKey, '1'); else if (!wasEnabled && now) set(optKey, null);
      wasEnabled = now;
    });
    const arm = (event: Event) => {
      if ((event.target as Element | null)?.closest?.('.ikun-voice-dock')) return;
      const s = controller.getSnapshot();
      if (s.armed || get(optKey)) return;
      controller.enableFromGesture(event);
    };
    document.addEventListener('click', arm, true);
    return () => { document.removeEventListener('click', arm, true); unsubscribe(); };
  }, [controller, session.user_id]);
  return <VoiceContext.Provider value={controller}>{children}
    {controller && <div className="ikun-voice-dock" data-state={status}>
      {open && <div className="ikun-voice-panel"><VoiceControls controller={controller} subscriptions={subs} /></div>}
      <button type="button" className="ikun-voice-fab" aria-expanded={open} title="实时推文语音"
        onClick={event => { if (status === 'locked') controller.enableFromGesture(event.nativeEvent); else setOpen(o => !o); }}>
        {status === 'on' ? '🔊' : status === 'locked' ? '🔈' : '🔇'}<span className="ikun-voice-label">{status === 'on' ? ' 语音开' : status === 'locked' ? ' 点我恢复语音' : ' 语音关'}</span>
      </button>
    </div>}
  </VoiceContext.Provider>;
}
