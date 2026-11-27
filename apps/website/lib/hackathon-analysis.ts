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
