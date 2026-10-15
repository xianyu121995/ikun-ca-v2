import type {ProjectRecord} from './project';
// Entirely fictional UI fixtures. Names, grades, dates and progress are NOT research findings.
const rows: [string,string,string,string,string,number,string,string][] = [
 ['Orbit Layer','S','2026-10-12','基础设施','进行中',72,'模块化执行层，探索应用链与可组合基础设施。','完成测试网任务；下一步验证跨链流程。'],
 ['Velum Finance','S','2026-10-10','DeFi','进行中',58,'面向稳定币的流动性协议与收益管理工具。','已整理交互步骤，周五复查任务更新。'],
 ['Nexa Compute','A','2026-10-13','AI × Crypto','准备中',35,'去中心化算力协作网络，提供可验证推理服务。','等待测试网开放；先准备节点环境。'],
 ['Tide Protocol','A','2026-10-08','DeFi','进行中',65,'跨链流动性路由与聚合交易基础设施。','本周重点：测试跨链到账与失败恢复。'],
 ['Prism Social','B','2026-10-11','社交','研究中',18,'开放社交图谱，让身份与内容在应用间流转。','核实产品体验，再决定是否持续参与。'],
 ['Ember World','A','2026-10-06','游戏','进行中',81,'链上策略游戏与可组合数字资产生态。','第二阶段已完成；记录下一轮任务。'],
 ['Lattice Network','S','2026-10-04','基础设施','进行中',46,'轻量级数据可用性网络与验证者工具。','节点已配置（演示）；检查任务清单。'],
 ['Morrow Labs','B','2026-10-09','AI × Crypto','研究中',22,'面向智能体的链上身份、协作与支付组件。','整理文档与产品定位，暂不追加任务。'],
 ['Flux Garden','A','2026-10-02','DeFi','已完成',100,'实验性资产管理工具与透明策略展示。','当前任务完成，等待新一季活动信息。'],
 ['Signal Mesh','B','2026-10-07','基础设施','准备中',30,'开放数据索引与实时事件分发网络。','准备部署清单；补充性能测试计划。'],
 ['Cobalt Play','C','2026-09-29','游戏','已暂停',40,'面向游戏开发者的资产和玩家协作工具。','暂缓参与；保留已有研究记录。'],
 ['Echo Identity','待定','2026-10-14','社交','研究中',10,'跨应用身份与凭证管理的概念产品。','新发现，评分待补充。'],
 ['Nova Bridge','B','2026-09-26','基础设施','已暂停',25,'用于演示移除与恢复操作的跨链项目。','已从主页移除，资料仍保留。'],
 ['Arcadia Studio','C','2026-09-23','游戏','已暂停',15,'用于演示移除列表的游戏基础设施项目。','暂不继续，必要时可重新加入主页。']
];
export function demoProjects():ProjectRecord[] {
  return rows.map((r,i)=>({id:`demo-${i+1}`,name:r[0],grade:r[1] as ProjectRecord['grade'],discoveredOn:r[2],category:r[3],stage:r[4] as ProjectRecord['stage'],progress:r[5],description:r[6],notes:r[7],website:`https://${r[0].toLowerCase().replaceAll(' ','-')}.example`,membership:i<12?'active':'removed',isDemo:true}));
}
