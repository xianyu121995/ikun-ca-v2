/** Owner decision 2026-10-19: AI reads a tweet and returns the important time in Beijing time. */
import { randomUUID } from 'node:crypto';
import { execFile } from 'node:child_process';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { homedir, tmpdir } from 'node:os';
import { join } from 'node:path';
import { withAuth, requireSuperadmin } from '../../../../../../../modules/auth/dist/src/server.js';
import { configFrom, deepseekExtract, parseTimeJson, timePrompt, unconfiguredMessage, beijingNow } from '../../../../../lib/ai-extract-time';
export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

const CANDIDATES = ['/opt/homebrew/bin/codex', '/usr/local/bin/codex', '/Applications/Codex.app/Contents/Resources/codex', '/Applications/ChatGPT.app/Contents/Resources/codex'];
async function settings() {
  try {
    const raw = JSON.parse(await readFile(process.env.IKUN_AI_CONFIG || join(homedir(), 'Library/Application Support/ikun-ca-v2-c0-lite/config/ai.json'), 'utf8'));
    return { raw, cfg: configFrom(raw, process.env) };
  } catch { return { raw: null, cfg: null }; }
}
const fail = (status: number, code: string, message: string) => Response.json({ error: { code, message } }, { status, headers: { 'cache-control': 'no-store' } });

type Job = { owner: string; at: number; result?: Response };
const shared = globalThis as typeof globalThis & { ikunTimeJobs?: Map<string, Job> };
const jobs = shared.ikunTimeJobs ??= new Map<string, Job>();
export async function GET(request: Request) {
  return withAuth(request, async () => {
    const actor = requireSuperadmin(request);
    const job = jobs.get(new URL(request.url).searchParams.get('job') ?? '');
    if (!job || job.owner !== actor.user_id) return fail(404, 'AI_JOB_EXPIRED', '识别任务已过期，请重新识别');
    return job.result?.clone() ?? Response.json({ data: { pending: true } }, { status: 202 });
  });
}

export async function POST(request: Request) {
  return withAuth(request, async () => {
    const actor = requireSuperadmin(request);
    let body: { text?: unknown; quote?: unknown; received_at?: unknown };
    try { body = await request.json(); } catch { return fail(422, 'VALIDATION_ERROR', '请求格式不正确'); }
    const text = typeof body.text === 'string' ? body.text.slice(0, 4000) : '';
    if (!text.trim()) return fail(422, 'VALIDATION_ERROR', '推文内容为空');
    const quote = typeof body.quote === 'string' ? body.quote.slice(0, 2000) : '';
    const loaded = await settings();
    if (!loaded.cfg) return fail(503, 'AI_NOT_CONFIGURED', unconfiguredMessage(loaded.raw, process.env));
    const cfg = loaded.cfg;
    const binary = cfg.provider === 'codex' ? [cfg.codexBin, ...CANDIDATES].find(p => typeof p === 'string' && p.startsWith('/') && existsSync(p)) : undefined;
    if (cfg.provider === 'codex' && !binary) return fail(503, 'AI_NOT_CONFIGURED', '找不到 Codex 命令行');
    const now = beijingNow();
    const prompt = timePrompt(text, quote, typeof body.received_at === 'string' ? body.received_at : '未知', now);
    for (const [key, job] of jobs) if (Date.now() - job.at > 10 * 60_000) jobs.delete(key);
    const existing = [...jobs].find(([, job]) => job.owner === actor.user_id && !job.result);
    if (existing) return Response.json({ data: { pending: true, job: existing[0] } }, { status: 202 });
    if (jobs.size >= 100) return fail(429, 'AI_BUSY', '识别任务较多，请稍后再试');
    const id = randomUUID(), job: Job = { owner: actor.user_id, at: Date.now() };
    jobs.set(id, job);
    void (async (): Promise<Response> => {
    if (cfg.provider === 'deepseek') {
      try {
        const data = await deepseekExtract(cfg, prompt, (url, init) => fetch(url, init));
        return Response.json({ data }, { headers: { 'cache-control': 'no-store' } });
      } catch (error) {
        const status = error instanceof Error && 'status' in error && typeof error.status === 'number' ? error.status : 502;
        const code = error instanceof Error && 'code' in error && typeof error.code === 'string' ? error.code : 'AI_FAILED';
        const message = error instanceof Error && error.message && !error.message.includes(cfg.apiKey) ? error.message : 'AI 识别失败，请稍后再试或手动填写';
        return fail(status, code, message);
      }
    }
    const work = await mkdtemp(join(tmpdir(), 'ikun-ai-'));
    try {
      const out = join(work, 'out.txt');
      const env: NodeJS.ProcessEnv = { NODE_ENV: 'production', HOME: homedir(), PATH: '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin', LANG: 'en_US.UTF-8' };
      if (cfg.proxy) Object.assign(env, { HTTPS_PROXY: cfg.proxy, HTTP_PROXY: cfg.proxy, https_proxy: cfg.proxy, http_proxy: cfg.proxy });
      await new Promise<void>((resolve, reject) => execFile(binary!, ['exec', '--skip-git-repo-check', '--sandbox', 'read-only', '-o', out, prompt], { cwd: work, env, timeout: 240_000, maxBuffer: 4 << 20 }, err => err ? reject(err) : resolve()).stdin?.end());
      const value = parseTimeJson(await readFile(out, 'utf8'));
      return Response.json({ data: value }, { headers: { 'cache-control': 'no-store' } });
    } catch { return fail(502, 'AI_FAILED', 'AI 识别失败，请稍后再试或手动填写'); }
    finally { await rm(work, { recursive: true, force: true }); }
    })().then(result => { job.result = result; }).catch(() => { job.result = fail(502, 'AI_FAILED', 'AI 识别失败，请稍后再试'); });
    return Response.json({ data: { pending: true, job: id } }, { status: 202, headers: { 'cache-control': 'no-store' } });
  });
}
