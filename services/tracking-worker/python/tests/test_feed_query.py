"""One wrapper for twelve Node query, cancellation and private UDS budget cases."""

import subprocess
import os
import shutil
import sys
import time
from pathlib import Path


def test_feed_query_node_contract():
    module = Path(__file__).resolve().parents[1]
    root = module.parents[2]
    node = shutil.which("node")
    (module / "artifacts/b3").mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            node,
            "--import",
            str(root / "node_modules/tsx/dist/loader.mjs"),
            "--test",
            str(module / "integration/tests/feed-query.test.mjs"),
        ],
        check=False,
        cwd=module,
        capture_output=True,
        text=True,
        timeout=40,
        env=dict(
            os.environ,
            IKUN_TEST_REPO_ROOT=str(root),
            IKUN_TEST_PYTHON=sys.executable,
            PYTHONPATH=os.pathsep.join([str(root / "packages/runtime/python"), str(module)]),
        ),
    )
    (module / f"artifacts/b3/feed-query-{time.time_ns()}.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
