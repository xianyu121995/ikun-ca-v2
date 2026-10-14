import { execFileSync } from 'node:child_process';

const tracked = execFileSync('git', ['ls-files', '-z'], { encoding: 'utf8' }).split('\0').filter(Boolean);
const forbidden = tracked.filter(path =>
  /(^|\/)(node_modules|var|data|logs|backups|secrets|\.tools|\.next|dist)(\/|$)/.test(path)
  || /^runtime(\/|$)/.test(path)
  || /\.(db|sqlite3?|pem|key|p12|pfx|keystore)([-.]|$)/i.test(path)
  || /(^|\/)\.env(\.|$)/.test(path) && !/\.env\.(production\.)?example$/.test(path)
  || /(^|\/)(credentials|cookies|storage-state).*\.json$/i.test(path));
for (const path of tracked) {
  if (path === 'pnpm-lock.yaml') continue;
  const text = execFileSync('git', ['show', `:${path}`], { encoding: 'utf8', maxBuffer: 4 * 1024 * 1024 });
  if (/-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/.test(text) && !path.endsWith('check-git.mjs')) forbidden.push(path);
  if (/\b(?:sk-proj-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b/.test(text)) forbidden.push(path);
}
if (forbidden.length) {
  process.stderr.write(`Unsafe tracked paths: ${[...new Set(forbidden)].join(', ')}\n`);
  process.exitCode = 1;
} else process.stdout.write(`Git hygiene OK: ${tracked.length} tracked files\n`);
