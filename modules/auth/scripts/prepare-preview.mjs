/** Copy this worktree's foundation into an ignored, isolated Next build directory. */
import { cpSync, existsSync, mkdirSync, rmSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { join, resolve } from "node:path";
const root=fileURLToPath(new URL("../../../",import.meta.url));
const preview=join(root,"modules/auth/test-results/next-preview");
if (existsSync(preview)) rmSync(preview,{recursive:true,force:true});
mkdirSync(preview,{recursive:true});
const archive=execFileSync("git",["archive","HEAD"],{cwd:root,maxBuffer:8*1024*1024});
execFileSync("tar",["-x","-C",preview],{input:archive});
cpSync(join(root,"node_modules"),join(preview,"node_modules"),{recursive:true,dereference:false});
for (const part of ["apps/website/node_modules","packages/contracts/node_modules","packages/runtime/node_modules",
  "packages/contracts/dist","packages/runtime/dist"])
  if (existsSync(join(root,part))) cpSync(join(root,part),join(preview,part),{recursive:true,dereference:false});
mkdirSync(join(preview,"modules/auth"),{recursive:true});
for (const part of ["src","dist","tsconfig.json"])
  cpSync(join(root,"modules/auth",part),join(preview,"modules/auth",part),{recursive:true});
cpSync(join(root,"modules/auth/integration/website"),join(preview,"apps/website"),{recursive:true});
console.log(resolve(preview));
