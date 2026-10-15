"""Export immutable dependency objects into this module's ignored local assembly only."""

import argparse
import hashlib
import io
import json
import shutil
import subprocess
import tarfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULE = HERE.parent
ROOT = MODULE.parents[2]
PREVIEW = MODULE / ".b3/preview"
PINS = dict(
    spec="9699375c920465b5d802e7acff17b5421203e544",
    b0="85be3bd6dce25d82033b6cb1a7157aaa39bd571e",
    auth="f097bd4722155d5e689b8894956391ed7e5f2fa7",
    projects="aa51a640a159e4c8f6cdd841a25f4279e73075ba",
    ui="486294ac3255b08fdb13a307ee15f96c571020d9",
    tracking_ui="d90598f4bc595458ce26c5ee1c2e1618e318abc0",
    homepage="eb93ac7739e0ce9d74fa9859f838a7bca294ce3e",
    hunter_ui="08065d700239b20fb4c887bbd0c85321904687f8",
    home_contract="6595c4a05b736889a4649b1d0aa7405601deebc4",
    collections="379c6e583e487f038629e1ca24d4b2614970ad0c",
    release="9e1d1aa53d58b9ee4f23f5ec1356da0ebbf1e362",
    product="50ee277aed435a723aab6139bd952e709b3ad08e",
    night_release="579a57f2e3e470525eb53f9f1f85ba75d25f3728",
    auth_review="967f3098e84de7e299d970019d56b571ac63de94",
    c03_review="0e2c86f3c00e03bcc7e9c49a5572f182d4c86b8a",
    view_review="6ea8b004c368e17a123e055848f59f6370f2c29d",
)


def frozen_sources():
    """Reconstruct the exact immutable exports, including the selective B2 copies."""
    files = {}
    exports = [
        ("b0", ()),
        ("auth", ("modules/auth", "schemas/auth")),
        ("projects", ("modules/projects", "schemas/projects")),
        ("ui", ("packages/ui",)),
        ("tracking_ui", ("apps/website/features/tracking", "apps/website/app/tracking")),
    ]
    for key, paths in exports:
        data = subprocess.check_output(["git", "archive", PINS[key], *paths], cwd=ROOT)
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            for entry in archive:
                if entry.isdir():
                    continue
                if not entry.isfile() or Path(entry.name).is_absolute() or ".." in Path(entry.name).parts:
                    raise ValueError("unsupported frozen archive entry")
                files[entry.name] = archive.extractfile(entry).read()
    for prefix, target in [
        ("modules/auth/integration/website/", "apps/website/"),
        ("modules/projects/integration/website/app/api/v1/projects/", "apps/website/app/api/v1/projects/"),
    ]:
        for name, data in list(files.items()):
            if name.startswith(prefix):
                files[target + name.removeprefix(prefix)] = data
    for name in ("projects.ts", "outbox-relay.ts", "stores.ts"):
        files["apps/website/lib/" + name] = files["modules/projects/integration/website/lib/" + name]
    package = json.loads(files["apps/website/package.json"])
    package["dependencies"]["@ikun/ui"] = "workspace:*"
    files["apps/website/package.json"] = (json.dumps(package, indent=2) + "\n").encode()
    files["pnpm-lock.yaml"] = files["config/b0/pnpm-ui-lock.yaml"]
    return files


def export(ref, *paths):
    data = subprocess.check_output(["git", "archive", ref, *paths], cwd=ROOT)
    subprocess.run(["tar", "-x", "-C", str(PREVIEW)], input=data, check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh-dependencies", action="store_true")
    args = parser.parse_args()
    if args.refresh_dependencies:
        if not PREVIEW.is_dir() or PREVIEW.is_symlink() or PREVIEW != PREVIEW.resolve():
            raise ValueError("private preview must already exist without aliases")
        previous = MODULE / ".b3/frozen-inputs.json"
        if previous.exists():
            history = MODULE / "artifacts/b3/history"
            history.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(previous, history / f"frozen-inputs-before-{time.time_ns()}.json")
        files = frozen_sources()
        for name, data in files.items():
            target = PREVIEW / name
            if target.is_symlink() or target != target.resolve():
                raise ValueError("preview export alias rejected")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        previous.write_text(
            json.dumps(
                {
                    "pins": PINS,
                    "files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
                },
                indent=2,
            )
            + "\n"
        )
        print("Immutable dependency exports refreshed; compiled output requires rebuilding")
        return
    if PREVIEW.exists():
        raise RuntimeError("Existing preview preserved; use it without overwriting frozen exports")
    PREVIEW.mkdir(parents=True)
    export(PINS["b0"])
    export(PINS["auth"], "modules/auth", "schemas/auth")
    export(PINS["projects"], "modules/projects", "schemas/projects")
    export(PINS["ui"], "packages/ui")
    export(PINS["tracking_ui"], "apps/website/features/tracking", "apps/website/app/tracking")
    shutil.copytree(
        PREVIEW / "modules/auth/integration/website", PREVIEW / "apps/website", dirs_exist_ok=True
    )
    shutil.copytree(
        PREVIEW / "modules/projects/integration/website/app/api/v1/projects",
        PREVIEW / "apps/website/app/api/v1/projects",
        dirs_exist_ok=True,
    )
    shutil.copyfile(
        PREVIEW / "modules/projects/integration/website/lib/stores.ts", PREVIEW / "apps/website/lib/stores.ts"
    )
    # Only the immutable Projects IPC client/relay is consumed; homepage isn't replaced.
    for name in ("projects.ts", "outbox-relay.ts"):
        shutil.copyfile(
            PREVIEW / "modules/projects/integration/website/lib" / name, PREVIEW / "apps/website/lib" / name
        )
    data = json.loads((PREVIEW / "apps/website/package.json").read_text())
    data["dependencies"]["@ikun/ui"] = "workspace:*"
    (PREVIEW / "apps/website/package.json").write_text(json.dumps(data, indent=2) + "\n")
    shutil.copyfile(PREVIEW / "config/b0/pnpm-ui-lock.yaml", PREVIEW / "pnpm-lock.yaml")
    files = {
        str(p.relative_to(PREVIEW)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in PREVIEW.rglob("*")
        if p.is_file()
    }
    (MODULE / ".b3/frozen-inputs.json").write_text(
        json.dumps({"pins": PINS, "files": files}, indent=2) + "\n"
    )
    print(PREVIEW)


if __name__ == "__main__":
    main()
