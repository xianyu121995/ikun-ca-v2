/** Test fixture deliberately outside Proxy matcher; never a production receiving patch. */
import { redirect } from 'next/navigation';
import { Panel,Button } from '@ikun/ui';
import '@ikun/ui/styles.css';
import { requireAuthPage,requireSuperadminAction } from '../../../../lib/auth';
export const dynamic='force-dynamic';
async function probe(form:FormData){'use server';let status=200;
  try {await requireSuperadminAction(String(form.get('csrf_token')??''));}
  catch(error){status=typeof error==='object'&&error&&'status' in error?Number(error.status):500;}
  redirect('/internal/v1/action-probe?result='+status);
}
export default async function Page(){const session=await requireAuthPage('/auth/password');return <Panel title="独立 Server Action 验证"><form action={probe}><input type="hidden" name="csrf_token" value={session.csrf_token} /><Button type="submit">执行鉴权测试</Button></form></Panel>;}
