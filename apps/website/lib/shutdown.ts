/** Process-wide shutdown signal for long-lived responses (SSE). Next's production
 * start-server only calls server.close() on SIGTERM, which waits for every open
 * connection; open EventSource streams therefore kept the process alive until
 * systemd's SIGKILL. Streams subscribe here and end themselves on shutdown, and a
 * bounded fallback exit guarantees the process leaves within the grace period. */
const KEY = Symbol.for('ikun.website.shutdown');
type ShutdownState = { controller: AbortController; installed: boolean };

function state(): ShutdownState {
  const scope = globalThis as typeof globalThis & { [KEY]?: ShutdownState };
  return (scope[KEY] ??= { controller: new AbortController(), installed: false });
}

export function shutdownSignal(): AbortSignal {
  return state().controller.signal;
}

/** Combine a request signal with the process shutdown signal. */
export function untilShutdown(signal: AbortSignal): AbortSignal {
  return AbortSignal.any([signal, shutdownSignal()]);
}

export function installShutdown(): void {
  const current = state();
  if (current.installed) return;
  current.installed = true;
  const parsed = Number(process.env.IKUN_WEB_SHUTDOWN_GRACE_MS ?? '3000');
  const graceMs = Number.isFinite(parsed) && parsed >= 0 ? Math.min(parsed, 30_000) : 3000;
  const begin = (code: number) => {
    if (current.controller.signal.aborted) return;
    current.controller.abort();
    // Next's own handler keeps running server.close(); this only bounds the wait.
    setTimeout(() => process.exit(code), graceMs).unref();
  };
  process.once('SIGTERM', () => begin(143));
  process.once('SIGINT', () => begin(130));
}
