'use server';
import { requireSuperadminAction } from '../../lib/auth';
export async function authorizeTrackingAction(csrf: string) { await requireSuperadminAction(csrf); return { authorized: true }; }
