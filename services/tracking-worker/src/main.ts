import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, isAbsolute, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { log, startWorker } from "@ikun/runtime";

const config = process.env.IKUN_TRACKING_CONFIG;
if (!config) {
  startWorker("tracking").catch(() => {
    log("tracking", "startup_failed", { code: "STARTUP_FAILED" });
    process.exitCode = 1;
  });
} else {
  const folder = resolve(dirname(fileURLToPath(import.meta.url)), "../python");
  const python = process.env.IKUN_TRACKING_PYTHON ?? resolve(folder, ".venv/bin/python");
  if (!isAbsolute(config) || !isAbsolute(python) || !existsSync(config) || !existsSync(python)) {
    throw new Error("TRACKING_RUNTIME_CONFIGURATION_INVALID");
  }
  const child = spawn(python, ["-m", "tracking.cli", "serve", "--config", config], {
    cwd: folder, env: process.env, stdio: "inherit",
  });
  child.once("error", () => {
    log("tracking", "startup_failed", { code: "PYTHON_START_FAILED" });
    process.exitCode = 1;
  });
  for (const signal of ["SIGINT", "SIGTERM"] as const) {
    process.on(signal, () => { if (child.exitCode === null) child.kill(signal); });
  }
  child.once("exit", (code, signal) => { process.exitCode = code ?? (signal ? 1 : 0); });
}
