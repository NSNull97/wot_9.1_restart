"""Derive a profile13 template manifest that also binds the pinned chassis bundles.

The input manifest is only read. Each profile row whose vehicle has a generated
chassis bundle (`config/catalog/chassis_armor.v1.json`) gets
`"chassis": {"path", "sha256"}`; the bundle bytes must equal the table pin. Rows
without a bundle stay as they are (the gateway then keeps the old hull-only hit).
The gateway reads the optional `chassis` key since SHELL-02.

Command: `python -B -X utf8 tools/chassis_manifest.py --manifest M --bundles DIR --out NEW`
(`DIR` is the `bundles/` directory written by `tools/chassis_armor_export.py build`).
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
TABLE = ROOT / "config" / "catalog" / "chassis_armor.v1.json"
MAX_MANIFEST = 1024 * 1024
MAX_BUNDLE = 512 * 1024
# Curated gateway kind labels (`VehicleKind::label`) -> bundle `<nation>-<resource>.json`.
CURATED = {"ms1": "ussr-MS-1", "is7": "ussr-IS-7", "t26": "ussr-T-26", "t34": "ussr-T-34", "t3485": "ussr-T-34-85",
           "wt-e100-128": "germany-Waffentrager_E100", "fv215b-183": "uk-GB48_FV215b_183"}


class ManifestError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ManifestError(message)


def read(path, limit):
    path = Path(path)
    require(path.is_absolute() and path.is_file() and not path.is_symlink(), "absolute plain file required: " + str(path))
    raw = path.read_bytes()
    require(0 < len(raw) <= limit, "size bound: " + str(path))
    return raw


def pins():
    table = json.loads(TABLE.read_bytes())
    require(table["schema"] == "wot091-chassis-armor.v1", "chassis table schema")
    return {row["bundle"]: row for row in table["vehicles"] if row["status"] == "generated"}


def derive(manifest_path, bundles_dir):
    manifest = json.loads(read(manifest_path, MAX_MANIFEST))
    require(isinstance(manifest, dict) and isinstance(manifest.get("profiles"), list), "manifest profiles")
    bundles_dir = Path(bundles_dir)
    require(bundles_dir.is_absolute() and bundles_dir.is_dir(), "absolute bundles directory required")
    table = pins()
    bound, kept = [], []
    for row in manifest["profiles"]:
        require(isinstance(row, dict) and set(row) == {"kind", "pool", "geometry"}, "profile row must be the old exact shape")
        label = row["kind"]
        name = CURATED.get(label, label) + ".json"
        pin = table.get(name)
        if pin is None:
            kept.append(label)
            continue
        path = bundles_dir / name
        raw = read(path, MAX_BUNDLE)
        digest = hashlib.sha256(raw).hexdigest()
        require(digest == pin["sha256"] and len(raw) == pin["bytes"], name + ": bundle bytes differ from the table pin")
        row["chassis"] = {"path": str(path), "sha256": digest}
        bound.append(dict(kind=label, bundle=name, vehicle_id=pin["vehicle_id"]))
    return manifest, bound, kept


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--bundles", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    out = Path(args.out)
    require(out.is_absolute() and not out.exists() and out.parent.is_dir(), "fresh absolute output with existing parent required")
    manifest, bound, kept = derive(args.manifest, args.bundles)
    raw = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    with out.open("xb") as stream:
        stream.write(raw)
    print(json.dumps(dict(out=str(out), sha256=hashlib.sha256(raw).hexdigest(), bound=bound, without_chassis=kept), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
