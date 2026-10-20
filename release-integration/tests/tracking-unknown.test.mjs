import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {build} from '../../packages/ui/node_modules/esbuild/lib/main.js';

test('live unknown posts remain visible with a type badge and normal actions',async()=>{
 const root=fileURLToPath(new URL('../../',import.meta.url));
 const result=await build({stdin:{contents:`
 import {createElement} from 'react';
 import {renderToStaticMarkup} from 'react-dom/server';
 import {TrackingPage} from './apps/website/features/tracking/final/tracking-page';
 import {selectPosts,emptyFilters} from './apps/website/features/tracking/final/model';
 const account={ui_key:'fixture-sub',name:'未知类型测试',handle:'fixture_only',note:'测试',grade:'A',status:'running',avatar:'测'};
 const posts=['unknown','original'].map((kind,i)=>({ui_key:'fixture-'+i,account_key:account.ui_key,body:'仍然显示 '+kind,published_at:null,received_at:'2026-10-20T00:00:00Z',tweet_kind:kind,important:null,comments:'未知',reposts:'未知',likes:'未知',media:null,media_available:false}));
 export const selected=selectPosts([account],posts,emptyFilters,Date.now()).map(p=>p.tweet_kind);
 export const html=renderToStaticMarkup(createElement(TrackingPage,{mode:'live',accounts:[account],posts,live:{historyAccounts:[account],connected:true,accountMenu:null,canManage:false,refresh:()=>{},onOpenPost:()=>{},manageActions:()=>null,addForm:()=>null,pagination:null,server:{filters:emptyFilters,onFiltersChange:()=>{},matchedTotal:2,subscriptionCounts:{S:0,A:1,B:0}}}}));
 `,resolveDir:root,loader:'tsx'},bundle:true,platform:'node',format:'cjs',jsx:'automatic',alias:{react:root+'packages/ui/node_modules/react','react-dom':root+'packages/ui/node_modules/react-dom'},plugins:[{name:'test-css',setup(b){b.onLoad({filter:/\.css$/},()=>({contents:'export default {}',loader:'js'}));}}],write:false,logLevel:'silent'});
 const module={exports:{}};
 new Function('require','module','exports',result.outputFiles[0].text)(createRequire(import.meta.url),module,module.exports);
 assert.deepEqual(module.exports.selected,['unknown','original']);
 assert.match(module.exports.html,/仍然显示 unknown/);
 assert.match(module.exports.html,/仍然显示 original/);
 assert.equal((module.exports.html.match(/类型未知/g)||[]).length,1);
 assert.equal((module.exports.html.match(/打开 X 原文/g)||[]).length,2);
});
