import { log, startWorker } from "@ikun/runtime";
startWorker("tracking").catch(() => { log("tracking", "startup_failed", { code: "STARTUP_FAILED" }); process.exitCode = 1; });
