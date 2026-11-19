import type {RadarPageModel} from '../../lib/radar-view';
import './radar.css';

const LEVEL: Record<string, string> = {info: '信息', warn: '注意', crit: '高危'};

export function RadarBoard({model}: {model: RadarPageModel}) {
  return <section className="radar-page">
    {model.sample && <p className="radar-banner" role="status">示例数据，不是生产监控。数字、区块和事件都是写死的预览，不会随着链上变化更新。</p>}
    <div className="radar-head">
      <div>
        <h1>FLAP / four.meme 模式雷达</h1>
        <p>只读监控新模式痕迹：文档、仓库、合约身份、链上新取值。不买卖、不签名。</p>
      </div>
      <div className="radar-status">
        <span className="radar-pill" data-state={model.bridge}>{model.bridgeLabel}</span>
        {model.generatedAt && <span>快照 {model.generatedAt}</span>}
      </div>
    </div>
    <div className="radar-grid">
      {model.cards.map(card => <article className="radar-card" key={card.id}>
        <header>
          <h2>{card.project}</h2>
          <span className="radar-pill" data-state={card.state}>{card.label}</span>
        </header>
        <div className="radar-kind">{card.kind}</div>
        <p>{card.summary}</p>
        <p className="radar-limit">{card.limit}</p>
      </article>)}
    </div>
    <div className="radar-list">
      <h2>最近变化</h2>
      {model.events.length === 0 ? <p className="radar-limit">还没有新的变化。基线建立之前不会把历史记录推成告警。</p> : model.events.map(event => <article className="radar-event" key={event.id}>
        <div>
          <span className="radar-pill" data-state={event.level === 'crit' ? 'crit' : event.level === 'warn' ? 'warn' : 'configured'}>{LEVEL[event.level]}</span>
          <div className="radar-meta">{event.project} · {event.kind === 'baseline' ? '基线' : event.motion || event.kind}</div>
        </div>
        <div>
          <strong>{event.title}</strong>
          <time dateTime={new Date(event.ts * 1000).toISOString()}>{event.time}</time>
          {event.detail && <p className="radar-limit">{event.detail}</p>}
          {event.href && <a href={event.href} target="_blank" rel="noopener noreferrer">查看来源</a>}
        </div>
      </article>)}
    </div>
    <p className="radar-footnote">{model.footnote}</p>
  </section>;
}
