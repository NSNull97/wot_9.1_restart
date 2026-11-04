"""SHELL-01: chassis (track) armour bundle of every #717 catalogue vehicle.

Read-only, bounded, hash-pinned; the original client is only read. Bytecode is
inspected as inert data (no import/exec). The existing three-component bundles
(BATTLE-ANY, P04M, P06T, MS-1/IS-7) and their readers stay byte-identical: this
tool writes a separate per-vehicle chassis bundle and a closed table of their pins.

Why a separate reader for materials: tracks are device MaterialInfo records
(`extra` leftTrackHealth/rightTrackHealth, `damageKind auto`) that the shared
material reader (`ms1_contact_bundle`) does not cover. VERIFIED in
`vehicles.pyc` `_readMaterials` (+267..340): `armor`->0, `device`->1, and
`auto`->1 with the material kind added to `autoDamageKindMaterials`. What the
original server did with that set is UNKNOWN; both facts are kept as data.

Outputs:
- `<out>/bundles/<nation>-<resource>.json` (`chassis-armor.v1`), one per vehicle
  whose chassis source is read without refusal;
- `config/catalog/chassis_armor.v1.json`: one row per catalogue vehicle, the
  bundle pin or a refusal code (only with `--update`, or when it does not exist).

Commands: `build --original C --out local/evidence/<fresh> [--update]`,
`check` (no client; table self-consistency).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
for directory in (ROOT, TOOLS):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))
import battle_any_profiles as profiles
import ms1_contact_bundle as materials
from packed_xml import decode
from py27_static import parse_pyc, records, text
from vehicle_physics_profile import no_links, owned

SCHEMA = "wot091-chassis-armor.v1"
BUNDLE_SCHEMA = "chassis-armor.v1"
TABLE = ROOT / "config" / "catalog" / "chassis_armor.v1.json"
PROFILES_TABLE = profiles.TABLE
TRIANGLE_BASE = 300000  # component index 3 (chassis) in the 100000-per-component ID rule
TRACKS = {"leftTrack": "leftTrackHealth", "rightTrack": "rightTrackHealth"}
DAMAGE_KINDS = {"armor": 0, "device": 1, "auto": 1}
COMMON_FIELDS = {"extra", "vehicleDamageFactor", "damageKind", "chanceToHitByProjectile",
                 "chanceToHitByExplosion", *materials.BOOL_FIELDS}
OVERRIDES = {"vehicleDamageFactor", "chanceToHitByProjectile", "chanceToHitByExplosion", *materials.BOOL_FIELDS}
REFUSALS = ("CHASSIS_SOURCE_UNRESOLVED", "CHASSIS_SOURCE_UNSUPPORTED")
MAX_TABLE = 1024 * 1024
MAX_BUNDLE = 512 * 1024
POLICY = {
    "id": "shell-01.chassis-armor.v1",
    "classification": "VERIFIED_STATIC_ORIGINAL_717",
    "assembly": "catalogue stock chassis only",
    "auto_damage_kind": "VERIFIED loader: damageKind 1 and member of autoDamageKindMaterials; server use UNKNOWN",
    "battle_admission": "NONE: consumed by the ordered layer query; the live hit path is unchanged",
}


class Refused(Exception):
    def __init__(self, code, detail):
        assert code in REFUSALS
        super().__init__(code)
        self.code, self.detail = code, str(detail)[:160]


def require(condition, message):
    if not condition:
        raise profiles.ProfileError(message)


def refuse_if(condition, code, detail):
    if condition:
        raise Refused(code, detail)


def damage_kind_loader(raw):
    """The `damageKind` name table of `_readMaterials`, read as inert data."""
    parsed = parse_pyc(raw)
    function = dict(records(parsed))["<module>._readMaterials"]
    consts = [text(c) if isinstance(c, (bytes, str)) else c for c in function["consts"]]
    # Operand order of the compare chain: 'armor' 0, 'device' 1, 'auto' 1.
    require(consts[7:13] == ["damageKind", "armor", "device", 1, "auto", "wrong damage kind name"]
            and consts[6] == 0, "_readMaterials damageKind table differs")
    require("autoDamageKindMaterials" in [text(name) for name in function["varnames"]], "autoDamageKindMaterials missing")
    return dict(DAMAGE_KINDS)


def common_tracks(node, mapping, kinds):
    """leftTrack/rightTrack MaterialInfo defaults of common/vehicle.xml."""
    definitions = materials._children(materials._section(node, ("materials",)), "common materials")
    result = {}
    for name, extra in TRACKS.items():
        require(name in definitions and name in mapping, name + ": common definition missing")
        require(definitions[name]["value"] == "", name + ": common scalar must be empty")
        fields = materials._children(definitions[name], name)
        require(set(fields) == COMMON_FIELDS, name + ": common fields differ")
        require(materials._string(fields["extra"], "extra") == extra, name + ": extra differs")
        kind_name = materials._string(fields["damageKind"], "damage kind")
        require(kind_name in kinds, name + ": damage kind name")
        record = dict(kind=mapping[name], armor=None, extra=extra, damage_kind=kinds[kind_name],
                      auto_damage_kind=kind_name == "auto")
        for field in materials.FRACTION_FIELDS:
            record[field] = materials._number(fields[field], name + " " + field, 1.0)
        for field in materials.BOOL_FIELDS:
            record[field] = materials._bool(fields[field], name + " " + field)
        result[name] = record
    return result


def local_tracks(vf, chassis, common):
    """Local `<chassis>/armor`: only listed tracks get MaterialInfo (_readArmor rule).

    Read from the flat path map: other chassis children may repeat (M103 has
    two `drivingWheels`), which is not an armour question. A repeated `armor`,
    track or override child is still refused.
    """
    prefix = "/chassis[1]/" + chassis + "[1]/armor["
    refuse_if(any(k.startswith(prefix) and not k.startswith(prefix + "1]") for k in vf), "CHASSIS_SOURCE_UNSUPPORTED", "repeated chassis armor")
    root = prefix + "1]/"
    refuse_if(vf.get(root[:-1]) != "", "CHASSIS_SOURCE_UNSUPPORTED", "chassis armor section")
    children = {}
    for key, value in vf.items():
        if not key.startswith(root):
            continue
        parts = key[len(root):].split("/")
        head = re.fullmatch(r"([A-Za-z0-9_]+)\[([0-9]+)\]", parts[0])
        refuse_if(head is None, "CHASSIS_SOURCE_UNSUPPORTED", "chassis armor child path")
        name, index = head.groups()
        refuse_if(index != "1", "CHASSIS_SOURCE_UNSUPPORTED", "repeated chassis armor child " + name)
        entry = children.setdefault(name, {"value": None, "overrides": {}})
        if len(parts) == 1:
            entry["value"] = value
        else:
            match = re.fullmatch(r"([A-Za-z0-9_]+)\[1\]", parts[1]) if len(parts) == 2 else None
            refuse_if(match is None, "CHASSIS_SOURCE_UNSUPPORTED", name + " override path")
            entry["overrides"][match.group(1)] = value
    refuse_if(not children or not set(children) <= set(TRACKS), "CHASSIS_SOURCE_UNSUPPORTED", "chassis armor kinds " + ",".join(sorted(children)))
    result = {}
    for label, entry in children.items():
        record = dict(common[label])
        record["armor"] = materials._number(entry["value"], label + " armor", materials.MAX_ARMOR)
        refuse_if(not set(entry["overrides"]) <= OVERRIDES, "CHASSIS_SOURCE_UNSUPPORTED", label + " override")
        for field, item in entry["overrides"].items():
            record[field] = materials._bool(item, field) if field in materials.BOOL_FIELDS else materials._number(item, field, 1.0)
        result[label] = record
    return result


def chassis_component(src, model_path, effective, kinds_by_label):
    """Chassis collision mesh: the same model/visual/primitive bindings as BATTLE-ANY."""
    match = re.fullmatch(r"vehicles/([a-z]+)/([A-Za-z0-9_.-]+)/collision/([A-Za-z0-9_.-]+)\.model", model_path or "")
    refuse_if(match is None or match.group(1) not in profiles.PACKAGE_FOLDERS, "CHASSIS_SOURCE_UNRESOLVED", model_path)
    package = "res/packages/" + profiles.PACKAGE_FOLDERS[match.group(1)]
    stem, part = model_path[:-len(".model")], match.group(3)
    raws = {}
    for suffix in ("model", "visual", "primitives"):
        raw = src.member(package, stem + "." + suffix)
        refuse_if(raw is None, "CHASSIS_SOURCE_UNRESOLVED", stem + "." + suffix)
        raws[suffix] = raw
    try:
        model, visual = profiles.flat(raws["model"]), profiles.flat(raws["visual"])
        require(model.get("/nodelessVisual[1]") == stem, "collision model/visual binding")
        require(visual.get("/node[1]/identifier[1]") == "Scene Root" and
                visual.get("/node[1]/transform[1]") == [1., 0., 0., 0., 1., 0., 0., 0., 1., 0., 0., 0.], "nonidentity visual root")
        require(visual.get("/renderSet[1]/treatAsWorldSpaceObject[1]") is False, "world-space collision mesh")
        m = profiles.mesh(raws["primitives"])
        groups = {k for k in visual if re.fullmatch(r"/renderSet\[1\]/geometry\[1\]/primitiveGroup\[[0-9]+\]", k)}
        require(len(groups) == len(m["groups"]), "visual primitive group count")
        triangles, labels, excluded = [None] * (len(m["ids"]) // 3), set(), []
        for n, group in enumerate(m["groups"], 1):
            path = "/renderSet[1]/geometry[1]/primitiveGroup[" + str(n) + "]"
            label = visual.get(path + "/material[1]/identifier[1]")
            require(label in kinds_by_label, "unmapped chassis material " + str(label))
            require(visual.get(path) == n - 1 and visual.get(path + "/material[1]/materialKind[1]") == kinds_by_label[label]
                    and visual.get(path + "/material[1]/collisionFlags[1]") == 0, "primitive material binding")
            require(group["start_index"] % 3 == 0 and group["triangle_count"] > 0, "primitive group range")
            labels.add(label)
            for t in range(group["start_index"] // 3, group["start_index"] // 3 + group["triangle_count"]):
                require(t < len(triangles) and triangles[t] is None, "triangle overlap/outside group")
                a, b, c = m["ids"][3 * t:3 * t + 3]
                require(all(group["start_vertex"] <= x < group["start_vertex"] + group["vertex_count"] for x in (a, b, c)),
                        "triangle escapes group vertices")
                triangle = dict(triangle_id=TRIANGLE_BASE + t, a=a, b=b, c=c, material=label, mesh=part,
                                group="primitiveGroup[" + str(n) + "]")
                if profiles.zero_area(m["vertices"], a, b, c):
                    excluded.append(triangle["triangle_id"])
                triangles[t] = triangle
        require(all(t is not None for t in triangles), "triangle coverage gap")
        # A mesh label without a local record has no MaterialInfo (missing != zero).
        entries = [dict(name=label, kind=kinds_by_label[label], effective=effective.get(label))
                   for label in sorted(set(effective) | labels, key=lambda k: kinds_by_label[k])]
        visual_bounds = [profiles.vector(visual["/boundingBox[1]/" + e + "[1]"], 3, "visual bounds") for e in ("min", "max")]
    except (*profiles.SOURCE_ERRORS, materials.BundleError, ValueError, KeyError, TypeError) as error:
        raise Refused("CHASSIS_SOURCE_UNSUPPORTED", part + ": " + str(error)) from error
    members = {package + "!" + stem + "." + s: profiles.pin(raws[s]) for s in ("model", "visual", "primitives")}
    return dict(name=part, vertex_format=m["format"], vertices=m["vertices"], triangles=triangles, materials=entries,
                visual_bounds=visual_bounds, mesh_bounds=m["bounds"], excluded_degenerate_triangle_ids=excluded), members


def vehicle_row(src, catalog, identity, vehicle_id, common, kinds_by_label):
    v = catalog.vehicles[vehicle_id]
    chassis = v["defaults"]["chassis"].split(":")[-1]
    row = dict(vehicle_id=vehicle_id, nation=v["nation"], resource=v["resource_name"], chassis=chassis,
               identity=identity, status="generated", refusal=None, detail=None)
    raw = None
    try:
        vf = src.xml(v["source"])
        label = "/chassis[1]/" + chassis + "[1]"
        model = vf.get(label + "/hitTester[1]/collisionModel[1]")
        refuse_if(model is None, "CHASSIS_SOURCE_UNRESOLVED", label + " hitTester")
        hull_position = profiles.vector(vf[label + "/hullPosition[1]"], 3, "hull position")
        effective = local_tracks(vf, chassis, common)
        component, members = chassis_component(src, model, effective, kinds_by_label)
        bundle = dict(schema=BUNDLE_SCHEMA, vehicle_id=vehicle_id, classification="VERIFIED_STATIC_ORIGINAL_717",
                      identity=identity, chassis=chassis, hull_position=hull_position,
                      members=dict(sorted(members.items())), component=component, battle_admission=False)
        raw = profiles.canonical(bundle) + b"\n"
        require(len(raw) <= MAX_BUNDLE, vehicle_id + ": chassis bundle size bound")
        row.update(bundle=profiles.bundle_name(row), bytes=len(raw), sha256=profiles.sha(raw), hull_position=hull_position,
                   vertices=len(component["vertices"]), triangles=len(component["triangles"]),
                   excluded_degenerate=len(component["excluded_degenerate_triangle_ids"]),
                   materials=[dict(name=m["name"], kind=m["kind"],
                                   armor=None if m["effective"] is None else m["effective"]["armor"])
                              for m in component["materials"]])
    except Refused as refusal:
        raw = None
        row.update(status="refused", refusal=refusal.code, detail=refusal.detail)
    except KeyError as error:
        raw = None
        row.update(status="refused", refusal="CHASSIS_SOURCE_UNSUPPORTED", detail=("missing " + str(error))[:160])
    return row, raw


def build(original):
    src = profiles.Sources(original)
    catalog = profiles.load_catalog(src.root)
    require(catalog.sha256 == profiles.CATALOG_SHA256, "research catalogue differs")
    for rel, expected in materials.FILE_PINS.items():
        if rel.startswith("res/"):
            require(profiles.pin(src.file(rel)) == expected, "material source pin differs: " + rel)
    kinds_raw = src.member(materials.MISC_REL, materials.KINDS_MEMBER)
    require(src.packages[materials.MISC_REL] == materials.PACKAGE_PINS[materials.MISC_REL], "misc package pin differs")
    require(kinds_raw is not None and profiles.pin(kinds_raw) == materials.MEMBER_PINS[materials.KINDS_KEY], "material kinds pin differs")
    mapping = materials._kind_mapping(decode(kinds_raw, max_bytes=profiles.MAX_MEMBER))
    damage_kinds = damage_kind_loader(src.file(materials.LOADER_REL))
    common = common_tracks(decode(src.file(materials.COMMON_REL), max_bytes=profiles.MAX_MEMBER), mapping, damage_kinds)
    kinds_by_label = {**materials.EXPECTED_KINDS, **{name: mapping[name] for name in TRACKS}}
    identities = {r["vehicle_id"]: r["identity"] for r in json.loads(PROFILES_TABLE.read_bytes())["vehicles"]}
    require(set(identities) == set(catalog.vehicles), "battle profile table does not cover the catalogue")
    rows, bundles = [], {}
    for vehicle_id in sorted(catalog.vehicles):
        identity = identities[vehicle_id]
        row, raw = vehicle_row(src, catalog, dict(type_compact_id=identity["type_compact_id"],
                                                  descriptor_hex=identity["descriptor_hex"]), vehicle_id, common, kinds_by_label)
        rows.append(row)
        if raw is not None:
            bundles[row["bundle"]] = raw
    table = dict(schema=SCHEMA, target="v.0.9.1 #717 RU", research_catalog_sha256=profiles.CATALOG_SHA256,
                 battle_profiles_sha256=profiles.sha(PROFILES_TABLE.read_bytes()), policy=POLICY,
                 common_tracks=common, source_pins=src.pins(), vehicles=rows)
    raw = profiles.canonical(table) + b"\n"
    require(len(raw) <= MAX_TABLE, "table size bound")
    return raw, bundles


def export(original, out, update=False):
    local = no_links(ROOT / "local").resolve(strict=True)
    out = owned(local, Path(out).absolute())
    require(not out.exists() and out.parent.is_dir(), "fresh output with existing parent required")
    raw, bundles = build(original)
    committed = TABLE.read_bytes() if TABLE.is_file() else None
    require(update or committed is None or committed == raw, "chassis table differs from committed; use --update")
    out.mkdir()
    (out / "bundles").mkdir()
    for name, data in sorted(bundles.items()):
        with (out / "bundles" / name).open("xb") as stream:
            stream.write(data)
    with (out / "chassis_armor.v1.json").open("xb") as stream:
        stream.write(raw)
    if update or committed is None:
        TABLE.write_bytes(raw)
    table = json.loads(raw)
    counts = {}
    for row in table["vehicles"]:
        key = row["status"] if row["refusal"] is None else row["refusal"]
        counts[key] = counts.get(key, 0) + 1
    receipt = dict(schema="chassis-armor-export.v1", status="PASS_PINNED_SOURCE_EXPORT", table_sha256=profiles.sha(raw),
                   vehicles=len(table["vehicles"]), counts=dict(sorted(counts.items())), bundles=len(bundles),
                   bundles_sha256=profiles.sha(profiles.canonical({k: profiles.sha(v) for k, v in sorted(bundles.items())})),
                   committed_table_changed=committed is not None and committed != raw,
                   native="NOT_RUN", client_bytecode_executed=False)
    with (out / "receipt.json").open("xb") as stream:
        stream.write(profiles.canonical(receipt) + b"\n")
    return receipt


def check(path=TABLE):
    raw = path.read_bytes()
    require(len(raw) <= MAX_TABLE, "table size bound")
    table = json.loads(raw)
    require(table["schema"] == SCHEMA and table["policy"] == POLICY, "table schema/policy differs")
    profile_rows = {r["vehicle_id"]: r for r in json.loads(PROFILES_TABLE.read_bytes())["vehicles"]}
    require(table["battle_profiles_sha256"] == profiles.sha(PROFILES_TABLE.read_bytes()), "battle profile table changed")
    seen = set()
    for row in table["vehicles"]:
        vid = row["vehicle_id"]
        require(vid not in seen and vid in profile_rows, vid + ": duplicate or unknown vehicle")
        seen.add(vid)
        identity = profile_rows[vid]["identity"]
        require(row["identity"] == dict(type_compact_id=identity["type_compact_id"], descriptor_hex=identity["descriptor_hex"]),
                vid + ": identity differs from the battle profile")
        if row["status"] == "generated":
            require(row["refusal"] is None and re.fullmatch(r"[0-9a-f]{64}", row["sha256"]) is not None, vid + ": pin")
            require(row["triangles"] > 0 and row["materials"], vid + ": empty chassis")
            geometry = profile_rows[vid].get("geometry")
            if profile_rows[vid]["status"] == "generated":
                require(geometry is not None, vid + ": generated profile without geometry")
        else:
            require(row["status"] == "refused" and row["refusal"] in REFUSALS, vid + ": refusal")
    require(seen == set(profile_rows), "table does not cover the battle profiles")
    return dict(status="PASS_CHASSIS_TABLE", vehicles=len(seen),
                generated=sum(r["status"] == "generated" for r in table["vehicles"]))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build")
    b.add_argument("--original", required=True)
    b.add_argument("--out", required=True)
    b.add_argument("--update", action="store_true")
    sub.add_parser("check")
    args = parser.parse_args(argv)
    result = export(args.original, args.out, args.update) if args.command == "build" else check()
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
