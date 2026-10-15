"""One wrapper for twelve Node query, cancellation and private UDS budget cases."""

import subprocess
import time
from pathlib import Path


def test_feed_query_node_contract():
    module = Path(__file__).resolve().parents[1]
    node = "/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2/.tools/node/bin/node"
    result = subprocess.run(
        [
            node,
            "--import",
            str(module / ".b3/preview/node_modules/tsx/dist/loader.mjs"),
            "--test",
            str(module / "integration/tests/feed-query.test.mjs"),
        ],
        check=False,
        cwd=module,
        capture_output=True,
        text=True,
        timeout=40,
    )
    (module / f"artifacts/b3/feed-query-{time.time_ns()}.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
