'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { TrackingVoiceController, VoiceControls, createWebSpeechPort, browserVoiceStorage, bindVoiceBrowserLifecycle,
  type VoiceSession, type VoiceIdentity } from '@ikun/ui';
import { resolveTrackingVoiceMetadata } from '../lib/tracking-voice-metadata';
import {clearClientSession} from '../lib/client-session-cache';

type Scope = { controller: TrackingVoiceController; identity: VoiceIdentity; revoked: boolean };
/** Only the existing TrackingLive EventSource calls this bridge. It never creates a stream. */
export function useTrackingVoice(session: VoiceSession) {
  const scope = useRef<Scope | null>(null);
  const [controller, setController] = useState<TrackingVoiceController | null>(null);
  const current = useCallback(() => {
    const value = scope.current;
    return value && !value.revoked && value.identity.user_id === session.user_id && value.identity.epoch === session.epoch ? value : null;
  }, [session.user_id, session.epoch]);
  const revoke = useCallback(() => {
    const value = current(); if (!value) return;
    clearClientSession();value.revoked = true; value.controller.setSession(null);
  }, [current]);
  useEffect(() => {
    const instance = new TrackingVoiceController({ speech: createWebSpeechPort(), storage: browserVoiceStorage(),
      resolveMetadata: resolveTrackingVoiceMetadata(revoke) });
    const value: Scope = { controller: instance, identity: { user_id: session.user_id, epoch: session.epoch }, revoked: false };
    scope.current = value; instance.setSession(session); setController(instance);
    const cleanup = bindVoiceBrowserLifecycle(instance);
    const invalidate = () => { value.revoked = true; instance.setSession(null); };
    const restored = (event: PageTransitionEvent) => { if (event.persisted) location.reload(); };
    window.addEventListener('pagehide', invalidate); document.addEventListener('freeze', invalidate); window.addEventListener('pageshow', restored);
    return () => {
      invalidate(); cleanup(); window.removeEventListener('pagehide', invalidate); document.removeEventListener('freeze', invalidate); window.removeEventListener('pageshow', restored);
      if (scope.current === value) scope.current = null;
    };
  }, [session.user_id, session.epoch, session.role, revoke]);
  const connected = useCallback((state: boolean) => {
    const value = current(); if (!value) return;
    value.controller.setStreamConnected(state, value.identity);
    if (state) value.controller.resumeAfterReconnect(value.identity, navigator.userActivation?.hasBeenActive === true);
  }, [current]);
  const verifyIdentity = useCallback(async () => {
    const before = current(); if (!before) return;
    try {
      const response = await fetch('/api/v1/auth/me', { credentials: 'same-origin', cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(2000) });
      if (scope.current !== before || before.revoked) return;
      if (response.status === 401 || response.status === 403) { revoke(); return; }
      if (!response.ok) return;
      const value = await response.json();
      if (scope.current !== before || before.revoked) return;
      if (!value || Object.keys(value).sort().join(',') !== 'data,request_id' || typeof value.request_id !== 'string' ||
        !/^[A-Za-z0-9_-]{1,64}$/.test(value.request_id) || value.data?.user_id !== session.user_id ||
        value.data?.role !== session.role || value.data?.must_change_password !== false) revoke();
    } catch { /* Remain disconnected; a transport failure never restores the old session. */ }
  }, [current, revoke, session.user_id, session.role]);
  const consumePublished = useCallback((item: unknown) => {
    const value = current(); return value ? value.controller.consumePublished(item, value.identity) : false;
  }, [current]);
  return { controller, connected, consumePublished, revoke, verifyIdentity };
}

export function TrackingVoiceSettings({ controller, subscriptions }: {
  controller: TrackingVoiceController | null; subscriptions: { subscription_id: string; label: string }[];
}) {
  return controller ? <VoiceControls controller={controller} subscriptions={subscriptions} /> : null;
}
