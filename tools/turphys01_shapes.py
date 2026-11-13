"""TURPHYS-01: hull and turret boxes per generated vehicle for the physics worker.

A projection of the geometry bundles that `tools/battle_any_profiles.py build`
writes from the original client: hull and turret mesh bounds and the hull and
turret pivots. Each bundle must have the SHA-256 that the committed battle
profile table pins for it, so the projection adds no new source. The profile
definitions and their pinned hashes are not touched.

    python -B -X utf8 tools/battle_any_profiles.py build --original <client> --out local/evidence/<fresh>
    WOT091_TEST_LAB=1 python -B -X utf8 tools/battle_any_profiles.py build --original <client> --out local/evidence/<fresh2>
    python -B -X utf8 tools/turphys01_shapes.py build --bundles local/evidence/<fresh>/bundles --bundles local/evidence/<fresh2>/bundles
    python -B -X utf8 tools/turphys01_shapes.py check [--bundles ...]
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLES = (ROOT / "config/catalog/battle_profiles.v1.json", ROOT / "config/test_lab/battle_profiles.v1.json")
OUT = ROOT / "server/physics/Profiles/turret-shapes.json"
POLICY = "turphys01-hull-turret-boxes-v1"
MAX_BUNDLE = 64 * 1024 * 1024
MIN_TURRET = .05  # metres per axis; project value
MAX_ROWS = 16384


def canonical(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")


def generated_rows():
    rows = {}
    for path in TABLES:
        for r in json.loads(path.read_text(encoding="utf-8"))["vehicles"]:
            if r.get("status") != "generated":
                continue
            kind, geometry = r["kind"], r["geometry"]
            pin = (geometry["bundle"], geometry["sha256"])
            if rows.setdefault(kind, pin) != pin:
                raise ValueError(kind + ": tables pin different geometry bundles")
    if not 1 <= len(rows) <= MAX_ROWS:
        raise ValueError("generated row count")
    return rows


def build_rows(rows):
    """CONTENT-0 3.3/4: {build label: (stock kind, build geometry pin, turret part pin or None)} of every generated
    build of a generated stock kind. The hull box and turret position are the stock hull's (the turret centre does
    not depend on the chassis hull position, ReferenceShapes.cs); the turret box is the stock one when the build keeps
    the stock turret, else the mesh bounds of its own turret part (None)."""
    from phys01_characteristics import generated_builds
    out = {}
    for v, stock, e in generated_builds():
        kind = v["hull"]["kind"]
        if kind not in rows:
            continue
        t = e["modules"]["turret"]
        part = None if t == stock["modules"]["turret"] else v["turrets"][t]["part"]["sha256"]
        row = (kind, e["geometry_sha256"], part)
        if out.setdefault(e["label"], row) != row:
            raise ValueError(e["label"] + ": tables disagree")
    return out


def turret_part_bounds(parts, digest, label):
    """The turret component's mesh bounds of one collision part (`parts/<sha>.json`, pinned by its SHA)."""
    found = [d / (digest + ".json") for d in parts if (d / (digest + ".json")).is_file()]
    if not found:
        raise ValueError(label + ": turret part " + digest + " absent")
    raw = found[0].read_bytes()
    if len(raw) > MAX_BUNDLE or hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError(label + ": turret part differs from its pin")
    component = json.loads(raw)["component"]
    if not component["name"].lower().startswith("turret"):
        raise ValueError(label + ": not a turret part")
    return turret_bounds(component["mesh_bounds"], label)


def bounds(value, label):
    lo, hi = value["min"], value["max"]
    if len(lo) != 3 or len(hi) != 3 or not all(isinstance(x, (int, float)) and -20 <= x <= 20 for x in lo + hi):
        raise ValueError(label + " bounds")
    if not all(hi[i] > lo[i] for i in range(3)):
        raise ValueError(label + " empty bounds")
    return dict(min=[float(x) for x in lo], max=[float(x) for x in hi])


def vector(value, label):
    if len(value) != 3 or not all(isinstance(x, (int, float)) and -20 <= x <= 20 for x in value):
        raise ValueError(label + " vector")
    return [float(x) for x in value]


def project(kind, raw):
    bundle = json.loads(raw)
    g = bundle["geometry"]
    components = g["components"]
    if len(components) != 3 or not components[1]["name"].lower().startswith("turret"):
        raise ValueError(kind + ": expected hull, turret, gun components")
    return dict(kind=kind, hull_position=vector(g["hull_position"], kind + " hull position"),
                turret_position=vector(g["turret_position"], kind + " turret position"),
                hull_bounds=bounds(components[0]["mesh_bounds"], kind + " hull"),
                turret_bounds=turret_bounds(components[1]["mesh_bounds"], kind))


def turret_bounds(value, kind):
    # A casemate vehicle has a flat or empty turret model: it gets no turret box (null), only the hull box.
    lo, hi = value["min"], value["max"]
    if all(isinstance(x, (int, float)) for x in lo + hi) and any(hi[i] - lo[i] < MIN_TURRET for i in range(3)):
        return None
    return bounds(value, kind + " turret")


def build(directories, parts=()):
    rows = generated_rows()
    out = []
    for kind, (name, digest) in sorted(rows.items()):
        found = [d / name for d in directories if (d / name).is_file()]
        if not found:
            raise ValueError(kind + ": bundle " + name + " absent")
        raw = found[0].read_bytes()
        if len(raw) > MAX_BUNDLE or hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError(kind + ": bundle differs from the table pin")
        out.append(dict(project(kind, raw), bundle_sha256=digest))
    by_kind = {r["kind"]: r for r in out}
    for label, (kind, digest, turret) in build_rows(rows).items():
        row = dict(by_kind[kind], kind=label, bundle_sha256=digest)
        if turret is not None:
            row["turret_bounds"] = turret_part_bounds(parts, turret, label)
        out.append(row)
    out.sort(key=lambda r: r["kind"])
    if len(out) > MAX_ROWS:
        raise ValueError("turret shapes row count")
    return dict(version=1, policy=POLICY, source="battle_profiles.v1 geometry bundles (original client collision models)",
                vehicles=out)


def check(directories, parts=()):
    data = json.loads(OUT.read_text(encoding="ascii"))
    if OUT.read_bytes() != canonical(data):
        raise ValueError("turret shapes not canonical")
    rows = generated_rows()
    kinds = {r["kind"]: r["bundle_sha256"] for r in data["vehicles"]}
    expected = {k: v[1] for k, v in rows.items()}
    expected.update({label: digest for label, (_, digest, _) in build_rows(rows).items()})
    if kinds != expected:
        raise ValueError("turret shapes do not cover exactly the generated rows and their bundle pins")
    if directories and canonical(build(directories, parts)) != OUT.read_bytes():
        raise ValueError("turret shapes differ from the bundles")
    return dict(status="PASS", vehicles=len(kinds), bundles_checked=bool(directories))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=("build", "check"))
    p.add_argument("--bundles", type=Path, action="append", default=[])
    p.add_argument("--parts", type=Path, action="append", default=[], help="CONTENT-0 4: collision parts (parts/<sha>.json)")
    a = p.parse_args(argv)
    if a.command == "build":
        if not a.bundles:
            p.error("build needs --bundles")
        OUT.write_bytes(canonical(build(a.bundles, a.parts)))
        a.command = "check"
    print(json.dumps(check(a.bundles, a.parts), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
