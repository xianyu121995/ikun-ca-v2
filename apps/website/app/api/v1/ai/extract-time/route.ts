/** Owner decision 2026-10-19: AI reads a tweet and returns the important time in Beijing time (Codex / ChatGPT Pro). */
import { execFile } from 'node:child_process';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { homedir, tmpdir } from 'node:os';
import { join } from 'node:path';
import { withAuth, requireSuperadmin } from '../../../../../../../modules/auth/dist/src/server.js';
export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

const CANDIDATES = ['/opt/homebrew/bin/codex', '/usr/local/bin/codex', '/Applications/Codex.app/Contents/Resources/codex', '/Applications/ChatGPT.app/Contents/Resources/codex'];
async function settings() {
  try { const d = JSON.parse(await readFile(process.env.IKUN_AI_CONFIG || join(homedir(), 'Library/Application Support/ikun-ca-v2-c0-lite/config/ai.json'), 'utf8'));
    return d && d.enabled !== false && d.provider === 'codex' ? d : null; } catch { return null; }
}
const fail = (status: number, code: string, message: string) => Response.json({ error: { code, message } }, { status, headers: { 'cache-control': 'no-store' } });

export async function POST(request: Request) {
  return withAuth(request, async () => {
    requireSuperadmin(request);
    let body: { text?: unknown; quote?: unknown; received_at?: unknown };
    try { body = await request.json(); } catch { return fail(422, 'VALIDATION_ERROR', '请求格式不正确'); }
    const text = typeof body.text === 'string' ? body.text.slice(0, 4000) : '';
    if (!text.trim()) return fail(422, 'VALIDATION_ERROR', '推文内容为空');
    const quote = typeof body.quote === 'string' ? body.quote.slice(0, 2000) : '';
    const cfg = await settings();
    if (!cfg) return fail(503, 'AI_NOT_CONFIGURED', 'AI 未启用（需在 ikun AI设置 里选 Codex）');
    const binary = [cfg.codex_bin, ...CANDIDATES].find(p => typeof p === 'string' && p.startsWith('/') && existsSync(p));
    if (!binary) return fail(503, 'AI_NOT_CONFIGURED', '找不到 Codex 命令行');
    const now = new Date(Date.now() + 8 * 3600_000).toISOString().slice(0, 16).replace('T', ' ');
    const prompt = `你是加密项目研究助手。从下面推文里找出项目即将发生的最重要时间点（如 TGE、发币、白名单、Mint、主网/测试网上线、空投快照）。\n` +
      `现在是北京时间 ${now}。把时间换算成北京时间（UTC+8）；"明天/今晚/周一"等相对时间按推文接收时间 ${typeof body.received_at === 'string' ? body.received_at : '未知'} 推算。\n` +
      `只输出一个 JSON：{"date":"YYYY-MM-DD 或 null","hour":"00-23 两位数 或 null（没写具体时刻就 null）","title":"不超过 20 字的中文事件说明","status":"confirmed（推文明确给出时间）或 estimated（推测/大概）"}。找不到时间就 date 为 null。不要运行任何命令。\n\n推文：${text}${quote ? `\n被引用推文：${quote}` : ''}`;
    const work = await mkdtemp(join(tmpdir(), 'ikun-ai-'));
    try {
      const out = join(work, 'out.txt');
      const env: NodeJS.ProcessEnv = { NODE_ENV: 'production', HOME: homedir(), PATH: '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin', LANG: 'en_US.UTF-8' };
      if (typeof cfg.proxy === 'string' && /^(https?|socks5h?):\/\/[A-Za-z0-9.-]+:\d{1,5}$/.test(cfg.proxy)) Object.assign(env, { HTTPS_PROXY: cfg.proxy, HTTP_PROXY: cfg.proxy, https_proxy: cfg.proxy, http_proxy: cfg.proxy });
      await new Promise<void>((resolve, reject) => execFile(binary, ['exec', '--skip-git-repo-check', '--sandbox', 'read-only', '-o', out, prompt], { cwd: work, env, timeout: 150_000, maxBuffer: 4 << 20 }, err => err ? reject(err) : resolve()));
      let raw = (await readFile(out, 'utf8')).trim().replace(/^```(?:json)?\s*|\s*```$/g, '');
      const s = raw.indexOf('{'), e = raw.lastIndexOf('}'); if (s >= 0 && e > s) raw = raw.slice(s, e + 1);
      const v = JSON.parse(raw);
      const date = typeof v.date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(v.date) ? v.date : null;
      const hour = date && typeof v.hour === 'string' && /^(?:[01]\d|2[0-3])$/.test(v.hour) ? v.hour : null;
      return Response.json({ data: { date, hour, title: typeof v.title === 'string' ? v.title.slice(0, 60) : '', status: v.status === 'confirmed' ? 'confirmed' : 'estimated' } }, { headers: { 'cache-control': 'no-store' } });
    } catch { return fail(502, 'AI_FAILED', 'AI 识别失败，请稍后再试或手动填写'); }
    finally { await rm(work, { recursive: true, force: true }); }
  });
}
