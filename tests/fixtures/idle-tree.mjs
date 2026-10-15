import { spawn } from 'node:child_process';
import { writeFileSync } from 'node:fs';
const grandchild = spawn(process.execPath, ['-e', "process.on('SIGTERM',()=>{});setInterval(()=>{},1000)"], { stdio: 'ignore' });
writeFileSync(process.argv[2], JSON.stringify({ pid: process.pid, grandchild: grandchild.pid }));
process.on('SIGTERM', () => process.exit(0));
setInterval(() => {}, 1000);
