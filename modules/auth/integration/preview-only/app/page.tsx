import { redirect } from 'next/navigation';
import { Panel, Button } from '@ikun/ui';
import { requireAuthPage, requireSuperadminAction } from '../lib/auth';
import { AuthShell } from '../components/auth/shell';
export const dynamic='force-dynamic';
async function write(form:FormData){'use server';await requireSuperadminAction(String(form.get('csrf_token')??''));redirect('/?action=passed');}
export default async function Page(){const session=await requireAuthPage('/');return <AuthShell pathname="/" username={session.username}><Panel title="认证接入验收">本页仅验证访问边界，没有业务数据。<form action={write}><input type="hidden" name="csrf_token" value={session.csrf_token} /><Button type="submit">验证服务端写入权限</Button></form></Panel></AuthShell>;}
