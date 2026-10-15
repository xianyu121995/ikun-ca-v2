"""Run under the shared heavy lock. Candidate source binding and serial builds."""

import hashlib
import importlib.util
import json
import os
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("assembly", HERE / "prepare-b3.py")
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)
MODULE = a.MODULE
P = a.PREVIEW


def source_inputs():
    inputs = {}
    for base in (
        MODULE / "tracking",
        MODULE / "tests",
        HERE,
        a.ROOT / "schemas/tracking",
        a.ROOT / "services/tracking-worker/src",
    ):
        for file in base.rglob("*"):
            if (
                file.is_file()
                and "__pycache__" not in file.parts
                and file.suffix in (".py", ".ts", ".tsx", ".mjs", ".sql", ".patch")
            ):
                inputs[str(file.relative_to(a.ROOT))] = hashlib.sha256(file.read_bytes()).hexdigest()
    for name in (
        "config.example.json",
        "requirements.lock.txt",
        "pyproject.toml",
        "deploy/ca.ikun.v2.tracking.plist.example",
        "entry.py",
    ):
        file = MODULE / name
        inputs[str(file.relative_to(a.ROOT))] = hashlib.sha256(file.read_bytes()).hexdigest()
    return inputs


def main():
    subprocess.run([str(MODULE / ".venv/bin/python"), str(HERE / "sync-b3.py")], check=True)
    subprocess.run([str(MODULE / ".venv/bin/python"), str(HERE / "bind-b3.py")], check=True)
    env = {
        **os.environ,
        "PATH": "/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2/.tools/node/bin:"
        + os.environ.get("PATH", ""),
        "NEXT_TELEMETRY_DISABLED": "1",
    }
    logs = MODULE / "artifacts/b3"
    logs.mkdir(parents=True, exist_ok=True)
    previous = logs / "build-inputs.json"
    if previous.exists():
        (logs / f"build-inputs-prior-{time.time_ns()}.json").write_bytes(previous.read_bytes())
    run = len(list(logs.glob("build-*.log"))) + 1
    logpath = logs / f"build-{run}.log"
    with logpath.open("w") as out:
        for cmd in [
            ["pnpm", "build:shared"],
            ["pnpm", "--filter", "@ikun/ui", "build"],
            ["pnpm", "exec", "tsc", "-p", "modules/auth/tsconfig.json"],
            ["pnpm", "--filter", "@ikun/tracking-worker", "build"],
            ["pnpm", "--filter", "@ikun/website", "build"],
        ]:
            result = subprocess.run(cmd, cwd=P, env=env, stdout=out, stderr=subprocess.STDOUT)
            if result.returncode:
                raise RuntimeError("BUILD_FAILED: " + str(logpath))
    subprocess.run([str(MODULE / ".venv/bin/python"), str(HERE / "bind-b3.py")], check=True)
    inputs = source_inputs()
    binding = json.loads((MODULE / ".b3/frozen-inputs-verified.json").read_text())
    receipt = {
        "pins": a.PINS,
        "source_inputs": inputs,
        "source_set_sha256": hashlib.sha256(
            json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "preview_source_set_sha256": binding["preview_source_set_sha256"],
        "preview_source_files": binding["files"],
        "next_build_id": (P / "apps/website/.next/BUILD_ID").read_text().strip(),
        "build_log_sha256": hashlib.sha256(logpath.read_bytes()).hexdigest(),
        "ui_patch_sha256": hashlib.sha256((HERE / "patches/tracking-live.patch").read_bytes()).hexdigest(),
    }
    encoded = json.dumps(receipt, indent=2) + "\n"
    (logs / f"build-{run}-inputs.json").write_text(encoded)
    (logs / "build-inputs.json").write_text(encoded)
    print("B3_BUILD_PASS " + receipt["source_set_sha256"])


if __name__ == "__main__":
    main()
