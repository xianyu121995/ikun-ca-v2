"""Verify every consumed frozen/candidate source file before binding a build receipt."""

import difflib
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("assembly", HERE / "prepare-b3.py")
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


def digest(value):
    return hashlib.sha256(value).hexdigest()


def bind():
    expected = a.frozen_sources()
    for relative in ("services/tracking-worker/python/tracking", "schemas/tracking"):
        for name in list(expected):
            if name.startswith(relative + "/"):
                del expected[name]
        for source in (a.ROOT / relative).rglob("*"):
            if source.is_file() and "__pycache__" not in source.parts:
                expected[str(source.relative_to(a.ROOT))] = source.read_bytes()
    main = "services/tracking-worker/src/main.ts"
    expected[main] = (a.ROOT / main).read_bytes()
    for source in (HERE / "website").rglob("*"):
        if source.is_file():
            expected["apps/website/" + str(source.relative_to(HERE / "website"))] = source.read_bytes()
    # sync-b3 always derives these two files from the fixed UI commit and writes its full patch.
    patch = ""
    for name in ("tracking-page.tsx", "model.ts"):
        path = "apps/website/features/tracking/final/" + name
        expected[path] = (a.PREVIEW / path).read_bytes()
        original = subprocess.check_output(["git", "show", a.PINS["tracking_ui"] + ":" + path], cwd=a.ROOT)
        patch += "".join(
            difflib.unified_diff(
                original.decode().splitlines(True),
                expected[path].decode().splitlines(True),
                fromfile="a/" + path,
                tofile="b/" + path,
            )
        )
    if patch.encode() != (HERE / "patches/tracking-live.patch").read_bytes():
        raise RuntimeError("PREVIEW_UI_PATCH_MISMATCH")
    mismatches = []
    files = {}
    for name, data in expected.items():
        path = a.PREVIEW / name
        if not path.is_file() or path.is_symlink() or path.read_bytes() != data:
            mismatches.append(name)
        files[name] = digest(data)
    if mismatches:
        raise RuntimeError("PREVIEW_SOURCE_MISMATCH: " + ", ".join(mismatches))
    receipt = {
        "pins": a.PINS,
        "files": files,
        "preview_source_set_sha256": digest(
            json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
        ),
        "ui_patch_sha256": digest((HERE / "patches/tracking-live.patch").read_bytes()),
    }
    (a.MODULE / ".b3/frozen-inputs-verified.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


if __name__ == "__main__":
    receipt = bind()
    print("B3_SOURCE_BIND_PASS", len(receipt["files"]), receipt["preview_source_set_sha256"])
