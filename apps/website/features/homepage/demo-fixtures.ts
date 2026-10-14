import type {ProjectRecordProjection} from './types';
// Explicitly fictional UI inputs. These demo-* keys are never canonical IDs.
export function phase2Fixtures():ProjectRecordProjection[]{
  const names=['Orbit Layer','Velum Finance','Nexa Compute','Tide Protocol','Prism Social','Ember World','Lattice Network','Morrow Labs','Flux Garden','Echo Identity','Nova Bridge','Arcadia Studio'];
  const ratings=['S','S','A','A','B','B','C','D',null,null,'D','C'] as const;
  const stages=['participating','watching','todo','researching','paused','participating','watching','researching','completed','todo','paused','researching'] as const;
  return names.map((name,index)=>({project_id:`demo-phase2-${index+1}`,name,rating:ratings[index],
    description:['模块化执行层与应用基础设施，供表格展示测试。','跨链流动性与资产研究，供界面交互演示。','面向开放算力和协作的概念项目。'][index%3],
    notes:['检查任务清单，核对当前阶段。','保留研究记录，补充下一步行动。','未知百分比保持空值，等待可靠信息。'][index%3],
    website_url:index===9?null:`https://${name.toLowerCase().replaceAll(' ','-')}.example`,category:index%2?'DeFi':'基础设施',
    progress_stage:stages[index],progress_percent:[72,58,null,20,40,81,46,0,100,null,25,15][index],
    token_date:index===0?'2026-12-01':index===1?'2026-11-20':null,token_date_status:index===0?'estimated':index===1?'confirmed':'unconfirmed',
    home_membership:index===10?'hidden':index===11?'removed':'active',
    discovered_at:index%3===2?null:`2026-10-${String(index+1).padStart(2,'0')}T02:30:00.000Z`,
    revision:1,created_at:'2026-10-15T00:00:00.000Z',updated_at:'2026-10-15T00:00:00.000Z'}));
}
