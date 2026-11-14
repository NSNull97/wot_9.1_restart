"""Build a bounded, local-only, static #717 Soviet vehicle/texture census.

Reads client package bytes, never executes client code or writes into a client.
DDS alpha results are values in the largest mip, not material semantics.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from collections import Counter
from pathlib import Path

from tools.visual02_dds import DDSError, MAX_FILE_BYTES, inspect_dds
from tools.visual02_paths import safe_evidence_output
from tools.visual02_vehicle_mapping import build_mapping

MAX_TOTAL_DDS = 2 * 1024 * 1024 * 1024
MAX_OUTPUT = 128 * 1024 * 1024
ROLES = {"diffuseMap": "diffuse", "normalMap": "normal",
         "metallicGlossMap": "metallic_gloss", "specularMap": "specular",
         "metallicDetailMap": "metallic_detail"}


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _role(label):
    return ROLES.get(label, "other_or_unknown")


def _walk_models(model):
    depth = 0
    while model:
        if depth >= 17:
            raise ValueError("model parent chain exceeds bound")
        yield model
        model = model.get("parent")
        depth += 1


def collect_bindings(mapping):
    """Collapse repeated model references while preserving evidence of each binding."""
    vehicles = []
    textures = {}
    for vehicle in mapping["vehicles"]:
        vehicle_id = vehicle["vehicle_id"]
        observations = {}
        problems = list(vehicle.get("unresolved", []))
        for root in vehicle["models"]:
            for model in _walk_models(root["model"]):
                problems.extend(model.get("unresolved", []))
                for visual_entry in model.get("visuals", []):
                    visual = visual_entry["visual"]
                    problems.extend(visual.get("unresolved", []))
                    for prop in visual.get("properties", []):
                        name = prop.get("texture")
                        label = prop.get("property_as_string")
                        if prop.get("unresolved") or not isinstance(name, str) or not name:
                            problems.append({"reason": prop.get("unresolved", "invalid_texture"),
                                             "visual": visual["resource"], "property": label,
                                             "texture": name})
                            continue
                        key = (name.casefold(), str(label), visual["resource"].casefold(),
                               model["resource"].casefold(), root["source_path"])
                        observations[key] = {"texture": name, "property": label, "role": _role(label),
                                             "model": model["resource"], "visual": visual["resource"],
                                             "vehicle_xml_path": root["source_path"]}
                        item = textures.setdefault(name.casefold(), {"resource": name,
                                                  "provenance": prop["provenance"], "uses": set()})
                        provenance_fields = ("archive", "member", "bytes", "crc32", "shadowed_archives")
                        if any(item["provenance"][k] != prop["provenance"][k] for k in provenance_fields):
                            raise ValueError("inconsistent texture resolution: " + name)
                        item["uses"].add((vehicle_id, str(label), _role(label)))
        # Repeated parts may report the same problem: retain one explicit occurrence.
        unique_problems = {json.dumps(x, ensure_ascii=True, sort_keys=True): x for x in problems}
        vehicles.append({"vehicle_id": vehicle_id, "resource_name": vehicle["resource_name"],
                         "tier": vehicle["tier"], "tags": vehicle["tags"],
                         "secret": vehicle["secret"], "not_in_shop": vehicle["not_in_shop"],
                         "reachable_from_ms1_in_client_research_graph": vehicle["reachable_from_ms1_in_client_research_graph"],
                         "tree_ui_visibility": vehicle["tree_ui_visibility"], "source": vehicle["source"],
                         "bindings": sorted(observations.values(), key=lambda x: tuple(str(x[k]) for k in
                                            ("texture", "property", "model", "visual", "vehicle_xml_path"))),
                         "unresolved": [unique_problems[k] for k in sorted(unique_problems)]})
    return vehicles, textures


def build_inventory(client_root):
    root = Path(client_root).resolve(strict=True)
    mapping = build_mapping(root)
    vehicles, textures = collect_bindings(mapping)
    packages = {}
    total = 0
    try:
        for item in textures.values():
            prov = item["provenance"]
            rel, member, size = prov["archive"], prov["member"], prov["bytes"]
            if rel not in mapping["packages"] or not isinstance(size, int) or not 0 <= size <= MAX_FILE_BYTES:
                raise ValueError("invalid texture package or size: " + item["resource"])
            if rel not in packages:
                packages[rel] = zipfile.ZipFile(root / rel)
            archive = packages[rel]
            info = archive.getinfo(member)
            if info.file_size != size or f"{info.CRC:08x}" != prov["crc32"]:
                raise ValueError("texture metadata changed: " + item["resource"])
            if info.file_size > max(1024, info.compress_size * 2000):
                raise ValueError("texture compression ratio bound: " + item["resource"])
            total += info.file_size
            if total > MAX_TOTAL_DDS:
                raise ValueError("total texture read bound")
            raw = archive.read(info)
            if len(raw) != size:
                raise ValueError("texture payload truncated: " + item["resource"])
            item["sha256"] = _sha(raw)
            if item["resource"].lower().endswith(".dds"):
                try:
                    item["dds"] = inspect_dds(raw)
                    item["inspection"] = "PASS"
                except DDSError as exc:
                    item["dds"] = None
                    item["inspection"] = "UNSUPPORTED_OR_INVALID"
                    item["inspection_error"] = str(exc)
            else:
                item["dds"] = None
                item["inspection"] = "NON_DDS_NOT_INSPECTED"
            item["uses"] = [{"vehicle_id": v, "property": p, "role": role}
                            for v, p, role in sorted(item["uses"])]
    finally:
        for archive in packages.values():
            archive.close()
    rows = sorted(textures.values(), key=lambda x: x["resource"].casefold())
    tree_ids = {v["vehicle_id"] for v in vehicles if v["reachable_from_ms1_in_client_research_graph"]}
    tree_textures = [x for x in rows if any(u["vehicle_id"] in tree_ids for u in x["uses"])]
    tree_diffuse = [x for x in tree_textures if any(u["vehicle_id"] in tree_ids and u["role"] == "diffuse" for u in x["uses"])]
    def counts(items):
        return {"textures": len(items),
                "inspection": dict(sorted(Counter(x["inspection"] for x in items).items())),
                "formats": dict(sorted(Counter((x["dds"] or {}).get("format", "UNKNOWN") for x in items).items())),
                "alpha_top": dict(sorted(Counter("UNKNOWN" if not x["dds"] else
                    "opaque_only" if x["dds"]["alpha_values_top_mip"] == [255] else
                    "binary" if set(x["dds"]["alpha_values_top_mip"]).issubset({0, 255}) else
                    "multiple_values" for x in items).items()))}
    return {"schema": "wot091-visual02-soviet-textures.v1", "target": mapping["target"],
            "scope": mapping["scope"], "paths_xml_sha256": mapping["paths_xml_sha256"],
            "catalog_sha256": mapping["catalog_sha256"],
            "warnings": ["Static research graph reachability ignores prerequisites and UI; not runtime selection.",
                         "Package sources only: loose resources, active overrides and runtime substitution not audited.",
                         "Archive lookup is case-insensitive (casefold); native ResMgr case behavior is not verified.",
                         "Only top mip alpha values scanned; alpha channel semantics unknown.",
                         "Only models/undamaged XML links and parent visuals; destroyed/exploded excluded."],
            "summary": {"vehicles_all_ussr": len(vehicles), "vehicles_reachable_ms1": len(tree_ids),
                        "vehicles_not_reachable_ms1": len(vehicles) - len(tree_ids),
                        "vehicles_with_unresolved": sum(bool(v["unresolved"]) for v in vehicles),
                        "all_linked": counts(rows), "tree_linked": counts(tree_textures),
                        "tree_diffuse": counts(tree_diffuse)},
            "vehicles": vehicles, "textures": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", required=True, type=Path, help="authorized #717 local client copy")
    parser.add_argument("--out", required=True, type=Path, help="new JSON output outside client")
    args = parser.parse_args()
    root = args.client.resolve(strict=True)
    out = safe_evidence_output(args.out)
    if out == root or root in out.parents:
        raise ValueError("output must be outside client")
    if out.exists():
        raise FileExistsError(out)
    result = build_inventory(root)
    payload = (json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    if len(payload) > MAX_OUTPUT:
        raise ValueError("output exceeds limit")
    out.parent.mkdir(parents=True, exist_ok=True)
    out = safe_evidence_output(out)
    with out.open("xb") as f:
        f.write(payload)
    print(json.dumps({"output": str(out), "sha256": _sha(payload), "summary": result["summary"]},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
