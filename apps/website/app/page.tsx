export default function Home() {
  return <main>
    <p className="eyebrow">IKUN.CA / V2</p>
    <h1>全新重建，基础已就位。</h1>
    <p className="intro">网站、猎手服务和跟踪服务独立运行。当前只提供工程基础，业务模块尚未接入。</p>
    <div className="services">
      <article><span>01</span><h2>网站</h2><p>Next.js · 项目数据与独立认证存储</p><code>127.0.0.1:3100</code></article>
      <article><span>02</span><h2>hunter-worker</h2><p>独立进程 · hunter.db</p><code>127.0.0.1:3111</code></article>
      <article><span>03</span><h2>tracking-worker</h2><p>独立进程 · tracking.db</p><code>127.0.0.1:3112</code></article>
    </div>
    <p className="note">开发入口：先阅读仓库中的 AGENTS.md 和 docs/HANDOFF.md。服务地址以本地配置为准。</p>
  </main>;
}
