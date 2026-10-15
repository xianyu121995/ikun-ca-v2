import { argon2, createHash, randomBytes, timingSafeEqual } from "node:crypto";

export class AuthError extends Error {
  constructor(public status: number, public code: string, message: string, public retryAfter = 0, public reason = "") {
    super(message);
  }
}
export const invalid = (message = "请求参数无效") => new AuthError(422, "VALIDATION_ERROR", message);
export const secret = () => randomBytes(32).toString("base64url");
export const digest = (value: string) => createHash("sha256").update(value).digest("hex");
export function equal(a: string, b: string) {
  const left = Buffer.from(a), right = Buffer.from(b);
  return left.length === right.length && timingSafeEqual(left, right);
}
export function username(value: unknown): string {
  if (typeof value !== "string") throw invalid();
  const key = value.trim().toLowerCase();
  if (!/^[a-z0-9][a-z0-9_.-]{2,31}$/.test(key))
    throw invalid("用户名须为 3–32 位字母、数字、点、下划线或短横线");
  return key;
}
export function password(value: unknown, creating = true): string {
  if (typeof value !== "string" || [...value].length < (creating ? 15 : 1) ||
      [...value].length > 128 || Buffer.byteLength(value) > 512)
    throw invalid("密码须为 15–128 个字符，建议使用独立长口令");
  return value;
}

// Per website process. Native asynchronous Argon2 doesn't block the event loop.
let active = 0;
async function derive(value: string, salt: Buffer): Promise<Buffer> {
  if (active >= 4) throw new AuthError(429, "RATE_LIMITED", "登录服务繁忙，请稍后重试", 2);
  active++;
  try {
    return await new Promise((resolve, reject) => argon2("argon2id", {
      message: value, nonce: salt, memory: 65536, passes: 3, parallelism: 1, tagLength: 32,
    }, (error, key) => error ? reject(error) : resolve(key)));
  } finally { active--; }
}
export async function hashPassword(value: string): Promise<string> {
  const salt = randomBytes(16), key = await derive(value, salt);
  return `$argon2id$v=19$m=65536,t=3,p=1$${salt.toString("base64")}$${key.toString("base64")}`;
}
export async function verifyPassword(encoded: string, value: string): Promise<boolean> {
  // Only accept our bounded parameters; a corrupt DB must not select arbitrary work factors.
  const match = /^\$argon2id\$v=19\$m=65536,t=3,p=1\$([A-Za-z0-9+/]{22}==)\$([A-Za-z0-9+/]{43}=)$/.exec(encoded);
  if (!match) return false;
  const actual = await derive(value, Buffer.from(match[1]!, "base64"));
  const expected = Buffer.from(match[2]!, "base64");
  return actual.length === expected.length && timingSafeEqual(actual, expected);
}
// A real, random per-process dummy hash equalizes absent/disabled/wrong-password work.
let dummy: Promise<string> | undefined;
export function dummyHash() { return dummy ??= hashPassword(secret()).catch(error => { dummy = undefined; throw error; }); }
