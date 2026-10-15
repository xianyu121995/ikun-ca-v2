import { Panel } from '@ikun/ui';
import { requireAuthPage } from '../../lib/auth';
import { AuthShell } from '../../components/auth/shell';
export const dynamic='force-dynamic';
export default async function Page(){const session=await requireAuthPage('/hunter');return <AuthShell pathname="/hunter" username={session.username}><Panel title="认证接入验收">本页仅验证访问边界，没有业务数据。</Panel></AuthShell>;}
