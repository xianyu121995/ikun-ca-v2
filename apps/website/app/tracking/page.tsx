import {Panel} from '@ikun/ui';
import {AuthShell} from '../../components/auth/shell';
import {requireAuthPage} from '../../lib/auth';
export const dynamic='force-dynamic';
export default async function Page(){const account=await requireAuthPage('/tracking');return <AuthShell pathname="/tracking" username={account.username}><Panel title="猎手项目追踪"><p>未接入。此测试站当前提供登录、本人改密和主页项目管理。</p></Panel></AuthShell>;}
