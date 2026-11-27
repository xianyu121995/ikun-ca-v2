import { existsSync, readFileSync } from "node:fs";
import { execFile } from "node:child_process";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { homedir, tmpdir } from "node:os";
import { join } from "node:path";
import { configFrom, deepseekBody, deepseekEndpoint, unconfiguredMessage, type DeepSeekConfig } from "./ai-extract-time";

export interface AnalysisEvidence {
  event_title: string;
  official_status: string;
  name: string;
  role: string;
  place: string;
  track: string;
  info: string;
  website: string;
  handle: string;
  tweets: { occurred_at: string; text: string }[];
}

export type AnalysisResult = { ok: true; text: string; thin: boolean } | { ok: false; message: string };

const CODEX = ["/opt/homebrew/bin/codex", "/usr/local/bin/codex"];

export function analysisPrompt(evidence: AnalysisEvidence) {
  const tweets = evidence.tweets.length
    ? evidence.tweets.map(tweet => `- ${tweet.occurred_at} ${tweet.text}`).join("\n")
    : "无";
  return [
    "你是黑客松项目分析助手。只用下面列出的官方字段，以及监控开始后已经保存的官推，写一段简体中文分析。",
    "不要编造奖项、名次、官网、推特账号或链上事实。材料里没有的内容就不要写成事实。",
    "材料很少时，正文第一句必须是「公开资料很少。」并把 thin 设为 true。",
    '只输出一个 JSON：{"analysis":"不超过 600 字","thin":true 或 false}。',
    "",
    `赛事：${evidence.event_title || "未提供"}`,
    `官方状态：${evidence.official_status || "未提供"}`,
    `项目名：${evidence.name}`,
    `名单角色：${evidence.role}`,
    `官方名次：${evidence.place || "无"}`,
    `赛道：${evidence.track || "无"}`,
    `官方简介：${evidence.info || "无"}`,
    `官网：${evidence.website || "无"}`,
    `官推：${evidence.handle ? "@" + evidence.handle : "无"}`,
    `已保存推文：\n${tweets}`,
  ].join("\n");
}

export function reviewAnalysis(raw: string, evidence: AnalysisEvidence): { text: string; thin: boolean } | null {
  let text = raw.trim().replace(/^```(?:json)?\s*|\s*```$/g, "");
  const start = text.indexOf("{");
  const end = text.lastIndexOf("}");
  if (start < 0 || end <= start) return null;
  let parsed: { analysis?: unknown; thin?: unknown };
  try { parsed = JSON.parse(text.slice(start, end + 1)); } catch { return null; }
  const analysis = typeof parsed.analysis === "string" ? parsed.analysis.trim().slice(0, 4000) : "";
  if (!analysis) return null;
  if (!evidence.place && /第\s*\d+\s*名|冠军|亚军|季军/.test(analysis)) return null;
  const officialNumber = /(\d+)/.exec(evidence.place)?.[1];
  if (officialNumber && [...analysis.matchAll(/第\s*(\d+)\s*名/g)].some(item => item[1] !== officialNumber)) return null;
  const allowedUrls = [evidence.website, ...evidence.tweets.flatMap(tweet => tweet.text.match(/https?:\/\/[^\s)]+/g) ?? [])].filter(Boolean);
  const urls = analysis.match(/https?:\/\/[^\s)]+/g) ?? [];
  if (urls.some(url => !allowedUrls.some(allowed => url.startsWith(allowed) || allowed.startsWith(url)))) return null;
  const mentions = analysis.match(/@[A-Za-z0-9_]{1,15}/g) ?? [];
  if (mentions.some(item => item.slice(1).toLowerCase() !== evidence.handle.toLowerCase())) return null;
  const thin = parsed.thin === true || analysis.startsWith("公开资料很少");
  return { text: analysis, thin };
}

function loadAi(env: NodeJS.ProcessEnv) {
  let raw: unknown = null;
  const path = env.IKUN_AI_CONFIG || join(homedir(), "Library/Application Support/ikun-ca-v2-c0-lite/config/ai.json");
  try { raw = JSON.parse(readFileSync(path, "utf8")); } catch { raw = null; }
  return { raw, cfg: configFrom(raw, env) };
}

type FetchLike = (url: string, init: { method: string; headers: Record<string, string>; body: string; signal: AbortSignal }) => Promise<{ status: number; json: () => Promise<unknown> }>;

