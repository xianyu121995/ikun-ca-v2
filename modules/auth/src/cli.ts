import { parseArgs } from "node:util";
import { environment } from "./config.js";
import { LocalAccounts } from "./local.js";
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
  const commands=["bootstrap","create","create-admin","disable","enable","reset-password","recover-admin","list","migrate"];
  if (positionals.length!==1 || !commands.includes(command??"") ||
      (!["migrate","list"].includes(command??"") && !values.username) || (["migrate","list"].includes(command??"") && values.username))
    throw new Error("USAGE: cli.js bootstrap|create|create-admin|disable|enable|reset-password|recover-admin --username NAME | list | migrate");
  // OS account and private filesystem permissions are the authority; no web session is needed.
  if (command!=="migrate" && (!process.stdin.isTTY || !process.stdout.isTTY)) throw new Error("AUTH_TTY_REQUIRED");
  const store=new LocalAccounts(environment(),command==="bootstrap" || command==="migrate");
  try {
    if (command==="migrate") {console.log("Auth migration 002 ready.");return;}
    if (command==="list") {console.table(store.list());return;}
    if (command==="disable" || command==="enable") store.setEnabled(values.username!,command==="enable");
    else {
      const value=await hidden("初始密码（至少10字符）：");
      if (value!==await hidden("再次输入密码：")) throw new Error("AUTH_PASSWORD_MISMATCH");
      if(command==="bootstrap") await store.bootstrap(values.username!,value);
      else if(command==="create" || command==="create-admin") await store.create(values.username!,value,command==="create-admin");
      else await store.reset(values.username!,value,command==="recover-admin");
    }
    console.log("本地账号操作完成；新建或重置后必须在网页修改初始密码。密码不会输出或记录。");
  } finally {store.close();}
}
main().catch(error=>{
  console.error(error instanceof AuthError?error.message:
    error instanceof Error && /^(AUTH_|USAGE:)/.test(error.message)?error.message:"AUTH_INITIALIZATION_FAILED");
  process.exitCode=1;
});
