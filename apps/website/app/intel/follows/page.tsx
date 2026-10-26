import { redirect } from 'next/navigation';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

/** Old third tab. The follow log now lives under 创始人关注的项目. */
export default function IntelFollowsRedirect() {
  redirect('/intel');
}
