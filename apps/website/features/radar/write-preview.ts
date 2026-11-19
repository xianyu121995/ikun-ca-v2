import {mkdirSync, writeFileSync} from 'node:fs';
import {presentRadar, type RadarPageModel} from '../../lib/radar-view.ts';
import {SAMPLE_WIRE} from './sample.ts';

function esc(value: string) {
  return value.replace(/[&<>"']/g, char => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[char]!));
}

function render(model: RadarPageModel) {
  const level: Record<string, string> = {info: '信息', warn: '注意', crit: '高危'};
  const cards = model.cards.map(card => `<article class="radar-card"><header><h2>${esc(card.project)}</h2><span class="radar-pill" data-state="${esc(card.state)}">${esc(card.label)}</span></header><div class="radar-kind">${esc(card.kind)}</div><p>${esc(card.summary)}</p><p class="radar-limit">${esc(card.limit)}</p></article>`).join('');
  const events = model.events.map(event => `<article class="radar-event"><div><span class="radar-pill" data-state="${event.level === 'crit' ? 'crit' : event.level === 'warn' ? 'warn' : 'configured'}">${level[event.level]}</span><div class="radar-meta">${esc(event.project)} · ${esc(event.kind === 'baseline' ? '基线' : event.motion || event.kind)}</div></div><div><strong>${esc(event.title)}</strong><time>${esc(event.time)}</time>${event.detail ? `<p class="radar-limit">${esc(event.detail)}</p>` : ''}${event.href ? `<a href="${esc(event.href)}" rel="noopener noreferrer">查看来源</a>` : ''}</div></article>`).join('');
  return `<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>模式雷达预览（示例数据）</title><style>
body{margin:0;background:#0b0e12;color:#e8eef5;font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
.wrap{max-width:1120px;margin:0 auto;padding:20px 16px 40px}
.radar-banner{margin:0 0 14px;padding:10px 12px;border:1px solid #8a6a22;background:#2a220c;color:#f3d48a;border-radius:8px}
.radar-head{display:flex;flex-wrap:wrap;justify-content:space-between;gap:8px 16px;align-items:flex-end;margin-bottom:14px}
.radar-head h1{margin:0;font-size:22px}.radar-head p{margin:4px 0 0;color:#a6b4c5}
.radar-status{display:flex;gap:8px;align-items:center;color:#a6b4c5;font-size:12px}
.radar-pill{border:1px solid #293544;border-radius:999px;padding:3px 8px;background:#111820}
.radar-pill[data-state="live"],.radar-pill[data-state="ok"],.radar-pill[data-state="configured"]{color:#8ce4c2;border-color:#1d6b52}
.radar-pill[data-state="stale"],.radar-pill[data-state="partial"],.radar-pill[data-state="warn"]{color:#f3d48a;border-color:#8a6a22}
.radar-pill[data-state="crit"],.radar-pill[data-state="disconnected"]{color:#ff9caa;border-color:#7a3140}
.radar-pill[data-state="unconfigured"],.radar-pill[data-state="disabled"]{color:#a6b4c5}
.radar-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}
.radar-card{background:#111820;border:1px solid #293544;border-radius:10px;padding:12px 14px;min-width:0}
.radar-card header{display:flex;justify-content:space-between;gap:8px;align-items:center}
.radar-card h2{margin:0;font-size:14px}.radar-kind,.radar-limit,.radar-meta{color:#a6b4c5}
.radar-card p,.radar-event strong{overflow-wrap:anywhere}
.radar-list{margin-top:18px;display:grid;gap:8px}
.radar-event{display:grid;grid-template-columns:minmax(128px,168px) minmax(0,1fr);gap:8px 12px;background:#111820;border:1px solid #293544;border-radius:10px;padding:10px 12px}
.radar-event a{color:#8ce4c2}
.radar-footnote{margin-top:16px;color:#a6b4c5;font-size:12px}
@media(max-width:720px){.radar-event,.radar-grid{grid-template-columns:1fr}}
</style></head><body><main class="wrap"><p class="radar-banner">示例数据，不是生产监控。这是可打开的静态预览，没有连接服务器或链节点。</p>
<div class="radar-head"><div><h1>FLAP / four.meme 模式雷达</h1><p>只读监控新模式痕迹。不买卖、不签名。</p></div>
<div class="radar-status"><span class="radar-pill" data-state="${esc(model.bridge)}">${esc(model.bridgeLabel)}</span><span>快照 ${esc(model.generatedAt)}</span></div></div>
<div class="radar-grid">${cards}</div><div class="radar-list"><h2>最近变化</h2>${events}</div>
<p class="radar-footnote">${esc(model.footnote)}</p></main></body></html>`;
}

const model = presentRadar(SAMPLE_WIRE, 1763510400);
if (!model?.sample) throw new Error('preview must stay marked as sample');
const html = render(model);
mkdirSync('/opt/cursor/artifacts', {recursive: true});
writeFileSync('/opt/cursor/artifacts/radar-preview.html', html);
writeFileSync(new URL('../../../../docs/radar/preview.html', import.meta.url), html);
console.log('wrote preview', model.cards.map(card => `${card.id}:${card.state}`).join(' '));
