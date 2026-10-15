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
}
else {
    const folder = resolve(dirname(fileURLToPath(import.meta.url)), "../python");
    const python = process.env.IKUN_TRACKING_PYTHON ?? resolve(folder, ".venv/bin/python");
    if (!isAbsolute(config) || !isAbsolute(python) || !existsSync(config) || !existsSync(python)) {
        throw new Error("TRACKING_RUNTIME_CONFIGURATION_INVALID");
    }
    const runtime = await import("@ikun/runtime") as typeof import("@ikun/runtime") & {
        spawnManaged?: (command: string, args: string[], options: {
            cwd: string;
            env: NodeJS.ProcessEnv;
            inheritOutput: boolean;
            graceMs: number;
        }) => {
            child: import("node:child_process").ChildProcess;
            stop: () => Promise<void>;
        };
    };
    if (!runtime.spawnManaged)
        throw new Error("PINNED_B0_RUNTIME_REQUIRED");
    const env: NodeJS.ProcessEnv = {};
    for (const key of ["PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "DATA_ROOT", "TRACKING_API_TOKEN"]) {
        if (process.env[key] !== undefined)
            env[key] = process.env[key];
    }
    // This release is explicitly admitted with external collection closed.
    env.IKUN_TRACKING_EXTERNAL_IO_DISABLED = "1";
    const entry = resolve(folder, "entry.py");
    if (!existsSync(entry)) throw new Error("TRACKING_RELEASE_ENTRY_MISSING");
    const managed = runtime.spawnManaged(python, [entry, "serve", "--config", config], {
        cwd: dirname(config), env, inheritOutput: true, graceMs: 10000,
    });
    const child = managed.child;
    child.once("error", () => {
        log("tracking", "startup_failed", { code: "PYTHON_START_FAILED" });
        process.exitCode = 1;
    });
    for (const signal of ["SIGINT", "SIGTERM"] as const) {
        process.on(signal, () => { void managed.stop(); });
    }
    child.once("exit", (code, signal) => { process.exitCode = code ?? (signal ? 1 : 0); });
}
