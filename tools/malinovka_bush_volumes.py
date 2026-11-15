"""Build local project-calibrated bush ellipsoids from the pinned #717 audit.

This creates no historical concealment assertion and does not enable combat
integration. Raw client resources are never emitted; output is a local receipt.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

if __package__:
    from .malinovka_bush_audit import MAP_PIN, SHARED_PIN, RESOURCE_PINS, audit
    from .map_package import no_links, transformed
else:
    from malinovka_bush_audit import MAP_PIN, SHARED_PIN, RESOURCE_PINS, audit
    from map_package import no_links, transformed

ROOT = Path(__file__).resolve().parents[1]
CALIBRATION = ROOT / "tools" / "malinovka_bush_calibration.v1.json"
SCHEMA = "content0-s5a-malinovka-bush-calibration.v1"
CLASS = "PROJECT_CALIBRATION_NOT_HISTORICAL"


def _unique(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate JSON key")
        out[key] = value
    return out


def _constant(_):
    raise ValueError("non-finite JSON constant")


def _vector(value, low, high):
    if (type(value) is not list or len(value) != 3 or
            any(type(x) not in (int, float) or not math.isfinite(x) or not low <= x <= high for x in value)):
        raise ValueError("calibration vector bounds")
    return value


def parse_calibration(raw):
    if type(raw) is not bytes or not 0 < len(raw) <= 65536:
        raise ValueError("calibration size")
    doc = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique, parse_constant=_constant)
    if (type(doc) is not dict or set(doc) != {"schema", "classification", "description", "resources", "fire_near_distance_m", "fire_near_multiplier"}
            or doc["schema"] != SCHEMA or doc["classification"] != CLASS
            or type(doc["description"]) is not str or not 0 < len(doc["description"]) <= 1024
            or type(doc["resources"]) is not dict or set(doc["resources"]) != set(RESOURCE_PINS)):
        raise ValueError("calibration schema")
    for key, high in (("fire_near_distance_m", 1000), ("fire_near_multiplier", 1)):
        value = doc[key]
        if type(value) not in (float, int) or not math.isfinite(value) or not 0 <= value <= high:
            raise ValueError("fire calibration bound")
    for entry in doc["resources"].values():
        if type(entry) is not dict or set(entry) != {"center_local", "radii_local", "concealment_additive"}:
            raise ValueError("calibration resource fields")
        _vector(entry["center_local"], -100, 100)
        _vector(entry["radii_local"], 0.01, 100)
        coef = entry["concealment_additive"]
        if type(coef) not in (int, float) or not math.isfinite(coef) or not 0 <= coef <= 1:
            raise ValueError("calibration coefficient")
    return doc


def determinant(m):
    return (m[0][0]*(m[1][1]*m[2][2]-m[1][2]*m[2][1])
            - m[0][1]*(m[1][0]*m[2][2]-m[1][2]*m[2][0])
            + m[0][2]*(m[1][0]*m[2][1]-m[1][1]*m[2][0]))


def volume(instance, setting):
    m = instance["transform"]
    if type(m) is not list or len(m) != 12 or any(type(x) not in (int, float) or not math.isfinite(x) or abs(x) > 10000 for x in m):
        raise ValueError("source transform bound")
    chunk = instance["chunk"]
    if type(chunk) is not list or len(chunk) != 2 or any(type(x) is not int or abs(x) > 64 for x in chunk):
        raise ValueError("source chunk bound")
    center = list(transformed(setting["center_local"], m, chunk))
    # Row-vector convention: world = center + u[0]*basis[0] + ...,
    # where dot(u,u) <= 1. This retains all original rotation, scale and shear.
    basis = [[setting["radii_local"][i] * m[3*i+j] for j in range(3)] for i in range(3)]
    det = determinant(basis)
    if not math.isfinite(det) or abs(det) < 1e-8:
        raise ValueError("degenerate calibrated ellipsoid")
    extents = [math.sqrt(sum(basis[i][j] ** 2 for i in range(3))) for j in range(3)]
    if (any(not math.isfinite(x) or abs(x) > 10000 for x in center) or
            any(not math.isfinite(x) or not 0 < x <= 1000 for x in extents)):
        raise ValueError("world ellipsoid bound")
    return {"chunk": chunk, "speedtree_index": instance["speedtree_index"],
            "resource": instance["resource"], "seed": instance["seed"],
            "center_world": center, "basis_world_rows": basis,
            "aabb_half_extents_world": extents,
            "concealment_additive": setting["concealment_additive"]}


def build(receipt, raw_calibration):
    pins = {k: {"bytes": v[0], "sha256": v[1]} for k, v in RESOURCE_PINS.items()}
    if (receipt.get("schema") != "content0-s5a-malinovka-bush-inventory.v1" or
            receipt.get("map_package_pin") != MAP_PIN or receipt.get("shared_package_pin") != SHARED_PIN or
            receipt.get("selected_resource_pins") != pins or
            type(receipt.get("chunk_pins")) is not list or len(receipt["chunk_pins"]) != 144 or
            type(receipt.get("instances")) is not list or not 0 < len(receipt["instances"]) <= 1024):
        raise ValueError("source inventory schema/count")
    calibration = parse_calibration(raw_calibration)
    rows = []
    keys = set()
    for instance in receipt["instances"]:
        key = (tuple(instance["chunk"]), instance["speedtree_index"])
        if key in keys:
            raise ValueError("duplicate source instance")
        keys.add(key)
        resource = instance["resource"]
        if resource not in calibration["resources"]:
            raise ValueError("unknown source resource")
        rows.append(volume(instance, calibration["resources"][resource]))
    return {"schema": "content0-s5a-malinovka-bush-volumes.v1", "map": "02_malinovka",
            "classification": CLASS, "calibration_schema": SCHEMA,
            "calibration_sha256": hashlib.sha256(raw_calibration).hexdigest(),
            "fire_near_distance_m": calibration["fire_near_distance_m"],
            "fire_near_multiplier": calibration["fire_near_multiplier"],
            "map_package_pin": receipt["map_package_pin"], "shared_package_pin": receipt["shared_package_pin"],
            "selected_resource_pins": receipt["selected_resource_pins"], "chunk_pins": receipt["chunk_pins"],
            "geometry_contract": "unit u: world=center_world+sum(u[i]*basis_world_rows[i]); dot(u,u)<=1",
            "aabb_contract": "center_world +/- aabb_half_extents_world contains the calibrated ellipsoid",
            "effect_contract": "project v1: max crossed shrub; during fire window multiply near shrubs by fire_near_multiplier; near means distance from ray exit to target point <= fire_near_distance_m",
            "instances": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    out = no_links(args.out).resolve(strict=False)
    evidence = (ROOT / "local" / "evidence").resolve(strict=True)
    if not out.is_relative_to(evidence) or out.suffix != ".json" or not out.parent.is_dir():
        raise ValueError("output must be a new JSON file under local/evidence")
    raw = no_links(CALIBRATION).read_bytes()
    result = build(audit(args.original), raw)
    encoded = (json.dumps(result, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(",", ":")) + "\n").encode("ascii")
    with out.open("xb") as stream:
        stream.write(encoded)
    print(json.dumps({"output": str(out), "sha256": hashlib.sha256(encoded).hexdigest(), "instances": len(result["instances"])}))


if __name__ == "__main__":
    main()
