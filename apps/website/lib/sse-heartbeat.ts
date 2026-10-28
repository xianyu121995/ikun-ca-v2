import { untilShutdown } from './shutdown';

/** Keep quiet authenticated event streams open through proxies without creating application events. */
export function withSseHeartbeat(response: Response, requestSignal: AbortSignal, intervalMs = 25_000): Response {
  const signal = untilShutdown(requestSignal);
  if (!response.ok || !response.body || !response.headers.get('content-type')?.startsWith('text/event-stream')) return response;
  const reader = response.body.getReader(), encoder = new TextEncoder();
  let done = false, timer: ReturnType<typeof setInterval> | undefined;
  let output: ReadableStreamDefaultController<Uint8Array>;
  const cleanup = () => { done = true; clearInterval(timer); signal.removeEventListener('abort', abort); };
  const abort = () => {
    if (done) return;
    cleanup(); output.close(); void reader.cancel().catch(() => {});
  };
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      output = controller;
      if (signal.aborted) { abort(); return; }
      signal.addEventListener('abort', abort, { once: true });
      // Flush response headers immediately; EventSource ignores comments.
      controller.enqueue(encoder.encode(': connected\n\n'));
      timer = setInterval(() => {
        if (!done && (controller.desiredSize ?? 0) > 0) controller.enqueue(encoder.encode(': heartbeat\n\n'));
      }, intervalMs);
      timer.unref?.();
    },
    async pull(controller) {
      try {
        const part = await reader.read();
        if (done) return;
        if (part.done) { cleanup(); controller.close(); }
        else controller.enqueue(part.value);
      } catch (error) {
        if (!done) { cleanup(); controller.error(error); }
        void reader.cancel().catch(() => {});
      }
    },
    cancel(reason) { cleanup(); return reader.cancel(reason); },
  });
  const headers = new Headers(response.headers);
  headers.set('cache-control', 'no-store, private, no-transform');
  headers.set('x-accel-buffering', 'no');
  headers.delete('content-length');
  headers.delete('content-encoding');
  return new Response(body, { status: response.status, headers });
}
