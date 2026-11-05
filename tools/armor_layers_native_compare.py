"""SHELL-01 step 5: compare native #717 collideSegment answers with the project armour meshes.

Input: a client trace (JSON lines) holding `armor_layers_*` records of
client_patch/armor_layers_probe.py, the chassis bundles of
tools/chassis_armor_export.py and the BATTLE-ANY geometry bundles. For every
recorded component-local segment the project mesh of the same component is
intersected (every triangle the segment crosses, Moeller-Trumbore, t in [0, 1])
and compared with the native hit list: count, distance, |cos| and material kind.

Reads local files only; bounded sizes and counts; no client code runs here.

    python tools/armor_layers_native_compare.py --trace T.jsonl --chassis DIR --geometry DIR --out REPORT.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

SCHEMA = "wot091-armor-layers-native-compare.v1"
MAX_TRACE = 64 * 1024 * 1024
MAX_BUNDLE = 4 * 1024 * 1024
MAX_LINE = 70000
DISTANCE_TOL = 1e-3
COS_TOL = 1e-3
EDGE_TOL = 1e-5
EPS = 1e-12
GEOMETRY_INDEX = {"hull": 0, "turret": 1, "gun": 2}


class CompareError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise CompareError(message)


def read(path, limit):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), "plain file required: " + str(path))
    require(path.stat().st_size <= limit, "file bound: " + str(path))
    return path.read_bytes()


def trace_records(path):
    raw = read(path, MAX_TRACE)
    out = []
    for line in raw.splitlines():
        require(len(line) <= MAX_LINE, "trace line bound")
        if b'"armor_layers_' not in line:
            continue
        value = json.loads(line)
        if str(value.get("event", "")).startswith("armor_layers_"):
            out.append(value)
    require(out, "no armor_layers records in trace")
    return out


def mesh(component):
    """(triangles [(a, b, c, kind, id)], vertex positions) of one bundle component."""
    kinds = {m["name"]: m["kind"] for m in component["materials"]}
    vertices = [tuple(float(x) for x in v[:3]) for v in component["vertices"]]
    excluded = set(component.get("excluded_degenerate_triangle_ids", []))
    triangles = []
    for t in component["triangles"]:
        if t["triangle_id"] in excluded:
            continue
        require(t["material"] in kinds, "triangle material without kind")
        triangles.append((vertices[t["a"]], vertices[t["b"]], vertices[t["c"]], kinds[t["material"]], t["triangle_id"]))
    require(0 < len(triangles) <= 65536, "mesh triangle bound")
    return triangles


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def segment_hits(triangles, start, end):
    """Every triangle crossing; [distance, cos(direction, face normal), kind, id] by distance."""
    d = sub(end, start)
    length = math.sqrt(dot(d, d))
    require(length > 0, "zero segment")
    unit = (d[0] / length, d[1] / length, d[2] / length)
    hits = []
    for a, b, c, kind, tid in triangles:
        e1, e2 = sub(b, a), sub(c, a)
        p = cross(d, e2)
        det = dot(e1, p)
        if abs(det) < EPS:
            continue
        inv = 1.0 / det
        s = sub(start, a)
        u = dot(s, p) * inv
        if u < 0 or u > 1:
            continue
        q = cross(s, e1)
        v = dot(d, q) * inv
        if v < 0 or u + v > 1:
            continue
        t = dot(e2, q) * inv
        if t < 0 or t > 1:
            continue
        n = cross(e1, e2)
        nl = math.sqrt(dot(n, n))
        hits.append([t * length, dot(unit, n) / nl if nl else 0.0, kind, tid])
    return sorted(hits, key=lambda h: (h[0], h[3]))


def collapse(hits):
    """Order by distance and merge a hit repeated at the same distance with the same
    material: a segment through the shared edge of two triangles. Native collideSegment
    returns its hits in BSP order (not along the ray) and reports both triangles."""
    out, merged = [], 0
    for hit in sorted(hits, key=lambda h: h[0]):
        if out and abs(out[-1][0] - hit[0]) <= EDGE_TOL and out[-1][2] == hit[2]:
            merged += 1
            continue
        out.append(hit)
    return out, merged


def compare_ray(native, project):
    if len(native) != len(project):
        return "count"
    for (nd, nc, nk), (pd, pc, pk, _) in zip(native, project):
        if abs(nd - pd) > DISTANCE_TOL:
            return "distance"
        if nk != pk:
            return "material"
        if abs(abs(nc) - abs(pc)) > COS_TOL:
            return "angle"
    return None


def bundle(path):
    return json.loads(read(path, MAX_BUNDLE))


def compare(records, chassis_dir, geometry_dir):
    components = {}
    for r in records:
        if r["event"] == "armor_layers_rays":
            components.setdefault((r["vehicle"], r["component"]), []).extend(r["rays"])
    require(components, "no ray records")
    report, meshes = [], {}
    for (vehicle, component), rays in sorted(components.items()):
        nation, name = vehicle.split(":", 1)
        stem = nation + "-" + name + ".json"
        if component == "chassis":
            source = Path(chassis_dir) / stem
            part = bundle(source)["component"]
        else:
            source = Path(geometry_dir) / stem
            part = bundle(source)["geometry"]["components"][GEOMETRY_INDEX[component]]
        triangles = meshes.setdefault((vehicle, component), mesh(part))
        counts = {"equal": 0, "count": 0, "distance": 0, "material": 0, "angle": 0}
        merged = {"native": 0, "project": 0}
        cos_sign = {"same": 0, "opposite": 0}
        examples = []
        for ray in rays:
            native, n_merged = collapse(ray["hits"])
            project, p_merged = collapse(segment_hits(triangles, tuple(ray["start"]), tuple(ray["end"])))
            merged["native"] += n_merged
            merged["project"] += p_merged
            verdict = compare_ray(native, project)
            counts[verdict or "equal"] += 1
            if verdict is None:
                for (_, nc, _), (_, pc, _, _) in zip(native, project):
                    cos_sign["same" if (nc >= 0) == (pc >= 0) else "opposite"] += 1
            elif len(examples) < 8:
                examples.append(dict(start=ray["start"], end=ray["end"], verdict=verdict, native=native,
                                     project=[[round(h[0], 6), round(h[1], 6), h[2]] for h in project]))
        report.append(dict(vehicle=vehicle, component=component, mesh=part.get("name"),
                           source=str(source), source_sha256=hashlib.sha256(read(source, MAX_BUNDLE)).hexdigest(),
                           rays=len(rays), native_hits=sum(len(r["hits"]) for r in rays), triangles=len(triangles),
                           verdicts=counts, cos_sign=cos_sign, edge_duplicates_merged=merged, examples=examples))
    calibers = [r for r in records if r["event"] == "armor_layers_calibers"]
    return dict(schema=SCHEMA, tolerance=dict(distance_m=DISTANCE_TOL, abs_cos=COS_TOL), components=report,
                calibers=calibers, all_equal=all(c["verdicts"]["equal"] == c["rays"] for c in report),
                classification="native collideSegment vs project mesh; local copy, diagnostic Hangar read only")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--trace", required=True)
    parser.add_argument("--chassis", required=True)
    parser.add_argument("--geometry", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    out = Path(args.out)
    require(not out.exists(), "fresh report path required")
    result = compare(trace_records(args.trace), args.chassis, args.geometry)
    out.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"all_equal": result["all_equal"], "components": [
        [c["vehicle"], c["component"], c["rays"], c["verdicts"]] for c in result["components"]]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
