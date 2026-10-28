"""BATTLE-ANY stage 3c: stand resources of generated catalog kinds (pilot).

For each requested CAT-01 catalog kind with a generated battle profile this
writes, into one fresh directory under the stand's local root:
- `<kind>-qualified-profile.json`: the exact qualified physics profile pinned by
  `config/catalog/battle_qualification.v1.json` (copied, SHA checked);
- `<kind>-geometry.json`: the exact collision/armour bundle pinned by
  `config/catalog/battle_profiles.v1.json` (copied, SHA checked);
- `<map>-<kind>-config.json`: per-map physics config = the source pool's own
  pinned config of that map (terrain, obstacles, spawn, bounds; accepted or
  MAPS-01 derived) + the profile's physics/handling projection (same rule as
  tools/p06t_extended_profiles.py);
- `pool-<kind>.json`: pool version 5 (shared-only IPC7 metadata) with the worker
  block of a given legacy pool;
- `battle-profiles-battle-any.json`: the given version3 template manifest as
  version 5 plus one row per generated kind.

Read-only on every source; output names never overwrite (fresh directory).
Admission stays a catalog/writer decision; these files only bind resources.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import battle_any
import catalog_v1_data
from battle_any_profiles import QUALIFICATION

MAX_JSON = 1024 * 1024
MAX_KINDS = 64


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")


def unlinked(path):
    path = Path(path).absolute()
    for p in (path, *path.parents):
        require(not p.is_symlink() and not p.is_junction(), "linked path: " + str(p))
    return path


def read(path, maximum, pin=None):
    path = unlinked(path)
    require(path.is_file() and 0 < path.stat().st_size <= maximum, "source file bound: " + str(path))
    raw = path.read_bytes()
    require(0 < len(raw) <= maximum, "source read bound")
    if pin is not None:
        require(sha(raw) == pin, "source SHA256 mismatch: " + str(path))
    return raw


def inside(local, path):
    path = unlinked(path).resolve()
    require(path.is_relative_to(local) and path != local, "path escapes the local root: " + str(path))
    return path


def generate(local_root, templates, source_pool, qualified_dir, bundles_dir, kinds, out):
    local = unlinked(local_root).resolve(strict=True)
    out = inside(local, out)
    require(out.parent.is_dir() and not out.exists(), "fresh output directory required")
    require(1 <= len(kinds) <= MAX_KINDS and len(set(kinds)) == len(kinds), "kind list")
    catalog = {v["kind"]: v for v in catalog_v1_data.VEHICLES}
    record = json.loads(QUALIFICATION.read_bytes())
    qualified = {r["kind"]: r for r in record["profiles"]}
    manifest = json.loads(read(inside(local, templates), MAX_JSON))
    require(manifest.get("version") == 3 and len(manifest["profiles"]) == 5, "version3 five-kind template manifest required")
    pool = json.loads(read(inside(local, source_pool), MAX_JSON))
    require(pool.get("version") == 3 and len(pool["maps"]) == 2, "version3 two-map source pool required")
    objects, rows = {}, []
    for kind in kinds:
        row = catalog.get(kind)
        require(row is not None and row["battle_admission"] != "none" and row["legacy_inventory"] is None,
                "admitted generated catalog kind required: " + kind)
        g = battle_any.profile(row["vehicle_id"])
        require(g is not None and g["status"] == "generated" and g["kind"] == kind, "generated battle profile: " + kind)
        q = qualified.get(kind)
        require(q is not None, "qualification record: " + kind)
        profile_raw = read(inside(local, Path(qualified_dir) / q["file"]), 16384, q["sha256"])
        profile = json.loads(profile_raw)
        require(profile["kind"] == kind and profile["battle_admission"] is False, "qualified profile identity: " + kind)
        bundle_raw = read(inside(local, Path(bundles_dir) / g["geometry"]["bundle"]), 512 * 1024, g["geometry"]["sha256"])
        objects[kind + "-qualified-profile.json"] = profile_raw
        objects[kind + "-geometry.json"] = bundle_raw
        maps = []
        for source in pool["maps"]:
            # Map identity, meshes, spawn and bounds of the stand's own pinned legacy config
            # of that map (accepted or MAPS-01 derived); only physics/handling change.
            base = json.loads(read(inside(local, Path(source["config"])), 16384, source["config_sha256"]))
            config = {k: base[k] for k in ("version", "profile", "map", "terrain", "obstacles", "spawn_origin", "spawn_yaw", "bounds_xz")}
            config.update(profile["definition"]["physics"], handling=profile["definition"]["handling"])
            name = source["asset"] + "-" + kind + "-config.json"
            objects[name] = encoded(config)
            maps.append(dict(arena_type_id=source["arena_type_id"], asset=source["asset"], config=str(out / name),
                             config_sha256=sha(objects[name])))
        pool_value = dict(version=5, profile="test_lab", worker=pool["worker"], maps=maps,
                          vehicle_profile=dict(path=str(out / (kind + "-qualified-profile.json")), sha256=q["sha256"]))
        objects["pool-" + kind + ".json"] = encoded(pool_value)
        rows.append(dict(kind=kind, pool=dict(path=str(out / ("pool-" + kind + ".json")), sha256=sha(objects["pool-" + kind + ".json"])),
                         geometry=dict(path=str(out / (kind + "-geometry.json")), sha256=g["geometry"]["sha256"])))
    templates_value = dict(manifest, version=5, profiles=manifest["profiles"] + rows)
    objects["battle-profiles-battle-any.json"] = encoded(templates_value)
    out.mkdir()
    receipt = []
    for name, raw in objects.items():
        raw = raw if isinstance(raw, bytes) else encoded(raw)
        with (out / name).open("xb") as stream:
            stream.write(raw)
        receipt.append(dict(path=name, bytes=len(raw), sha256=sha(raw)))
    result = dict(schema="battle-any-stand.v1", status="PASS_RESOURCES_ONLY", kinds=kinds,
                  catalog_sha256=catalog_v1_data.CATALOG_SHA256, table_sha256=battle_any.data.TABLE_SHA256,
                  qualification_sha256=sha(QUALIFICATION.read_bytes()), native="NOT_RUN", outputs=receipt,
                  templates=str(out / "battle-profiles-battle-any.json"),
                  templates_sha256=sha(objects["battle-profiles-battle-any.json"]))
    with (out / "generation.json").open("xb") as stream:
        stream.write(encoded(result))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--local-root", type=Path, required=True)
    parser.add_argument("--templates", type=Path, required=True, help="version3 five-kind battle-profiles manifest")
    parser.add_argument("--source-pool", type=Path, required=True, help="version3 legacy pool (worker block, map list)")
    parser.add_argument("--qualified-dir", type=Path, required=True)
    parser.add_argument("--bundles-dir", type=Path, required=True)
    parser.add_argument("--kind", action="append", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    result = generate(args.local_root, args.templates, args.source_pool, args.qualified_dir, args.bundles_dir, args.kind, args.out)
    print(json.dumps(dict(status=result["status"], templates=result["templates"], templates_sha256=result["templates_sha256"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
