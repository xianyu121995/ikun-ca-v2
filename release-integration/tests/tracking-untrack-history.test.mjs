import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {build} from '../../packages/ui/node_modules/esbuild/lib/main.js';

test('removed account metadata renders historical tweets without appearing in management',async()=>{
 const root=fileURLToPath(new URL('../../',import.meta.url));
 const result=await build({stdin:{contents:`
 import {createElement} from 'react';
 import {renderToStaticMarkup} from 'react-dom/server';
 import {TrackingPage} from './apps/website/features/tracking/final/tracking-page';
 const account={ui_key:'removed-sub',name:'历史保留测试',handle:'fixture_only',note:'测试',grade:'A',status:'stopped',avatar:'测'};
 const post={ui_key:'old-post',account_key:'removed-sub',body:'旧推文继续显示',published_at:null,received_at:'2026-10-19T00:00:00Z',tweet_kind:'original',important:null,comments:'未知',reposts:'未知',likes:'未知',media:null,media_available:false};
 export const html=renderToStaticMarkup(createElement(TrackingPage,{mode:'live',accounts:[],posts:[post],onAdd:async()=>{},onRemove:async()=>{},live:{historyAccounts:[account],connected:true,accountMenu:null,canManage:false,refresh:()=>{},onOpenPost:()=>{},manageActions:()=>null,addForm:()=>null,pagination:null,server:{filters:{query:'',grade:'all',hours:'all',important:false},onFiltersChange:()=>{},matchedTotal:1,subscriptionCounts:{S:0,A:0,B:0}}}}));
 `,resolveDir:root,loader:'tsx'},bundle:true,platform:'node',format:'cjs',jsx:'automatic',alias:{react:root+'packages/ui/node_modules/react','react-dom':root+'packages/ui/node_modules/react-dom'},plugins:[{name:'test-css',setup(b){b.onLoad({filter:/\.css$/},()=>({contents:'export default {}',loader:'js'}));}}],write:false,logLevel:'silent'});
 const module={exports:{}};
 new Function('require','module','exports',result.outputFiles[0].text)(createRequire(import.meta.url),module,module.exports);
 assert.match(module.exports.html,/旧推文继续显示/);
 assert.match(module.exports.html,/历史保留测试/);
 assert.match(module.exports.html,/监控账号总数 0/);
});
