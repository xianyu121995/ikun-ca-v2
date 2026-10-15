import { spawnManaged } from '../../packages/runtime/dist/index.js';
spawnManaged(process.execPath, [process.argv[2], process.argv[3]], { cwd: process.cwd(), env: { PATH: '/usr/bin:/bin' }, graceMs: 250 });
setInterval(() => {}, 1000);
