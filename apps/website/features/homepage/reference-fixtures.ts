import type {ProjectRecordProjection} from './types';
import type {AiTimelineEntry,ProjectMilestone} from './reference-types';

export const DEMO_AS_OF='2026-10-15';
// Fictional inputs adapted from the user-supplied HTML, never canonical IDs or live evidence.
const seeds=[
  ['Prism Labs','S','2026-10-07T05:00:00Z','prism','面向 AI 时代的模块化 Rollup 基础设施。','watching','2026-10-18','代币发行（预计）','重点关注：社区热度高，持续验证进展。'],
  ['Nova Network','A','2026-10-08T01:00:00Z','nova','专注于链上身份与跨应用认证的 L1 公链。','todo','2026-10-22','主网上线','团队背景较强，关注主网上线。'],
  ['Orbit Network','A','2026-10-10T08:00:00Z','orbit','为新兴生态提供全链流动性聚合服务。','participating','2026-11-03','测试网奖励快照','已完成多轮交互，等待快照。'],
  ['Echo Finance','B','2026-10-12T03:00:00Z','echo','面向真实收益场景的 DeFi 协议。','watching','2026-11-12','社区治理投票','经济模型设计合理，团队背景待核实。'],
  ['Float Protocol','B','2026-10-14T06:00:00Z','float','基于 LSD 的收益增强协议，提高资金效率。','researching','2026-11-21','公开路线图','持续关注生态增长。'],
  ['PaperTrade','B','2026-10-15T02:00:00Z','papertrade','链上模拟交易与激励机制。','watching','2026-12-01','积分活动结束','产品体验良好，观察用户留存。'],
  ['SixthSense','S','2026-10-09T03:00:00Z','sense','链上交易数据的智能分析平台。','researching','2026-12-05','测试版更新','密切评估技术落地。'],
  ['Street','B','2026-10-11T12:00:00Z','street','新型 Web3 创作者交易生态。','watching','2026-12-10','新功能开放','社区还在早期。'],
  ['Cobalt Labs','A','2026-10-04T00:00:00Z','cobalt','跨链流动性路由基础设施。','researching','2026-12-12','开发者计划','需要调查审计报告。'],
  ['Vela AI','S','2026-10-06T00:00:00Z','vela','探索加密领域的自动化研究助手。','watching','2026-12-16','产品公测','重点检查数据来源。'],
  ['Delta DAO','A','2026-10-05T04:00:00Z','delta','去中心化治理与激励平台。','researching','2026-12-21','治理提案','观察治理参与度。'],
  ['Amber Finance','B','2026-10-03T08:00:00Z','amber','面向多链的收益聚合产品。','watching','2026-12-26','协议升级','需评估合约风险。'],
] as const;
/** Fixture AI rows inside the next three Beijing days, so the timeline can show them without a live worker. */
export function fixtureAiEntries(now=Date.now()):AiTimelineEntry[]{
  const day=(offset:number)=>new Date(now+offset*86400000+8*3600000).toISOString().slice(0,10);
  return [
    {entry_id:'tle_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa1',project_id:'demo-reference-1',project_name:'Prism Labs',rating:'S',event_type:'tge',title:'TGE 开盘',date:day(1),hour:'20',status:'confirmed',source_url:'https://x.com/prism_labs/status/1866001001',source_tweet_id:'1866001001',confidence:0.94},
    {entry_id:'tle_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb2',project_id:'demo-reference-2',project_name:'Nova Network',rating:'A',event_type:'launch',title:'主网上线',date:day(2),hour:'09',status:'estimated',source_url:'https://x.com/nova_network/status/1866001002',source_tweet_id:'1866001002',confidence:0.88},
  ];
}
export function referenceFixtures():{projects:ProjectRecordProjection[];milestones:ProjectMilestone[]}{
  return {projects:seeds.map((seed,index)=>({project_id:`demo-reference-${index+1}`,name:seed[0],rating:seed[1],description:seed[4],website_url:`https://${seed[3]}.example`,progress_stage:seed[5],progress_percent:null,notes:seed[8],category:null,home_membership:'active',discovered_at:seed[2],revision:1,created_at:'2026-10-15T00:00:00Z',updated_at:'2026-10-15T00:00:00Z',token_date:index===0?seed[6]:null,token_date_status:index===0?'estimated':'unconfirmed'})),milestones:seeds.map((seed,index)=>({project_id:`demo-reference-${index+1}`,date:seed[6],hour:String([14,9,16,11,10,15,14,20,8,13,12,16][index]).padStart(2,'0'),title:seed[7],status:'estimated'}))};
}
