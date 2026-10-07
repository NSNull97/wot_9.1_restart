"""Audit the bounded static #717 research graph without opening the client.

The web catalogue is a reference dataset.  This tool checks its hash binding,
record/edge shape, tier coverage and the observed IS-8 -> IS-7 direction.  It
does not read account/shop payloads and never claims native tree visibility.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any


MAX_BYTES = 16 * 1024 * 1024
MAX_DEPTH = 32
MAX_VEHICLES = 512
MAX_NODES_PER_TREE = 512
MAX_EDGES_PER_TREE = 2048
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
NODE_KINDS = {"chassis", "engine", "radio", "turret", "gun", "vehicle"}


class ResearchTreeAuditError(ValueError):
    """The static catalogue is malformed or outside the pinned contract."""


def _reject_constant(value: str) -> Any:
    raise ResearchTreeAuditError(f"non-finite JSON constant: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ResearchTreeAuditError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _depth(value: Any, level: int = 0) -> None:
    if level > MAX_DEPTH:
        raise ResearchTreeAuditError("JSON nesting exceeds bounds")
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ResearchTreeAuditError("JSON object key must be text")
            _depth(child, level + 1)
    elif isinstance(value, list):
        for child in value:
            _depth(child, level + 1)


def _read_json(path: str | Path) -> tuple[dict[str, Any], str]:
    candidate = Path(path).absolute()
    if candidate.is_symlink() or getattr(candidate, "is_junction", lambda: False)():
        raise ResearchTreeAuditError("source links are forbidden")
    try:
        info = candidate.stat()
    except OSError as error:
        raise ResearchTreeAuditError(f"source is not readable: {candidate}") from error
    if not candidate.is_file() or info.st_size <= 0 or info.st_size > MAX_BYTES:
        raise ResearchTreeAuditError("source size/type is outside bounds")
    raw = candidate.read_bytes()
    if len(raw) != info.st_size:
        raise ResearchTreeAuditError("source changed while reading")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                           parse_constant=_reject_constant)
    except ResearchTreeAuditError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise ResearchTreeAuditError("source must be bounded UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise ResearchTreeAuditError("source root must be an object")
    _depth(value)
    return value, hashlib.sha256(raw).hexdigest()


def _keys(value: dict[str, Any], required: set[str], optional: set[str], label: str) -> None:
    missing = required - set(value)
    unknown = set(value) - required - optional
    if missing:
        raise ResearchTreeAuditError(f"{label}: missing fields {sorted(missing)}")
    if unknown:
        raise ResearchTreeAuditError(f"{label}: unknown fields {sorted(unknown)}")


def _id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise ResearchTreeAuditError(f"{label}: invalid bounded ID")
    return value


def _integer(value: Any, label: str, lower: int, upper: int) -> int:
    if type(value) is not int or not lower <= value <= upper:
        raise ResearchTreeAuditError(f"{label}: integer outside bounds")
    return value


def _finite_number(value: Any, label: str) -> int | float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ResearchTreeAuditError(f"{label}: finite number required")
    return value


def audit(catalog_path: str | Path, research_path: str | Path) -> dict[str, Any]:
    catalog, catalog_sha256 = _read_json(catalog_path)
    research, research_sha256 = _read_json(research_path)
    _keys(catalog, {"schemaVersion", "build", "namingVersion", "vehicleCount", "mapCount", "vehicles", "maps"}, set(), "catalog")
    if catalog["schemaVersion"] != "static-catalog.v1" or catalog["build"] != "0.9.1 #717":
        raise ResearchTreeAuditError("catalog schema/build is outside #717 scope")
    catalog_rows = catalog["vehicles"]
    if not isinstance(catalog_rows, list) or not 1 <= len(catalog_rows) <= MAX_VEHICLES:
        raise ResearchTreeAuditError("catalog vehicles list is outside bounds")
    if catalog["vehicleCount"] != len(catalog_rows):
        raise ResearchTreeAuditError("catalog vehicleCount does not match rows")
    catalog_by_id: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(catalog_rows):
        if not isinstance(row, dict):
            raise ResearchTreeAuditError(f"catalog.vehicles[{index}]: object required")
        vehicle_id = _id(row.get("id"), f"catalog.vehicles[{index}].id")
        if vehicle_id in catalog_by_id:
            raise ResearchTreeAuditError(f"duplicate catalogue vehicle: {vehicle_id}")
        if not isinstance(row.get("nation"), str) or not row["nation"]:
            raise ResearchTreeAuditError(f"catalog.vehicles[{index}].nation: text required")
        _integer(row.get("tier"), f"catalog.vehicles[{index}].tier", 1, 10)
        catalog_by_id[vehicle_id] = row

    _keys(research, {"schemaVersion", "build", "factsSha256", "vehicles"}, set(), "research")
    if research["schemaVersion"] != "catalog-research.v1" or research["build"] != "0.9.1 #717":
        raise ResearchTreeAuditError("research schema/build is outside #717 scope")
    if research["factsSha256"] != catalog_sha256:
        raise ResearchTreeAuditError("research factsSha256 does not match catalog")
    trees = research["vehicles"]
    if not isinstance(trees, dict) or not 1 <= len(trees) <= MAX_VEHICLES:
        raise ResearchTreeAuditError("research vehicle map is outside bounds")
    if set(trees) != set(catalog_by_id):
        raise ResearchTreeAuditError("research and catalogue vehicle sets differ")

    total_nodes = total_edges = 0
    vehicle_edges: dict[str, list[dict[str, Any]]] = {}
    for vehicle_id, tree in trees.items():
        _id(vehicle_id, "research vehicle ID")
        if not isinstance(tree, dict):
            raise ResearchTreeAuditError(f"research[{vehicle_id}]: object required")
        _keys(tree, {"price", "nodes", "edges", "source"}, set(), f"research[{vehicle_id}]")
        if not isinstance(tree["source"], str) or not tree["source"].startswith("res/scripts/"):
            raise ResearchTreeAuditError(f"research[{vehicle_id}].source: pinned client path required")
        nodes = tree["nodes"]
        edges = tree["edges"]
        if not isinstance(nodes, list) or len(nodes) > MAX_NODES_PER_TREE:
            raise ResearchTreeAuditError(f"research[{vehicle_id}].nodes: outside bounds")
        if not isinstance(edges, list) or len(edges) > MAX_EDGES_PER_TREE:
            raise ResearchTreeAuditError(f"research[{vehicle_id}].edges: outside bounds")
        node_ids: set[str] = set()
        for index, node in enumerate(nodes):
            if not isinstance(node, dict):
                raise ResearchTreeAuditError(f"research[{vehicle_id}].nodes[{index}]: object required")
            _keys(node, {"id", "kind", "key", "name", "level", "price"}, {"vehicleId", "weightKg", "turrets", "maxLoadKg", "rotation", "terrainResistance", "power", "fireChance", "range"}, f"research[{vehicle_id}].nodes[{index}]")
            node_id = _id(node["id"], f"research[{vehicle_id}].nodes[{index}].id")
            if node_id in node_ids:
                raise ResearchTreeAuditError(f"research[{vehicle_id}]: duplicate node {node_id}")
            node_ids.add(node_id)
            if node["kind"] not in NODE_KINDS:
                raise ResearchTreeAuditError(f"research[{vehicle_id}].nodes[{index}].kind: unsupported")
            _integer(node["level"], f"research[{vehicle_id}].nodes[{index}].level", 1, 10)
            if node["kind"] != "vehicle" and "weightKg" not in node:
                raise ResearchTreeAuditError(f"research[{vehicle_id}].nodes[{index}].weightKg: required for module nodes")
            if "weightKg" in node:
                _finite_number(node["weightKg"], f"research[{vehicle_id}].nodes[{index}].weightKg")
            if node["kind"] == "vehicle":
                target_id = _id(node.get("vehicleId"), f"research[{vehicle_id}].nodes[{index}].vehicleId")
                if target_id not in catalog_by_id:
                    raise ResearchTreeAuditError(f"research[{vehicle_id}]: unknown vehicle node {target_id}")
        seen_edges: set[tuple[str, str, int | float]] = set()
        outgoing_vehicle_edges: list[dict[str, Any]] = []
        for index, edge in enumerate(edges):
            if not isinstance(edge, dict):
                raise ResearchTreeAuditError(f"research[{vehicle_id}].edges[{index}]: object required")
            _keys(edge, {"from", "to", "xp"}, set(), f"research[{vehicle_id}].edges[{index}]")
            source = _id(edge["from"], f"research[{vehicle_id}].edges[{index}].from")
            target = _id(edge["to"], f"research[{vehicle_id}].edges[{index}].to")
            xp = _integer(edge["xp"], f"research[{vehicle_id}].edges[{index}].xp", 0, 2_000_000_000)
            if source not in node_ids:
                raise ResearchTreeAuditError(f"research[{vehicle_id}]: edge source is not a node")
            if target.startswith("vehicle-"):
                target_vehicle = target.removeprefix("vehicle-")
                if target_vehicle not in catalog_by_id:
                    raise ResearchTreeAuditError(f"research[{vehicle_id}]: unknown edge vehicle {target_vehicle}")
                outgoing_vehicle_edges.append(edge)
            elif target not in node_ids:
                raise ResearchTreeAuditError(f"research[{vehicle_id}]: edge target is not a node")
            identity = (source, target, xp)
            if identity in seen_edges:
                raise ResearchTreeAuditError(f"research[{vehicle_id}]: duplicate edge")
            seen_edges.add(identity)
        total_nodes += len(nodes)
        total_edges += len(edges)
        vehicle_edges[vehicle_id] = outgoing_vehicle_edges

    ussr_ids = [vehicle_id for vehicle_id, row in catalog_by_id.items() if row["nation"] == "ussr"]
    ussr_tiers = sorted({catalog_by_id[vehicle_id]["tier"] for vehicle_id in ussr_ids})
    if ussr_tiers != list(range(1, 11)):
        raise ResearchTreeAuditError(f"USSR tier coverage differs: {ussr_tiers}")
    is8_edges = [edge for edge in vehicle_edges["ussr-is8"] if edge["to"] == "vehicle-ussr-is-7"]
    if len(is8_edges) != 1 or vehicle_edges["ussr-is-7"]:
        raise ResearchTreeAuditError("IS-8 -> IS-7 direction or terminal IS-7 invariant failed")
    return {
        "status": "PASS_STATIC_RESEARCH_TREE_GRAPH",
        "schema": "catalog-research.v1",
        "build": "0.9.1 #717",
        "catalog_sha256": catalog_sha256,
        "research_sha256": research_sha256,
        "tree_count": len(trees),
        "node_count": total_nodes,
        "edge_count": total_edges,
        "ussr_vehicle_count": len(ussr_ids),
        "ussr_tiers": ussr_tiers,
        "is8_to_is7": True,
        "is7_vehicle_edges": 0,
        "native_visibility": "NOT_RUN",
        "native_shop_payload": "NOT_RUN",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", required=True, help="catalog.v1.json")
    parser.add_argument("--research", required=True, help="catalog-research.v1.json")
    parser.add_argument("--out", help="optional bounded JSON receipt")
    args = parser.parse_args()
    try:
        report = audit(args.catalog, args.research)
        if args.out:
            output = Path(args.out).absolute()
            if output.is_symlink() or getattr(output, "is_junction", lambda: False)():
                raise ResearchTreeAuditError("output links are forbidden")
            output.parent.mkdir(parents=True, exist_ok=True)
            raw = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            if len(raw) > 64 * 1024:
                raise ResearchTreeAuditError("receipt exceeds output bound")
            output.write_bytes(raw + b"\n")
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    except (ResearchTreeAuditError, OSError) as error:
        raise SystemExit(f"research tree audit rejected: {error}")


if __name__ == "__main__":
    main()
