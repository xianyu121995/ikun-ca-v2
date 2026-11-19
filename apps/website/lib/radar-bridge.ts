import {radarBridgeConfig, unavailableRadar, presentRadar, type RadarPageModel} from './radar-view';

function failure(id: string, status: number, code: string, message: string) {
  return Response.json({error: {code, message, retryable: status === 503}, request_id: id}, {status, headers: {'cache-control': 'no-store', 'x-request-id': id}});
}

export async function radarSnapshot(requestId: string, nowSec = Math.floor(Date.now() / 1000)): Promise<Response> {
  const configured = radarBridgeConfig(process.env);
  if (!configured) {
    return Response.json({data: unavailableRadar('not_configured'), request_id: requestId}, {headers: {'cache-control': 'no-store', 'x-request-id': requestId}});
  }
  try {
    const response = await fetch(new URL('/v1/snapshot', configured.origin), {
      headers: {authorization: 'Bearer ' + configured.token, accept: 'application/json'},
      cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(4000),
    });
    if (response.status === 401) return failure(requestId, 503, 'RADAR_NOT_CONFIGURED', '雷达桥接认证未通过');
    if (!response.ok) return Response.json({data: unavailableRadar('disconnected'), request_id: requestId}, {headers: {'cache-control': 'no-store', 'x-request-id': requestId}});
    const text = await response.text();
    if (text.length > 200_000) return Response.json({data: unavailableRadar('unavailable'), request_id: requestId}, {headers: {'cache-control': 'no-store', 'x-request-id': requestId}});
    const model = presentRadar(JSON.parse(text), nowSec);
    if (!model) return Response.json({data: unavailableRadar('unavailable'), request_id: requestId}, {headers: {'cache-control': 'no-store', 'x-request-id': requestId}});
    return Response.json({data: model, request_id: requestId}, {headers: {'cache-control': 'no-store', 'x-request-id': requestId}});
  } catch {
    return Response.json({data: unavailableRadar('disconnected'), request_id: requestId}, {headers: {'cache-control': 'no-store', 'x-request-id': requestId}});
  }
}

export async function radarEvents(request: Request, requestId: string): Promise<Response> {
  const configured = radarBridgeConfig(process.env);
  if (!configured) return failure(requestId, 503, 'RADAR_NOT_CONFIGURED', '雷达桥接未配置');
  const cursor = request.headers.get('last-event-id');
  if (cursor && !/^\d{1,15}$/.test(cursor)) return failure(requestId, 422, 'VALIDATION_ERROR', '雷达事件游标无效');
  try {
    const headers: Record<string, string> = {authorization: 'Bearer ' + configured.token, accept: 'text/event-stream'};
    if (cursor) headers['last-event-id'] = cursor;
    const upstream = await fetch(new URL('/v1/events', configured.origin), {
      headers, cache: 'no-store', redirect: 'error', signal: request.signal,
    });
    if (upstream.status === 401) return failure(requestId, 503, 'RADAR_NOT_CONFIGURED', '雷达桥接认证未通过');
    if (!upstream.ok || !upstream.body) return failure(requestId, 503, 'RADAR_DISCONNECTED', '雷达服务未连接');
    return new Response(upstream.body, {status: 200, headers: {
      'content-type': 'text/event-stream; charset=utf-8', 'cache-control': 'no-store', 'x-accel-buffering': 'no', 'x-request-id': requestId,
    }});
  } catch {
    return failure(requestId, 503, 'RADAR_DISCONNECTED', '雷达服务未连接');
  }
}

export type {RadarPageModel};
