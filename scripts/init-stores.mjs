import { openStores, closeStores } from '../packages/runtime/dist/index.js';
const [service] = process.argv.slice(2);
if (!['website', 'hunter', 'tracking'].includes(service) || !process.env.DATA_ROOT) throw new Error('Usage: DATA_ROOT=ABS node scripts/init-stores.mjs website|hunter|tracking');
const options = service === 'website' && process.argv.includes('--auth-only') ? { names: ['auth'] } : {};
closeStores(openStores(service, process.env.DATA_ROOT, options));
