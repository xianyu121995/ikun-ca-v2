import { log, startWorker } from "@ikun/runtime";
startWorker("hunter").catch(() => { log("hunter", "startup_failed", { code: "STARTUP_FAILED" }); process.exitCode = 1; });
