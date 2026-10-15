import { redirect } from 'next/navigation';
import { requireAuthPage } from '../../lib/auth';
export const runtime='nodejs';
export const dynamic='force-dynamic';
export default async function Account(){await requireAuthPage('/auth');redirect('/auth/password');}
