import { isAbsolute, resolve } from "node:path";

export interface AuthConfig {
  dataRoot: string;
  origin: string;
  secure: boolean;
  absoluteTtl: number;
  idleTtl: number;
  rateWindow: number;
  accountAttempts: number;
  ipAttempts: number;
  globalAttempts: number;
  maxSessions: number;
  tenantId: string;
}
export function config(input: Partial<AuthConfig> & Pick<AuthConfig, "dataRoot">): AuthConfig {
  const cfg: AuthConfig = {origin: "https://ikun.ca", secure: true, absoluteTtl: 43200,
    idleTtl: 1800, rateWindow: 900, accountAttempts: 10, ipAttempts: 30,
    globalAttempts: 300, maxSessions: 5, tenantId: "ikun-main", ...input};
  if (!/^[a-zA-Z0-9_-]{1,64}$/.test(cfg.tenantId)) throw new Error("AUTH_SCOPE_REJECTED");
  if (!isAbsolute(cfg.dataRoot)) throw new Error("AUTH_DATA_ROOT_MUST_BE_ABSOLUTE");
  const url = new URL(cfg.origin);
  if (url.origin !== cfg.origin || url.username || url.password ||
      (cfg.secure ? url.protocol !== "https:" :
        url.protocol !== "http:" || !["localhost", "127.0.0.1", "[::1]"].includes(url.hostname)))
    throw new Error("AUTH_ORIGIN_REJECTED");
  for (const value of [cfg.absoluteTtl, cfg.idleTtl, cfg.rateWindow, cfg.accountAttempts,
    cfg.ipAttempts, cfg.globalAttempts, cfg.maxSessions])
    if (!Number.isSafeInteger(value) || value <= 0) throw new Error("AUTH_LIMIT_REJECTED");
  return cfg;
}
export const cookieName = (cfg: AuthConfig) => cfg.secure ? "__Host-ikun_session" : "ikun_dev_session";
export function environment(): AuthConfig {
  if (!process.env.DATA_ROOT) throw new Error("AUTH_DATA_ROOT_REQUIRED");
  return config({dataRoot: resolve(process.env.DATA_ROOT),
    origin: process.env.IKUN_AUTH_ORIGIN ?? "https://ikun.ca", secure: process.env.IKUN_AUTH_DEV !== "1",
    tenantId: process.env.IKUN_AUTH_TENANT_ID ?? "ikun-main"});
}