async function deepseekText(cfg: DeepSeekConfig, prompt: string, fetchImpl: FetchLike) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), cfg.timeoutMs);
  try {
    const response = await fetchImpl(deepseekEndpoint(cfg.baseUrl), {
      method: "POST",
      headers: { authorization: `Bearer ${cfg.apiKey}`, "content-type": "application/json" },
      body: JSON.stringify(deepseekBody(cfg.model, prompt)),
      signal: controller.signal,
    });
    if (response.status === 401 || response.status === 403) return { ok: false as const, message: "DeepSeek 拒绝了密钥，没有写入分析" };
    if (response.status !== 200) return { ok: false as const, message: "AI 分析失败，没有写入结果" };
    const payload = await response.json();
    const content = (payload as { choices?: { message?: { content?: unknown } }[] } | null)?.choices?.[0]?.message?.content;
    return typeof content === "string" ? { ok: true as const, content } : { ok: false as const, message: "AI 返回无法解析，没有写入分析" };
  } catch (error) {
    const name = error instanceof Error ? error.name : "";
    if (name === "AbortError" || name === "TimeoutError") return { ok: false as const, message: "AI 分析超时，没有写入结果" };
    return { ok: false as const, message: "AI 分析失败，没有写入结果" };
  } finally {
    clearTimeout(timer);
  }
}

async function codexText(binary: string, prompt: string) {
  const work = await mkdtemp(join(tmpdir(), "ikun-hackathon-ai-"));
  try {
    const out = join(work, "out.txt");
    const env: NodeJS.ProcessEnv = { NODE_ENV: "production", HOME: homedir(), PATH: "/usr/local/bin:/usr/bin:/bin", LANG: "zh_CN.UTF-8" };
    await new Promise<void>((resolve, reject) => {
      const child = execFile(binary, ["exec", "--skip-git-repo-check", "--sandbox", "read-only", "-o", out, prompt], {
        cwd: work,
        timeout: 90_000,
        maxBuffer: 1 << 20,
        env,
      }, (error: Error | null) => error ? reject(error) : resolve());
      child.stdin?.end();
    });
    return { ok: true as const, content: await readFile(out, "utf8") };
  } catch {
    return { ok: false as const, message: "Codex 没有返回可用分析，没有写入结果" };
  } finally {
    await rm(work, { recursive: true, force: true });
  }
}

export async function generateHackathonAnalysis(evidence: AnalysisEvidence, env: NodeJS.ProcessEnv = process.env, fetchImpl: FetchLike = fetch): Promise<AnalysisResult> {
  const loaded = loadAi(env);
  if (!loaded.cfg) {
    return { ok: false, message: `${unconfiguredMessage(loaded.raw, env)}。黑客松分析需要 IKUN_AI_CONFIG 指向现有 ai.json（provider 为 deepseek 或 codex），DeepSeek 另需 DEEPSEEK_API_KEY。没有生成时不会编造分析。` };
  }
  const prompt = analysisPrompt(evidence);
  let content = "";
  if (loaded.cfg.provider === "deepseek") {
    const produced = await deepseekText(loaded.cfg, prompt, fetchImpl);
    if (!produced.ok) return produced;
    content = produced.content;
  } else {
    const binary = [loaded.cfg.codexBin, ...CODEX].find(item => item && existsSync(item));
    if (!binary) return { ok: false, message: "找不到 Codex 命令行。也可在 ai.json 里改用 DeepSeek，并设置 DEEPSEEK_API_KEY。没有写入分析。" };
    const produced = await codexText(binary, prompt);
    if (!produced.ok) return produced;
    content = produced.content;
  }
  const reviewed = reviewAnalysis(content, evidence);
  if (!reviewed) return { ok: false, message: "AI 返回无法按官方材料核对，没有写入分析" };
  return { ok: true, ...reviewed };
}

export interface TweetEventInput {
  text: string;
  occurred_at: string;
  handle: string;
  project_name: string;
  place?: string;
}

export type TweetEventReview =
  | { thin: true; analysis: string; title: string; date: null; hour: null; status: null; starts_at: null }
  | { thin: false; analysis: string; title: string; date: string; hour: string | null; status: "confirmed" | "estimated"; starts_at: string };

export function tweetEventPrompt(input: TweetEventInput) {
  return [
    "你是黑客松官推分析助手。只根据下面这条已经保存的推文，判断它有没有写出具体日期或钟点。",
    "不要编造奖项、名次、官网、推特账号或链上事实。推文没写的时间就不要猜。",
    "没有具体日期时 concrete=false，analysis 写「这条推文没有写出具体时间。」",
    "date 用北京时间的 YYYY-MM-DD。hour 用 00 到 23 的两位，没写钟点就 null。title 不超过 40 字简体中文。",
    '只输出一个 JSON：{"concrete":false,"title":"","date":null,"hour":null,"status":"estimated","analysis":"这条推文没有写出具体时间。"}',
    "",
    `项目：${input.project_name}`,
    `官推：@${input.handle}`,
    `推文时间：${input.occurred_at}`,
    `推文：${input.text}`,
  ].join("\n");
}

