"""Record reproducible local evidence without running a build or browser."""

import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent


def module(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + ".py"))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pytest-log", required=True)
    parser.add_argument("--node-log", required=True)
    parser.add_argument("--lifecycle-log", required=True)
    args = parser.parse_args()
    build = module("build-b3")
    binding = module("bind-b3").bind()
    logs = {}
    for name, value in vars(args).items():
        path = Path(value).resolve()
        if not path.is_relative_to(build.MODULE / "artifacts/b3"):
            raise ValueError("evidence logs must belong to this module")
        logs[name] = {"path": str(path.relative_to(build.MODULE)), "sha256": digest(path.read_bytes())}
    xml = Path(args.pytest_log).resolve().with_suffix(".xml")
    cases = list(ET.parse(xml).getroot().iter("testcase"))
    if any(list(case) for case in cases):
        raise ValueError("all evidence cases must pass without skips")
    if "B3_LIFECYCLE_PASS" not in Path(args.lifecycle_log).read_text():
        raise ValueError("lifecycle did not pass")
    node = Path(args.node_log).read_text()
    if not re.search(r"(?:#|ℹ) pass 6\b", node) or not re.search(r"(?:#|ℹ) fail 0\b", node):
        raise ValueError("actual Node entry cases did not pass")
    inputs = build.source_inputs()
    result = {
        "schema_version": 1,
        "status": "LOCAL_CANDIDATE_HEAVY_VALIDATION_PAUSED",
        "base_commit": "9e2835cafc95cb15dc4b8178abacf0c604018536",
        "pins": build.a.PINS,
        "pytest": {
            "passed": len(cases),
            "by_file": dict(Counter(c.attrib["classname"] for c in cases)),
            "node_wrapper_count": 1,
            "nested_node_cases": 6,
            "nested_cases_added_to_total": False,
        },
        "logs": logs
        | {"junit": {"path": str(xml.relative_to(build.MODULE)), "sha256": digest(xml.read_bytes())}},
        "source_inputs": inputs,
        "source_set_sha256": digest(json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode()),
        "preview_source_files": len(binding["files"]),
        "preview_source_set_sha256": binding["preview_source_set_sha256"],
        "ui_patch_sha256": binding["ui_patch_sha256"],
        "allowed_paths": ["services/tracking-worker/", "schemas/tracking/"],
        "runtime_database": "DATA_ROOT/tracking/tracking.db",
        "real_provider_calls": 0,
        "deployed": False,
        "heavy_validation": {
            "final_build": "PAUSED",
            "compiled_launcher": "PAUSED",
            "browser_1440_390": "PAUSED",
            "historical_build_1": "STALE_SOURCE_NOT_FINAL_EVIDENCE",
        },
        "blocked_contracts": ["C-01", "C-03", "C-05", "B2_TRACKING_INGEST_501"],
    }
    scope = subprocess.check_output(
        ["git", "diff", "--name-only", result["base_commit"]], cwd=build.a.ROOT, text=True
    ).splitlines()
    scope += subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard"], cwd=build.a.ROOT, text=True
    ).splitlines()
    if any(not any(path.startswith(prefix) for prefix in result["allowed_paths"]) for path in scope):
        raise ValueError("changed path outside Tracking ownership")
    target = build.MODULE / "B3-EVIDENCE.json"
    target.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print("B3_LIGHT_EVIDENCE", len(cases), result["source_set_sha256"])


if __name__ == "__main__":
    main()
