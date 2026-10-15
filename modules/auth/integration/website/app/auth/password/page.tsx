import { PasswordForm } from '../../../components/auth/forms';
import { AuthShell } from '../../../components/auth/shell';
import { requireAuthPage } from '../../../lib/auth';
export const runtime='nodejs';
export const dynamic='force-dynamic';
export default async function PasswordPage(){const session=await requireAuthPage('/auth/password');return <AuthShell pathname="/auth/password" username={session.username}><PasswordForm forced={session.must_change_password} /></AuthShell>;}
