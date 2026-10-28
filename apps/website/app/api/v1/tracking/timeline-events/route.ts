import {listTimeline} from './shared';
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export function GET(request: Request) { return listTimeline(request); }
