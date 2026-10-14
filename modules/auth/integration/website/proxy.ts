import { NextResponse, type NextRequest } from "next/server";
import { gate } from "../../modules/auth/dist/src/server.js";

export function proxy(request: NextRequest) {
  const blocked=gate(request);
  if (blocked) return blocked;
  const response=NextResponse.next();
  response.headers.set("cache-control","no-store, private");
  return response;
}
export const config={matcher:["/((?!_next/static/|_next/webpack-hmr$|favicon\\.ico$|health/(?:live|ready)$|internal/v1(?:/|$)).*)"]};
