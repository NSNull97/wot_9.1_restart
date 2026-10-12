"""Build the pinned Prohorovka tree/contact catalog.

The legacy fragile importer remains version 1 and is deliberately untouched.
This module joins that inventory with the original speedtree instances whose
movement mesh has triangles and whose projectile mesh is empty.  It never
allocates native IDs by source order: IDs must come from the complete, stable
passive native getter export.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import zipfile

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
import destructible_catalog as dc

MAP = "05_prohorovka"
MAX_OBJECTS = 1024
MAX_REMOVED = 1024
MAX_CHUNKS = 128
MAX_ITEMS_PER_CHUNK = 256
MAX_TREE_ITEMS_PER_CHUNK = 62
MAX_NATIVE_BYTES = 16 * 1024 * 1024
MAX_MANIFEST_BYTES = 512 * 1024
MAX_WORKER_BYTES = 512 * 1024
CONTACTS = True


def require(condition, message):
    if not condition:
        raise dc.CatalogError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load_sources():
    sources = dc.load_sources(MAP)
    geometry = dc.json_value(sources["physics"])["geometries"]
    original = dc.configured_paths()["original_client_root"]
    package = dc.no_links(original / "res/packages" / (MAP + ".pkg"))
    size, expected = dc.map_profile(MAP).package_pins()[MAP + ".pkg"]
    require(package.stat().st_size == size, "tree package size pin")
    with package.open("rb") as stream:
        require(hashlib.file_digest(stream, "sha256").hexdigest() == expected, "tree package SHA256 pin")
    sources["tree_resources"] = {}
    with zipfile.ZipFile(package) as archive:
        require(len(archive.infolist()) <= 20000 and len(set(archive.namelist())) == len(archive.namelist()),
                "tree package index bound/duplicates")
        for name, meta in sorted(geometry.items()):
            if name.endswith(".spt"):
                bsp = dc.member(archive, name[:-4] + ".bsp2")
                require(len(bsp) == meta["bytes"] and sha(bsp) == meta["sha256"], "tree BSP source pin")
                sources["tree_resources"][name] = {"spt": dc.member(archive, name), "bsp": bsp}
    return sources


def tree_material_contracts(sources, meshes):
    contracts = {}
    geometries = meshes["physics"]["geometries"]
    names = {i["resource"] for i in meshes["physics"]["instances"] if i["kind"] == "speedtree"}
    require(set(sources["tree_resources"]) == names, "complete tree source set required")
    for name in sorted(names):
        resources = sources["tree_resources"][name]
        bsp, spt = resources["bsp"], resources["spt"]
        meta = geometries[name]
        require(meta == meshes["projectile"]["geometries"][name], "tree BSP mesh metadata differs")
        require(type(bsp) is bytes and len(bsp) == meta["bytes"] and sha(bsp) == meta["sha256"],
                "tree BSP pin before parse")
        require(type(spt) is bytes and 0 < len(spt) <= 8 * 1024 * 1024, "tree SPT byte bound")
        require(len(bsp) >= 60 and bsp[:4] == b"BSP\x02" and
                struct.unpack_from("<3I", bsp, 4) == (16, 40, 40), "tree BSP header")
        count = struct.unpack_from("<I", bsp, 16)[0]
        require(count == meta["triangles"] and count <= 100000 and 60 + count * 40 <= len(bsp),
                "tree BSP triangle bound")
        flags = Counter(struct.unpack_from("<H", bsp, 60 + i * 40 + 36)[0] for i in range(count))
        require(set(flags) <= {18336, 18608}, "unsupported tree source material flags")
        contracts[name] = {"bsp_sha256": sha(bsp), "spt_sha256": sha(spt),
                           "bsp_bytes": len(bsp), "spt_bytes": len(spt), "source_flags": dict(flags),
                           "movement_triangles_before_quantization": sum(n for f, n in flags.items() if not f & 18),
                           "projectile_triangles": sum(n for f, n in flags.items() if not f & 128),
                           "material_kind": 71, "collision_flags": 160}
    return contracts


def _chunk_objects(sources):
    """Return exact original /model and /speedtree records keyed by chunk path."""
    result = {}
    for name, raw in sources["chunks"].items():
        stem = Path(name).name
        coords = [int(stem[i:i + 4], 16) for i in (0, 4)]
        coords = [v - 65536 if v >= 32768 else v for v in coords]
        counts = Counter()
        for row in dc.decode(raw)["children"]:
            counts[row["name"]] += 1
            if row["name"] not in ("model", "speedtree"):
                continue
            key = (tuple(coords), "/" + row["name"] + "[" + str(counts[row["name"]]) + "]")
            require(key not in result, "duplicate original tree/model key")
            result[key] = dict(dc.walk(row["data"]))
    return result


def _tree_rows(sources, meshes, defs, contracts):
    """Build every source tree row, retaining exclusions for coverage audits."""
    original = _chunk_objects(sources)
    physics, projectile = meshes["physics"], meshes["projectile"]
    require(len(physics["instances"]) == len(projectile["instances"]),
            "tree geometry instance count differs")
    rows, eligible = [], []
    candidates = defaultdict(list)
    for instance_id, (phy, shot) in enumerate(zip(physics["instances"], projectile["instances"])):
        if phy["kind"] != "speedtree":
            continue
        require(shot["kind"] == "speedtree" and shot["resource"] == phy["resource"] and
                shot["chunk"] == phy["chunk"] and shot["instance"] == phy["instance"] and
                shot["transform"] == phy["transform"],
                "tree projectile/physics instance identity differs")
        key = (tuple(phy["chunk"]), phy["instance"])
        source = original.get(key)
        require(source is not None, "tree source chunk instance missing")
        require(source.get("/spt[1]") == phy["resource"] and
                source.get("/transform[1]") == phy["transform"],
                "tree source resource/transform differs")
        definition = defs.get(phy["resource"])
        require(definition is not None and definition["family"] == "trees",
                "speedtree has no pinned tree definition")
        chunk = phy["chunk"]
        chunk_id = ((chunk[0] + 127) << 8) | (chunk[1] + 127)
        candidates[chunk_id].append({"instance_id": instance_id, "resource": phy["resource"],
                                     "kind": "tree"})
        reasons = []
        contract = contracts[phy["resource"]]
        require(phy["triangles"] + phy["degenerate"] == contract["movement_triangles_before_quantization"] and
                shot["triangles"] == contract["projectile_triangles"], "tree source material/span coverage")
        require(type(shot["triangles"]) is int and shot["triangles"] == 0,
                "tree projectile triangle count must be zero")
        if phy["triangles"] <= 0:
            reasons.append("no_movement_triangles")
        if phy.get("excluded_mask18", 0) < 0:
            reasons.append("invalid_movement_exclusion_count")
        # Direct BSP flags and the pinned span retain only trunk material 71.
        first, count = phy["first_triangle"], phy["triangles"]
        require(0 <= first <= meshes["physics"]["summary"]["kept"] and
                0 <= count <= meshes["physics"]["summary"]["kept"] - first,
                "tree movement triangle span")
        health = definition["reference_health"]
        require(type(health) is int and 1 <= health <= 0xFFFFFFFF,
                "tree reference health outside u32")
        row = {
            "instance_id": instance_id,
            "resource": phy["resource"],
            "kind": "tree",
            "chunk": chunk,
            "chunk_id": chunk_id,
            "source_instance": phy["instance"],
            "transform": phy["transform"],
            "source_basis_lengths": [sum(v * v for v in phy["transform"][axis * 3:axis * 3 + 3]) ** 0.5
                                     for axis in range(3)],
            "source_transform_determinant": phy["determinant"],
            "world_origin": [phy["transform"][9] + 100 * chunk[0], phy["transform"][10],
                             phy["transform"][11] + 100 * chunk[1]],
            "reference_health": health,
            "source_bsp_sha256": contract["bsp_sha256"],
            "source_spt_sha256": contract["spt_sha256"],
            "material_name": None,
            # Speedtree chunk records have no destructibleState field.  Keep
            # this explicit UNKNOWN instead of claiming a client state that
            # was not present in the pinned source.
            "initial_state": None,
            "projectile_first_triangle": shot["first_triangle"],
            "projectile_triangle_count": 0,
            "physics_first_triangle": first,
            "physics_triangle_count": count,
            "eligible": not reasons,
            "exclusions": reasons,
            "native_index": None,
        }
        if not reasons:
            # The physics manifest itself is pinned and its world bounds are
            # checked by the source exporter; retain a digest for identity.
            points = dc._points(sources, "physics", phy)
            identity = {
                "schema": "destructible-object-source.v2",
                "map": MAP,
                "kind": "tree",
                "destructibles_sha256": dc.DESTRUCTIBLES_SHA256,
                "physics_manifest_sha256": dc.map_profile(MAP).files()["physics"][1],
                "projectile_manifest_sha256": dc.map_profile(MAP).files()["projectile"][1],
                "instance": {k: v for k, v in row.items()
                             if k not in ("eligible", "exclusions", "native_index")},
                "world_triangle_points_sha256": sha(points),
                "material_kind": 71,
            }
            row["world_triangle_points_sha256"] = sha(points)
            row["object_revision"] = sha(dc.canonical(identity))
            eligible.append(row)
        rows.append(row)
    return rows, eligible, candidates


def build_inventory(sources=None):
    """Import old fragiles and all eligible trees from pinned Prohorovka."""
    sources = load_sources() if sources is None else sources
    require(sources.get("map") == MAP, "tree catalog requires Prohorovka sources")
    meshes = dc.verify_sources(sources)
    definitions, defs, duplicates = dc.parse_definitions(sources["destructibles"])
    legacy = dc.build_inventory(sources)
    contracts = tree_material_contracts(sources, meshes)
    tree_rows, tree_eligible, tree_candidates = _tree_rows(sources, meshes, defs, contracts)
    eligible = []
    for row in legacy["eligible"]:
        copy = dict(row)
        copy["kind"] = "fragile"
        copy["reference_health"] = int(copy["reference_health"])
        eligible.append(copy)
    eligible.extend(tree_eligible)
    # Runtime catalog validators require the object_id sequence to be strictly
    # increasing.  Legacy and tree rows originate from the same instance list,
    # so sort once after merging rather than relying on family traversal order.
    eligible.sort(key=lambda row: row["instance_id"])
    require(0 < len(eligible) <= MAX_OBJECTS, "bounded nonempty combined catalog")
    # The native probe audits each chunk containing an admitted object.  Every
    # one of the 116 tree chunks is included; no source chunk is silently cut.
    target_chunks = sorted({r["chunk_id"] for r in eligible})
    require(len(target_chunks) <= MAX_CHUNKS, "native target chunk bound")
    tree_counts = Counter(r["chunk_id"] for r in tree_eligible)
    require(max(tree_counts.values(), default=0) <= MAX_TREE_ITEMS_PER_CHUNK,
            "tree objects per chunk exceed native probe budget")
    candidates = defaultdict(list)
    for chunk, values in legacy["registered_source_candidates_by_chunk"].items():
        candidates[int(chunk)].extend(values)
    for chunk, values in tree_candidates.items():
        candidates[int(chunk)].extend(values)
    files = dc.map_profile(MAP).files()
    spec = {"version": 2, "kind": "p06q_tree_contact_catalog_spec", "map": MAP,
            "source_pins": sources["pins"], "chunk_ids": target_chunks}
    tree_exclusions = Counter(reason for row in tree_rows for reason in row["exclusions"])
    return {
        "version": 2,
        "kind": "p06q_tree_contact_catalog_inventory",
        "map": MAP,
        "source_pins": sources["pins"],
        "package_pins": dc.map_profile(MAP).package_pins(),
        "summary": {
            "definition_rows": len(definitions),
            "unique_definition_resources": len(defs),
            "map_instances": len(meshes["physics"]["instances"]),
            "fragile_instances": len(legacy["fragiles"]),
            "legacy_eligible_instances": len(legacy["eligible"]),
            "tree_instances": len(tree_rows),
            "tree_eligible_instances": len(tree_eligible),
            "tree_chunks": len(tree_counts),
            "eligible_instances": len(eligible),
            "probe_chunks": len(target_chunks),
            "tree_exclusion_reasons": dict(tree_exclusions),
        },
        "definitions": definitions,
        "identical_duplicate_definitions": duplicates,
        "fragiles": legacy["fragiles"],
        "trees": tree_rows,
        "tree_material_contracts": contracts,
        "eligible": eligible,
        "chunk_pins": legacy["chunk_pins"],
        "registered_source_candidates_by_chunk": {str(k): v for k, v in sorted(candidates.items())},
        "probe_spec": spec,
        "contacts": CONTACTS,
        "health_contract": {
            "classification": "VERIFIED_REFERENCE_HEALTH_U32_APPROXIMATE_RUNTIME_POLICY",
            "runtime_choice": "Original XML reference health; native scale is not reconstructed",
        },
        "limits": [
            "Native IDs require complete stable passive getter catalog, not source ordinal.",
            "Tree projectile mesh is intentionally empty; movement spans are physics-only.",
            "Original speedtree chunks carry no destructibleState field; initial state is UNKNOWN.",
            "Health is original reference health under test_lab; historical scaling remains UNKNOWN.",
        ],
    }


def probe_spec_bytes(inventory):
    require(inventory["probe_spec"]["version"] == 2, "tree probe requires spec version 2")
    return dc.canonical(inventory["probe_spec"]) + b"\n"


def _native_vector(value):
    return dc.native_matrix(value)


def validate_native(raw, inventory):
    """Validate a version-2 full native export, retaining native holes."""
    value = dc.json_value(raw, MAX_NATIVE_BYTES, 400000, 12)
    require(type(value) is dict and set(value) == {
        "version", "kind", "map", "space_id", "source_pins", "spec_sha256",
        "observation_count", "chunks"}, "tree native export fields")
    require(value["version"] == 2 and value["kind"] == "p06q_tree_contact_catalog" and
            value["map"] == MAP and value["observation_count"] == 2,
            "tree native export identity")
    dc.integer(value["space_id"], 1, 2 ** 32 - 1, "native space ID")
    require(value["source_pins"] == inventory["source_pins"] and
            value["spec_sha256"] == sha(probe_spec_bytes(inventory)),
            "tree native export source/spec binding")
    expected = inventory["probe_spec"]["chunk_ids"]
    rows = value["chunks"]
    require(type(rows) is list and len(rows) == len(expected) <= MAX_CHUNKS,
            "complete tree native chunk count")
    result = {}
    for chunk in rows:
        require(type(chunk) is dict and set(chunk) == {"chunk_id", "count", "chunk_matrix", "items"},
                "tree native chunk fields")
        chunk_id = dc.integer(chunk["chunk_id"], 0, 65535, "chunk ID")
        require(chunk_id in expected and chunk_id not in result, "unexpected/duplicate tree chunk ID")
        count = dc.integer(chunk["count"], 1, MAX_ITEMS_PER_CHUNK, "native count bound")
        x, z = (chunk_id >> 8) - 127, (chunk_id & 255) - 127
        expected_matrix = [1., 0., 0., 0., 1., 0., 0., 0., 1., float(100 * x), 0., float(100 * z)]
        require(_native_vector(chunk["chunk_matrix"]) == dc.matrix_bits(expected_matrix),
                "native tree chunk transform differs")
        items, by_index, identities = chunk["items"], {}, set()
        require(type(items) is list and len(items) == count, "native tree item count")
        for item in items:
            require(type(item) is dict and set(item) == {"index", "filename", "local_matrix"},
                    "native tree item fields")
            index = dc.integer(item["index"], 0, count - 1, "native item index")
            require(index not in by_index, "duplicate native tree item index")
            filename = dc.resource(item["filename"])
            identity = (filename, _native_vector(item["local_matrix"]))
            require(identity not in identities, "ambiguous native tree filename/matrix")
            identities.add(identity)
            by_index[index] = identity
        require(set(by_index) == set(range(count)), "native tree index gap")
        result[chunk_id] = by_index
    require(set(result) == set(expected), "native tree target chunk missing")
    return result


def join_exports(inventory, exports):
    """Join one or two independently captured v2 native exports."""
    require(type(exports) is list and 1 <= len(exports) <= 2, "one or two native exports required")
    mappings, digests = [], []
    for raw, expected in exports:
        require(type(raw) is bytes and sha(raw) == dc.digest(expected), "native export SHA256 before parse")
        mappings.append(validate_native(raw, inventory))
        digests.append(expected)
    require(len(set(digests)) == len(digests) and all(m == mappings[0] for m in mappings),
            "native exports disagree or duplicate")
    objects, worker_objects, seen_native = [], [], set()
    for row in inventory["eligible"]:
        key = (row["resource"], dc.matrix_bits(row["transform"]))
        matches = [index for index, identity in mappings[0][row["chunk_id"]].items() if identity == key]
        require(len(matches) == 1, "missing or ambiguous native source instance match")
        native_index = matches[0]
        native_key = (row["chunk_id"], native_index)
        require(native_key not in seen_native, "two source objects share native ID")
        seen_native.add(native_key)
        kind = row["kind"]
        require(kind in ("fragile", "tree"), "unknown runtime object kind")
        obj = {
            "object_id": row["instance_id"] + 1,
            "instance_id": row["instance_id"],
            "kind": kind,
            "chunk_id": row["chunk_id"],
            "native_index": native_index,
            "resource": row["resource"],
            "health": int(row["reference_health"]),
            "material_kind": 71 if kind == "tree" else 73,
            "projectile_first_triangle": row["projectile_first_triangle"],
            "projectile_triangle_count": 0 if kind == "tree" else row["projectile_triangle_count"],
            "physics_first_triangle": row["physics_first_triangle"],
            "physics_triangle_count": row["physics_triangle_count"],
            "object_revision": row["object_revision"],
        }
        objects.append(obj)
        worker_objects.append({
            "object_id": obj["object_id"],
            "instance_id": obj["instance_id"],
            "kind": kind,
            "first_triangle": obj["physics_first_triangle"],
            "triangle_count": obj["physics_triangle_count"],
            "object_revision": obj["object_revision"],
        })
    require(0 < len(objects) <= MAX_OBJECTS, "runtime object bound")
    profile = dc.map_profile(MAP)
    files = profile.files()
    worker = {
        "version": 3, "profile": "test_lab", "map": MAP,
        "physics_manifest_sha256": files["physics"][1],
        "projectile_manifest_sha256": files["projectile"][1],
        "contacts": CONTACTS, "objects": worker_objects,
    }
    worker_raw = dc.canonical(worker) + b"\n"
    dc.json_value(worker_raw, MAX_WORKER_BYTES, 12000, 12)
    manifest = {
        "version": 2, "profile": "test_lab", "map": MAP,
        "destructibles_sha256": dc.DESTRUCTIBLES_SHA256,
        "physics_manifest_sha256": files["physics"][1],
        "projectile_manifest_sha256": files["projectile"][1],
        "native_exports_sha256": sorted(digests),
        "worker": {"file": "physics-removals.json", "sha256": sha(worker_raw)},
        "contacts": CONTACTS, "objects": objects,
    }
    manifest_raw = dc.canonical(manifest) + b"\n"
    dc.json_value(manifest_raw, MAX_MANIFEST_BYTES, 12000, 12)
    return manifest_raw, worker_raw


def fresh_output(path, local):
    return dc.fresh_output(path, local)


def save(path, raw):
    return dc.save(path, raw)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="fresh output directory under local/")
    parser.add_argument("--native-export", action="append", default=[])
    parser.add_argument("--native-sha256", action="append", default=[])
    args = parser.parse_args(argv)
    require(len(args.native_export) == len(args.native_sha256) and args.native_export,
            "native export and sha256 pairs required")
    inventory = build_inventory()
    exports = []
    for path, expected in zip(args.native_export, args.native_sha256):
        exports.append((Path(path).read_bytes(), expected))
    manifest_raw, worker_raw = join_exports(inventory, exports)
    output = fresh_output(args.out, dc.configured_paths()["local_artifacts_root"])
    save(output / "manifest.json", manifest_raw)
    save(output / "physics-removals.json", worker_raw)
    print(json.dumps({"status": "complete", "manifest": str(output / "manifest.json"),
                      "manifest_sha256": sha(manifest_raw), "worker_sha256": sha(worker_raw),
                      "objects": len(inventory["eligible"]), "chunks": len(inventory["probe_spec"]["chunk_ids"])},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
