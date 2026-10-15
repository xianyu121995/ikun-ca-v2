#!/usr/bin/env python3
"""Approved C0-lite root wiring; domain/public component files remain untouched."""
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
package = json.loads((ROOT / 'package.json').read_text())
package['scripts'].update({
    'build:shared': 'pnpm --filter @ikun/contracts build && pnpm --filter @ikun/runtime build && pnpm --filter @ikun/ui build',
    'build:auth': 'pnpm exec tsc -p modules/auth/tsconfig.json',
    'build': 'pnpm build:shared && pnpm build:auth && pnpm --filter @ikun/website build',
    'typecheck': 'pnpm --filter @ikun/contracts typecheck && pnpm --filter @ikun/runtime typecheck && pnpm --filter @ikun/ui typecheck && pnpm build:auth && pnpm --filter @ikun/website typecheck',
    'test:auth': 'node --test modules/auth/tests/*.test.mjs',
    'start:website': 'node scripts/start-c0-lite.mjs',
})
(ROOT / 'package.json').write_text(json.dumps(package, indent=2) + '\n')
website = json.loads((ROOT / 'apps/website/package.json').read_text())
website['dependencies']['@ikun/ui'] = 'workspace:*'
(ROOT / 'apps/website/package.json').write_text(json.dumps(website, indent=2) + '\n')
shutil.copyfile(ROOT / 'config/b0/pnpm-ui-lock.yaml', ROOT / 'pnpm-lock.yaml')
tsconfig = json.loads((ROOT / 'apps/website/tsconfig.json').read_text())
tsconfig['include'] = ['next-env.d.ts', 'app/**/*.ts', 'app/**/*.tsx', 'lib/**/*.ts', 'components/auth/**/*.tsx',
                       'components/projects-home.tsx', 'components/homepage-ui/reference-homepage.tsx',
                       'components/homepage-ui/reference-editor.tsx', 'components/homepage-ui/shared-dialog.tsx',
                       'features/homepage/types.ts', 'features/homepage/reference-types.ts',
                       'features/homepage/reference-model.ts', 'features/homepage/view-model.ts',
                       '.next/types/**/*.ts', '.next/dev/types/**/*.ts']
(ROOT / 'apps/website/tsconfig.json').write_text(json.dumps(tsconfig, indent=2) + '\n')
for name, title in [('hunter', '猎手监控'), ('tracking', '猎手项目监控')]:
    path = ROOT / f'apps/website/app/{name}/page.tsx'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("import {Panel} from '@ikun/ui';\nimport {AuthShell} from '../../components/auth/shell';\n"
                    "import {requireAuthPage} from '../../lib/auth';\nexport const dynamic='force-dynamic';\n"
                    f"export default async function Page(){{const account=await requireAuthPage('/{name}');return "
                    f"<AuthShell pathname=\"/{name}\" username={{account.username}}><Panel title=\"{title}\">"
                    "<p>未接入。此测试站当前提供登录、本人改密和主页项目管理。</p></Panel></AuthShell>;}\n")
# Keep prototype source history; explicitly make every received prototype route 404.
for path in (ROOT / 'apps/website/app/prototypes').rglob('page.tsx'):
    path.write_text("import {notFound} from 'next/navigation';\nexport default function Page(){notFound();}\n")
for path in (ROOT / 'apps/website/app/prototypes').rglob('route.ts'):
    path.write_text("export function GET(){return new Response(null,{status:404});}\n")
(ROOT / 'apps/website/app/globals.css').write_text(""":root { color-scheme:dark; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; background:#0b0e12; color:#e8eef5; }
* { box-sizing:border-box; }
body { margin:0; }
button,input,select,textarea { font:inherit; }
a { color:inherit; }
""")
(ROOT / 'apps/website/app/layout.tsx').write_text("""import type {Metadata} from 'next';
import '@ikun/ui/styles.css';
import './globals.css';
export const metadata:Metadata={title:'ikun.ca v2',description:'受保护的 v2 测试站'};
export default function RootLayout({children}:Readonly<{children:React.ReactNode}>){return <html lang="zh-CN"><body>{children}</body></html>;}
""")
(ROOT / 'apps/website/app/api/v1/[...path]/route.ts').write_text("""import {withAuth} from '../../../../../modules/auth/dist/src/server.js';
import {projectsAuth,failure,requestId} from '../../../../lib/projects';
export const runtime='nodejs';
export const dynamic='force-dynamic';
function unavailable(request:Request){projectsAuth();return withAuth(request,async()=>failure(requestId(request),501,'NOT_IMPLEMENTED','此业务尚未接入测试站'));}
export const GET=unavailable;export const POST=unavailable;export const PUT=unavailable;export const PATCH=unavailable;export const DELETE=unavailable;
""")
# Match the relative import depth from app/api/v1/[...path] to repository modules.
p = ROOT / 'apps/website/app/api/v1/[...path]/route.ts'
p.write_text(p.read_text().replace("'../../../../../modules/auth", "'../../../../../../modules/auth"))
ready = ROOT / 'apps/website/app/health/ready/route.ts'
ready.write_text(ready.read_text().replace('business_enabled: false', "business_enabled: true, profile: 'c0-lite', workers_enabled: false"))
print('C0-lite workspace, exact UI dependency, protected placeholders and 404 prototype routes wired')
