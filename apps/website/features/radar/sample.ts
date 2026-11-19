/** Fixed example feed. It is not a live monitor and must stay marked sample. */
export const SAMPLE_WIRE = {
  version: '0.2.0-ikun',
  generated_at: 1763510400,
  bridge: 'ok' as const,
  sample: true,
  chains: {
    bsc: {mode: 'configured', link: 'live', detail: '最近区块 12345678（示例）', head: '12345678', head_ts: 1763510400},
    fourmeme: {mode: 'unconfigured', link: 'unconfigured', detail: '空配置，已禁用', head: '', head_ts: 0},
  },
  probes: {
    docs: {ok_ts: 1763510300, error: ''},
    github: {ok_ts: 1763500000, error: ''},
    onchain: {ok_ts: 1763510400, error: ''},
  },
  coverage: [
    {id: 'flap-docs', project: 'FLAP', kind: '文档', state: 'configured', summary: 'docs.flap.sh 侧边栏。示例里显示为已检查。', limit: '公开文档目录，不是成交。'},
    {id: 'flap-github', project: 'FLAP', kind: '仓库', state: 'unconfigured', summary: '没有配置 FLAP 源代码仓库。', limit: '不能用 four.meme 仓库代替。'},
    {id: 'flap-identity', project: 'FLAP', kind: '合约身份', state: 'configured', summary: '附件中的 Portal / Vault / Dock。WSS newHeads 推动读取。', limit: '地址未经本仓库重新核对为官方全集。'},
    {id: 'flap-events', project: 'FLAP', kind: '链上事件', state: 'configured', summary: '示例：extensionID / migratorType / tokenVersion。', limit: '只订阅已知地址。全新地址不在范围内。'},
    {id: 'four-docs', project: 'four.meme', kind: '文档', state: 'configured', summary: 'GitBook llms.txt。', limit: '文档变化不等于链上事件已覆盖。'},
    {id: 'four-github', project: 'four.meme', kind: '仓库', state: 'configured', summary: 'four-meme-community 的两个文档仓库。', limit: '社区文档树，不是完整协议。'},
    {id: 'four-identity', project: 'four.meme', kind: '合约身份', state: 'partial', summary: '示例里只标出部分 TokenManager 身份，不是全集。', limit: '三个名字含 fourmeme 的地址只做字节码/实现槽。'},
    {id: 'four-events', project: 'four.meme', kind: '链上事件', state: 'configured', summary: '这条自述会被页面改写成未配置。', limit: '即使上游误写已配置，页面也不宣称完整。'},
  ],
  events: [
    {id: 4, ts: 1763510400, source: 'onchain:bsc', key: 'enum:TokenExtensionEnabled:extensionID=0x77', kind: 'new', level: 'crit', title: 'bsc TokenExtensionEnabled 出现新取值 extensionID=0x77（未登记）', detail: '示例事件。合约 0xportal。', url: 'https://bscscan.com/tx/0x' + 'ab'.repeat(32)},
    {id: 3, ts: 1763510000, source: 'github:four-meme-community/openfour-docs', key: 'path:contracts/token/NewMode.sol', kind: 'new', level: 'crit', title: 'four-meme-community/openfour-docs 新增文件 contracts/token/NewMode.sol', detail: '示例：新合约文件。', url: 'https://github.com/four-meme-community/openfour-docs'},
    {id: 2, ts: 1763509800, source: 'docs:flap', key: 'https://docs.flap.sh/en/flap/old', kind: 'gone', level: 'warn', title: '文档页面删除：旧玩法说明 <script>', detail: '示例删除。javascript:alert(1) 不应成为链接。', url: 'javascript:alert(1)'},
    {id: 1, ts: 1763509000, source: 'docs:fourmeme', key: 'baseline', kind: 'baseline', level: 'info', title: '已建立基线：fourmeme（示例，不推送）', detail: '首次只建基线。', url: 'https://evil.example/phish'},
  ],
  latest_event_id: 4,
};
