import { parseArgs } from "node:util";
import { environment } from "./config.js";
import { AuthStore } from "./store.js";
import { AuthError } from "./security.js";

async function hidden(prompt: string): Promise<string> {
  if (!process.stdin.isTTY || !process.stdout.isTTY) throw new Error("AUTH_TTY_REQUIRED");
  process.stdout.write(prompt);
  const previous=process.stdin.isRaw;
  process.stdin.setRawMode(true);process.stdin.resume();
  try {
    return await new Promise((resolve,reject)=>{
      let value="";
      function input(chunk: Buffer) {
        for (const char of chunk.toString("utf8")) {
          if (char==="\u0003") {cleanup();reject(new Error("AUTH_CANCELLED"));return;}
          if (char==="\r" || char==="\n") {cleanup();resolve(value);return;}
          if (char==="\u007f" || char==="\b") value=[...value].slice(0,-1).join("");
          else if (char>=" " && [...value].length<129) value+=char;
        }
      }
      function cleanup() {process.stdin.off("data",input);process.stdout.write("\n");}
      process.stdin.on("data",input);
    });
  } finally {process.stdin.setRawMode(previous);process.stdin.pause();}
}
async function main() {
  const {values,positionals}=parseArgs({allowPositionals:true,options:{username:{type:"string"}}});
  const command=positionals[0];
  if (positionals.length!==1 || !["bootstrap","migrate"].includes(command??""))
    throw new Error("USAGE: cli.js migrate | bootstrap --username NAME");
  // Verify TTY before creating a database; passwords are never accepted as arguments/env/stdin pipes.
  if (command==="bootstrap" && (!process.stdin.isTTY || !values.username)) throw new Error("AUTH_TTY_AND_USERNAME_REQUIRED");
  const store=new AuthStore(environment(),true);
  try {
    if (command==="migrate") {console.log("Auth migration 002 ready.");return;}
    const value=await hidden("超级管理员密码（至少15字符）：");
    if (value!==await hidden("再次输入密码：")) throw new Error("AUTH_PASSWORD_MISMATCH");
    await store.bootstrap(values.username!,value);
    console.log("初始超级管理员已创建；密码不会被输出或记录。");
  } finally {store.close();}
}
main().catch(error=>{
  console.error(error instanceof AuthError?error.message:
    error instanceof Error && /^(AUTH_|USAGE:)/.test(error.message)?error.message:"AUTH_INITIALIZATION_FAILED");
  process.exitCode=1;
});
