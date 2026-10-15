import { log, startWorker } from "@ikun/runtime";
import { existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

// Explicit opt-in replaces this OS process with Python. No fourth service or child supervisor.
if (process.env.HUNTER_ENGINE === "python") {
  try {
    const pythonRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../python");
    const python = process.env.HUNTER_PYTHON_BIN ?? join(pythonRoot, ".venv/bin/python");
    if (!existsSync(python) || !process.env.DATA_ROOT) throw new Error("PYTHON_RUNTIME_NOT_CONFIGURED");
    if ((process.env.HUNTER_EXTERNAL_IO_ENABLED ?? "0") !== "0") throw new Error("EXTERNAL_COLLECTION_NOT_RELEASED");
    const env = Object.fromEntries(Object.entries(process.env).filter((entry): entry is [string, string] => typeof entry[1] === "string"));
    Object.assign(env, {
      PYTHONPATH: pythonRoot,
      HUNTER_DB: join(resolve(process.env.DATA_ROOT), "hunter", "hunter.db"),
      HUNTER_HOST: "127.0.0.1",
      HUNTER_PORT: process.env.HUNTER_PORT ?? "3311",
      HUNTER_V2_MODE: "1",
      HUNTER_ADMIN_TOKEN: process.env.HUNTER_API_TOKEN ?? "",
      HUNTER_TENANT_ID: "ikun-main",
      HUNTER_DELIVERY_PROTOCOL: "v2-event",
      HUNTER_EXTERNAL_IO_ENABLED: "0",
      HUNTER_REQUIRE_EXTERNAL_IO_DISABLED: "1",
    });
    delete env.OPENNEWS_TOKEN;
    delete env.TWITTERAPI_IO_API_KEY;
    if (!process.execve) throw new Error("EXECVE_UNAVAILABLE");
    process.execve(python, [python, "-m", "hunterradar", "run"], env);
    throw new Error("EXECVE_UNAVAILABLE");
  } catch {
    log("hunter", "startup_failed", { code: "HUNTER_PYTHON_STARTUP_FAILED" });
    process.exitCode = 1;
  }
} else {
  startWorker("hunter").catch(() => { log("hunter", "startup_failed", { code: "STARTUP_FAILED" }); process.exitCode = 1; });
}
