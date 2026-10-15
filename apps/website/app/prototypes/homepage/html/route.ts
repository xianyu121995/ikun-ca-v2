import {readFile} from 'node:fs/promises';
import {join} from 'node:path';
export const dynamic='force-dynamic';
export async function GET(){
  if(process.env.IKUN_HOMEPAGE_UI_PREVIEW!=='1'||process.env.IKUN_ENV==='production')return new Response(null,{status:404});
  const html=await readFile(join(process.cwd(),'components/homepage-ui/prototype/ikun-home-ui-hourly-date-filter.html'),'utf8');
  return new Response(html,{headers:{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store','X-Robots-Tag':'noindex, nofollow'}});
}
