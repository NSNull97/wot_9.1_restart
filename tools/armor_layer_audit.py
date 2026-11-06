"""SHELL-PEN step 1: can a shot tell entering a layer from leaving it?

For every battle vehicle of the main table (config/catalog/battle_profiles.v1.json,
status generated) this reads its BATTLE-ANY geometry bundle (Hull/Turret/Gun) and
its chassis armour bundle, both pinned by SHA-256, and reports per component:

- mesh topology: boundary edges (used once), non-manifold edges (used 3+ times),
  edges whose two triangles disagree on orientation, closed = no boundary/non-manifold;
- signed volume (sum a.(b x c)/6) of a closed, consistently oriented mesh;
- outward test: rays from outside towards the bounding-box centre on a fixed grid;
  for the first triangle crossed, dot(ray, winding normal) < 0 means the winding
  normal points out of the solid (an entry is "against the winding");
- material roles: main armour (vehicleDamageFactor > 0), spaced armour (factor 0,
  not a device), tracks (kinds 23/24), devices (damageKind 1), and whether each
  role's triangles form closed sub-meshes.

Reads local files only, bounded; nothing of the client runs.

    python tools/armor_layer_audit.py --geometry DIR --chassis DIR --out REPORT.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT / "config" / "catalog" / "battle_profiles.v1.json"
MAX_BUNDLE = 4 * 1024 * 1024
GRID = (0.2, 0.35, 0.5, 0.65, 0.8)
SCHEMA = "wot091-armor-layer-audit.v1"


class AuditError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise AuditError(message)


def read_pinned(path, sha256=None):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_BUNDLE, "bundle file: " + str(path))
    raw = path.read_bytes()
    if sha256 is not None:
        require(hashlib.sha256(raw).hexdigest() == sha256, "bundle SHA differs from the table: " + path.name)
    return json.loads(raw)


def sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def cross(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
def dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def component_mesh(part):
    roles = {}
    for m in part["materials"]:
        e = m.get("effective") or {}
        kind = m["kind"]
        if kind in (23, 24):
            role = "track"
        elif e.get("damageKind", e.get("damage_kind")) == 1:
            role = "device"
        elif (e.get("vehicleDamageFactor") or 0) > 0:
            role = "main"
        else:
            role = "spaced"
        roles[m["name"]] = role
    vertices = [tuple(float(x) for x in v[:3]) for v in part["vertices"]]
    excluded = set(part.get("excluded_degenerate_triangle_ids", []))
    tris = [(t["a"], t["b"], t["c"], roles.get(t["material"], "unknown")) for t in part["triangles"] if t["triangle_id"] not in excluded]
    return vertices, tris


def topology(vertices, tris):
    """Edges keyed by welded positions (the same point may repeat with other uv/normal)."""
    key = {}
    for i, v in enumerate(vertices):
        key[i] = tuple(round(x, 5) for x in v)
    directed = Counter()
    undirected = Counter()
    for a, b, c, _ in tris:
        for u, w in ((a, b), (b, c), (c, a)):
            ku, kw = key[u], key[w]
            if ku == kw:
                continue
            directed[(ku, kw)] += 1
            undirected[frozenset((ku, kw))] += 1
    boundary = sum(1 for n in undirected.values() if n == 1)
    nonmanifold = sum(1 for n in undirected.values() if n > 2)
    inconsistent = sum(1 for (u, w), n in directed.items() if n > 1 or directed.get((w, u), 0) == 0 and undirected[frozenset((u, w))] == 2)
    return boundary, nonmanifold, inconsistent


def signed_volume(vertices, tris):
    return sum(dot(vertices[a], cross(vertices[b], vertices[c])) for a, b, c, _ in tris) / 6.0


def first_hit(vertices, tris, start, end):
    d = sub(end, start)
    best = None
    for a, b, c, role in tris:
        p0, p1, p2 = vertices[a], vertices[b], vertices[c]
        e1, e2 = sub(p1, p0), sub(p2, p0)
        p = cross(d, e2)
        det = dot(e1, p)
        if abs(det) < 1e-12:
            continue
        inv = 1.0 / det
        s = sub(start, p0)
        u = dot(s, p) * inv
        if u < 0 or u > 1:
            continue
        q = cross(s, e1)
        v = dot(d, q) * inv
        if v < 0 or u + v > 1:
            continue
        t = dot(e2, q) * inv
        if 0 <= t <= 1 and (best is None or t < best[0]):
            best = (t, dot(d, cross(e1, e2)), role)
    return best


def outward_test(vertices, tris):
    used = [vertices[i] for a, b, c, _ in tris for i in (a, b, c)]
    lo = [min(v[i] for v in used) for i in range(3)]
    hi = [max(v[i] for v in used) for i in range(3)]
    margin = max(hi[i] - lo[i] for i in range(3)) + 1.0
    against = along = 0
    by_role = Counter()
    for axis in range(3):
        others = [i for i in range(3) if i != axis]
        for u in GRID:
            for w in GRID:
                point = [0.0, 0.0, 0.0]
                point[others[0]] = lo[others[0]] + (hi[others[0]] - lo[others[0]]) * u
                point[others[1]] = lo[others[1]] + (hi[others[1]] - lo[others[1]]) * w
                for sign in (-1, 1):
                    start, end = list(point), list(point)
                    start[axis] = (lo[axis] - margin) if sign < 0 else (hi[axis] + margin)
                    end[axis] = (lo[axis] + hi[axis]) / 2
                    hit = first_hit(vertices, tris, tuple(start), tuple(end))
                    if hit is None:
                        continue
                    if hit[1] < 0:
                        against += 1
                        by_role[hit[2] + ":against"] += 1
                    else:
                        along += 1
                        by_role[hit[2] + ":along"] += 1
    return against, along, dict(sorted(by_role.items()))


def audit_part(name, part):
    vertices, tris = component_mesh(part)
    require(0 < len(tris) <= 65536, "triangle bound")
    boundary, nonmanifold, inconsistent = topology(vertices, tris)
    roles = Counter(t[3] for t in tris)
    sub_closed = {}
    for role in sorted(roles):
        sub_tris = [t for t in tris if t[3] == role]
        b, n, _ = topology(vertices, sub_tris)
        sub_closed[role] = b == 0 and n == 0
    against, along, by_role = outward_test(vertices, tris)
    closed = boundary == 0 and nonmanifold == 0
    return dict(component=name, triangles=len(tris), roles=dict(sorted(roles.items())), closed=closed,
                boundary_edges=boundary, nonmanifold_edges=nonmanifold, inconsistent_edges=inconsistent,
                signed_volume=round(signed_volume(vertices, tris), 6), role_closed=sub_closed,
                first_hit_against_winding=against, first_hit_along_winding=along, first_hit_by_role=by_role)


def audit(geometry_dir, chassis_dir):
    table = json.loads(TABLE.read_bytes())
    rows = [r for r in table["vehicles"] if r["status"] == "generated"]
    require(len(rows) == 232, "main table battle rows: %d" % len(rows))
    out = []
    for row in rows:
        geo = read_pinned(Path(geometry_dir) / row["geometry"]["bundle"], row["geometry"]["sha256"])
        parts = [(c["name"], c) for c in geo["geometry"]["components"]]
        chassis_path = Path(chassis_dir) / row["geometry"]["bundle"]
        if chassis_path.is_file():
            parts.insert(0, ("Chassis", read_pinned(chassis_path)["component"]))
        out.append(dict(kind=row["kind"], vehicle_id=row["vehicle_id"], parts=[audit_part(n, p) for n, p in parts]))
    return out


def summary(vehicles):
    s = Counter()
    for v in vehicles:
        for p in v["parts"]:
            c = p["component"].split("_")[0]
            s[c + ":parts"] += 1
            s[c + ":closed"] += p["closed"]
            s[c + ":consistent"] += p["inconsistent_edges"] == 0
            s[c + ":all_first_hits_against"] += p["first_hit_along_winding"] == 0 and p["first_hit_against_winding"] > 0
            s[c + ":all_first_hits_along"] += p["first_hit_against_winding"] == 0 and p["first_hit_along_winding"] > 0
            for role in p["roles"]:
                s[c + ":has_" + role] += 1
            for role, closed in p["role_closed"].items():
                s[c + ":" + role + "_closed"] += closed
    return dict(sorted(s.items()))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--geometry", required=True)
    parser.add_argument("--chassis", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    out = Path(args.out)
    require(not out.exists(), "fresh report path required")
    vehicles = audit(args.geometry, args.chassis)
    report = dict(schema=SCHEMA, table_sha256=hashlib.sha256(TABLE.read_bytes()).hexdigest(), vehicles=len(vehicles),
                  summary=summary(vehicles), details=vehicles)
    out.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
