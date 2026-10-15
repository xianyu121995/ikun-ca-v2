import {NextRequest} from 'next/server';
import {projectsAuth} from './lib/projects';
export function proxy(request:NextRequest){
  if(['/health/live','/health/ready'].includes(request.nextUrl.pathname))return;
  // Internal direction-authenticated route has its own exact handler guard.
  if(/^\/internal\/v1\/(?:ingest\/(?:hunter|tracking)|receipts\/(?:hunter|tracking)\/evt_[a-f0-9-]{36})$/.test(request.nextUrl.pathname))return;
  return projectsAuth().gate(request)??undefined;
}
export const config={matcher:['/((?!_next/static|_next/image|favicon.ico).*)']};
