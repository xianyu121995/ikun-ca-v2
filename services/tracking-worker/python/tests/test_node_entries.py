"""One pytest wrapper contains nine Node cases; never add those nine twice."""

import subprocess
import time
from pathlib import Path


def test_actual_b1_b2_tracking_entries():
    module = Path(__file__).resolve().parents[1]
    node = Path("/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2/.tools/node/bin/node")
    preview = module / ".b3/preview"
    if not (preview / "modules/auth/dist/src/server.js").exists():
        raise RuntimeError("Prepare pinned B3 dependency assembly before integration regression")
    result = subprocess.run(
        [
            str(node),
            "--import",
            str(preview / "node_modules/tsx/dist/loader.mjs"),
            "--test",
            str(module / "integration/tests/entries.test.mjs"),
        ],
        cwd=module,
        capture_output=True,
        text=True,
        timeout=90,
    )
    logs = module / "artifacts/b3"
    logs.mkdir(parents=True, exist_ok=True)
    log = logs / f"node-entries-pytest-{time.time_ns()}.log"
    log.write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
