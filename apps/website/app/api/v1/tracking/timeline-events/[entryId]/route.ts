import {mutateTimeline} from '../shared';
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export async function PATCH(request: Request, context: {params: Promise<{entryId: string}>}) {
  const {entryId} = await context.params;
  return mutateTimeline(request, entryId, 'PATCH');
}
export async function DELETE(request: Request, context: {params: Promise<{entryId: string}>}) {
  const {entryId} = await context.params;
  return mutateTimeline(request, entryId, 'DELETE');
}
