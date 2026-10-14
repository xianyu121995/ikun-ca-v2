import type {Metadata} from 'next';
import {notFound} from 'next/navigation';
import HomepagePreview from '../../../components/homepage-ui/preview';
export const dynamic='force-dynamic';
export const metadata:Metadata={title:'ikun.ca v2 · 主页 UI 演示原型',robots:{index:false,follow:false}};
export default function HomepagePreviewPage(){
  // Explicit opt-in. The prototype cannot become a silent production data fallback.
  if(process.env.IKUN_HOMEPAGE_UI_PREVIEW!=='1'||process.env.IKUN_ENV==='production')notFound();
  return <HomepagePreview/>;
}