function beijingDay(iso: string) {
  const time = Date.parse(iso);
  if (!Number.isFinite(time)) return null;
  const shifted = new Date(time + 8 * 3600_000);
  return { year: shifted.getUTCFullYear(), month: shifted.getUTCMonth() + 1, day: shifted.getUTCDate() };
}

function dateIsInTweet(text: string, occurredAt: string, date: string) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date);
  if (!match) return false;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const forms = [`${year}-${match[2]}-${match[3]}`, `${month}月${day}日`, `${month}/${day}`, `${month}.${day}`];
  if (forms.some(form => text.includes(form))) return true;
  const base = beijingDay(occurredAt);
  if (!base) return false;
  const diff = Math.round((Date.UTC(year, month - 1, day) - Date.UTC(base.year, base.month - 1, base.day)) / 86400000);
  if (diff === 0 && /今天|今日/.test(text)) return true;
  if (diff === 1 && /明天|明日/.test(text)) return true;
  if (diff === 2 && /后天/.test(text)) return true;
  return false;
}

function hourIsInTweet(text: string, hour: string) {
  const value = Number(hour);
  if (!Number.isInteger(value) || value < 0 || value > 23) return false;
  return new RegExp(`(?:^|\\D)0?${value}(?:\\s*(?:点|:|：))`).test(text);
}

export function reviewTweetEvent(raw: string, input: TweetEventInput): TweetEventReview | null {
  let text = raw.trim().replace(/^```(?:json)?\s*|\s*```$/g, "");
  const start = text.indexOf("{");
  const end = text.lastIndexOf("}");
  if (start < 0 || end <= start) return null;
  let parsed: { concrete?: unknown; title?: unknown; date?: unknown; hour?: unknown; status?: unknown; analysis?: unknown };
  try { parsed = JSON.parse(text.slice(start, end + 1)); } catch { return null; }
  const analysis = typeof parsed.analysis === "string" ? parsed.analysis.trim().slice(0, 600) : "";
  if (!analysis) return null;
  if (!input.place && /第\s*\d+\s*名|冠军|亚军|季军/.test(analysis)) return null;
  const mentions = analysis.match(/@[A-Za-z0-9_]{1,15}/g) ?? [];
  if (mentions.some(item => item.slice(1).toLowerCase() !== input.handle.toLowerCase())) return null;
  const title = typeof parsed.title === "string" ? parsed.title.trim().slice(0, 40) : "";
  const thin = { thin: true as const, analysis, title: title || "没有具体时间", date: null, hour: null, status: null, starts_at: null };
  if (parsed.concrete !== true || typeof parsed.date !== "string" || !dateIsInTweet(input.text, input.occurred_at, parsed.date)) return thin;
  const hour = typeof parsed.hour === "string" && /^(?:[01]\d|2[0-3])$/.test(parsed.hour) && hourIsInTweet(input.text, parsed.hour) ? parsed.hour : null;
  const status = hour && parsed.status === "confirmed" ? "confirmed" as const : "estimated" as const;
  const starts = new Date(Date.parse(`${parsed.date}T${hour ?? "12"}:00:00+08:00`));
  if (!Number.isFinite(starts.getTime())) return thin;
  return { thin: false, analysis, title: title || "已写明时间", date: parsed.date, hour, status, starts_at: starts.toISOString().replace(/\.\d{3}Z$/, "Z") };
}

export async function generateTweetEvent(input: TweetEventInput, env: NodeJS.ProcessEnv = process.env, fetchImpl: FetchLike = fetch): Promise<{ ok: true } & TweetEventReview | { ok: false; message: string }> {
  const loaded = loadAi(env);
  if (!loaded.cfg) return { ok: false, message: unconfiguredMessage(loaded.raw, env) };
  const prompt = tweetEventPrompt(input);
  let content = "";
  if (loaded.cfg.provider === "deepseek") {
    const produced = await deepseekText(loaded.cfg, prompt, fetchImpl);
    if (!produced.ok) return produced;
    content = produced.content;
  } else {
    const binary = [loaded.cfg.codexBin, ...CODEX].find(item => item && existsSync(item));
    if (!binary) return { ok: false, message: "找不到 Codex 命令行。也可在 ai.json 里改用 DeepSeek，并设置 DEEPSEEK_API_KEY。没有写入分析。" };
    const produced = await codexText(binary, prompt);
    if (!produced.ok) return produced;
    content = produced.content;
  }
  const reviewed = reviewTweetEvent(content, input);
  if (!reviewed) return { ok: false, message: "AI 返回无法按这条推文核对，没有写入时间点" };
  return { ok: true, ...reviewed };
}
