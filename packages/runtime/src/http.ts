import { randomUUID, timingSafeEqual } from "node:crypto";
import type { ApiError, ErrorCode } from "@ikun/contracts";

export function requestId(input: string | null | undefined): string {
  return input && /^[A-Za-z0-9_-]{1,64}$/.test(input) ? input : randomUUID();
}
export function apiError(code: ErrorCode, message: string, id: string, retryable = false): ApiError {
  return { error: { code, message, retryable }, request_id: id };
}
export function validBearer(header: string | null | undefined, token: string | undefined): boolean {
  if (!token || token.length < 32 || !header?.startsWith("Bearer ")) return false;
  const presented = Buffer.from(header.slice(7));
  const expected = Buffer.from(token);
  return presented.length === expected.length && timingSafeEqual(presented, expected);
}
/** Log only an explicit allowlist; never pass env, request bodies or errors wholesale. */
export function log(service: string, event: string, details: Record<string, string | number | boolean> = {}): void {
  const allowed = ["port", "pid", "mode", "code", "duration_ms", "request_id"];
  const fields = Object.fromEntries(Object.entries(details).filter(([key]) => allowed.includes(key)));
  process.stdout.write(`${JSON.stringify({ at: new Date().toISOString(), service, event, ...fields })}\n`);
}
