// Synthetic readiness fixture. It contains no Projects CRUD, business DB or provider IO.
import { createServer } from 'node:http';
import { chmodSync, writeFileSync } from 'node:fs';
const server = createServer((req, res) => {
  if (req.headers.authorization !== `Bearer ${process.env.IKUN_IPC_TOKEN}`) { res.writeHead(401); res.end(); return; }
  if (process.argv.includes('--stall')) return;
  if (req.url !== '/health/ready' || req.method !== 'GET') { res.writeHead(404); res.end(); return; }
  res.setHeader('content-type', 'application/json');
  res.end(JSON.stringify({ data: { service: 'projects', writer: 'projects-domain', ready: true, build_sha: process.env.IKUN_BUILD_SHA } }));
});
server.listen(process.env.IKUN_IPC_SOCKET, () => {
  chmodSync(process.env.IKUN_IPC_SOCKET, 0o600);
  const stateIndex = process.argv.indexOf('--state-file');
  if (stateIndex >= 0) writeFileSync(process.argv[stateIndex + 1], JSON.stringify({ pid: process.pid, socket: process.env.IKUN_IPC_SOCKET }), { mode: 0o600 });
});
process.once('SIGTERM', () => { server.closeAllConnections(); server.close(); });
