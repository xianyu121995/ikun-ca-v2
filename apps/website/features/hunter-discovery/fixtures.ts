import type {DiscoveryDTO,HunterAccountDTO,ProjectFields} from './model';

/** Synthetic UI0 fixtures, used by the isolated demo route only. */
export function demoDiscoveries(): DiscoveryDTO[] {
  const names=['Orbit Finance','LayerGarden','Arc Network','Nexum Labs','Prism Protocol','Flux AI','Anchor Vault','Nova Mesh','Forma','Synapse Garden','Ember Exchange','Vector Zero','Halo Network','Tide Protocol','Pixel Harbor','Open Meridian','Cobalt Labs','Arbor Markets','Glide','Echo Systems','Delta Index','Lumen Node'];
  const bios=['Connecting liquidity across chains. A unified layer for the next generation of DeFi.','A modular execution layer for open applications.','Open infrastructure for autonomous agents and verifiable compute.'];
  return names.map((name,i)=>({discovery_id:`demo-discovery-${i+1}`,project_id:i===0?null:`prj_00000000-0000-4000-8000-${String(i+1).padStart(12,'0')}`,
    project:{name,rating:([null,'S','D','A','B','C'] as const)[i%6],description:bios[i%3],website_url:null,notes:i===0?'重点核实项目资料，canonical ID 尚未注册。':'',category:i%3===0?'DeFi':i%3===1?'基础设施':'AI',progress_stage:'researching',progress_percent:null,token_date:null,token_date_status:'unconfirmed'},
    x_user_id:null,x_handle:`demo_project_${i+1}`,profile_bio:bios[i%3],followers:i===0?null:4200+i*1000,signal_count:2+i%5,
    first_seen_at:null,last_seen_at:null,discovered_at:i===0?null:new Date(Date.parse('2026-10-14T22:00:00Z')-i*3600000).toISOString(),review_state:i===4?'tracking':i%4===0?'reviewed':'pending',monitoring_state:i===4?'accepted':null,revision:1}));
}
export const demoAccounts: HunterAccountDTO[]=[
  {account_id:'demo-account-1',x_handle:'demo_hunter_a',label:'Alpha Research',notes:'仅管理员 DTO 注入展示',enabled:true,baseline_ready:true,connection:'connected',last_signal_at:'2026-10-14T21:40:00Z',revision:1},
  {account_id:'demo-account-2',x_handle:'demo_hunter_b',label:'Signal Lab',notes:'enabled 不代表来源连接正常',enabled:true,baseline_ready:false,connection:'disconnected',last_signal_at:null,revision:1}
];
export function copyProject(project:ProjectFields): ProjectFields {return {...project};}
