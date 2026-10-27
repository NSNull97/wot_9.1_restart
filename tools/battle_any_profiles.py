"""BATTLE-ANY: battle profile of the stock assembly of ANY #717 catalogue vehicle.

Read-only, bounded, hash-pinned. The same source rules as the closed P04M
(`p04m_battle_profiles`), P06T shells (`p06t_shell_catalog`) and P06T extended
physics (`p06t_extended_profiles`) importers, without hand-written per-vehicle
specs. Original bytecode is inspected as inert data only (no import/exec).

Outputs:
- `config/catalog/battle_profiles.v1.json`: closed table, one row per catalogue
  vehicle: VERIFIED source facts, the explicit test_lab physics projection and a
  `generated`/`refused` decision with a refusal code. Rows never grant admission.
- `<out>/bundles/<nation>-<resource>.json`: per generated vehicle collision and
  armour bundle (shape of `p04m-battle-source.v1` components) with member pins;
  the table pins each bundle by SHA-256.

Commands: `build --original C --out local/evidence/<fresh>` (refuses to change the
committed table unless `--update`), `check` (no client; table self-consistency).
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import sys
import zipfile

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
for directory in (ROOT, TOOLS):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))
import ms1_contact_bundle as materials
from geometry_spike import primitive_sections
from packed_xml import decode, walk
from p04m_battle_profiles import ProfileError as SourceError, _effective, number, vector
from p09e_research_catalog import load_catalog
from p09e_research_projection import descriptor
from py27_static import parse_pyc
from vehicle_physics_profile import no_links, owned

SCHEMA = "wot091-battle-profiles.v1"
BUNDLE_SCHEMA = "battle-any-source.v1"
TABLE = ROOT / "config" / "catalog" / "battle_profiles.v1.json"
BINDING = TOOLS / "battle_any_data.py"
CATALOG_SHA256 = "b6baecd204444d1e894253fa6c19c61478993b8ae87c71373633989d3a8ee460"
# Original res/scripts/common/nations.pyc order (verified in build, as P06T does).
# The P09E research catalogue enumerates france/uk/china differently; its
# compact IDs for those nations are recorded but not used (see table rows).
NATIONS = ("ussr", "germany", "usa", "china", "france", "uk", "japan")
PACKAGE_FOLDERS = {"russian": "vehicles_russian.pkg", "german": "vehicles_german.pkg",
                   "american": "vehicles_american.pkg", "french": "vehicles_french.pkg",
                   "british": "vehicles_british.pkg", "chinese": "vehicles_chinese.pkg",
                   "japan": "vehicles_japan.pkg"}
PREFIX = "res/scripts/item_defs/vehicles/"
COMPONENT_FILES = ("guns", "shells", "chassis", "turrets", "engines", "fueltanks", "radios")
MODULE_KINDS = ("chassis", "engine", "fuelTank", "radio", "turret", "gun")
CLASSES = ("lightTank", "mediumTank", "heavyTank", "AT-SPG", "SPG")
FAMILIES = ("ARMOR_PIERCING", "ARMOR_PIERCING_CR", "HOLLOW_CHARGE", "HIGH_EXPLOSIVE")
MAX_SOURCE = 1024 * 1024
MAX_MEMBER = 256 * 1024
MAX_PACKAGE = 4 * 1024 * 1024 * 1024
MAX_TABLE = 4 * 1024 * 1024
MAX_BUNDLE = 2 * 1024 * 1024
# Mounted single-shot/drum limit of the accepted P06T armament state machine
# (`battle/armament.rs`, clip_count 1..=6, no burst). Not a historical rule.
MAX_CLIP = 6
PHYSICS_POLICY = "p06t-extended-six-support-v2"
SUPPORT_RADIUS = "named-equal-main-W_L0-W_R0-or-group-W_L-W_R"
# Numeric envelope enforced by server/physics StockVehicleProfiles/Extended
# ValidateProjection; a vehicle outside it is refused, never clamped.
ENVELOPE = {"mass_kg": (1000, 100000), "max_forward_mps": (1, 20), "max_reverse_mps": (.5, 10),
            "engine_max_torque_nm": (10, 10000), "wheel_radius": (.05, 1),
            "track_max_brake_torque": (100, 300000), "max_yaw_rate_rad_s": (.1, 1.5)}
# Constant per-row projection mapping, identical to extended-definitions.json.
MAPPING = {"policy": PHYSICS_POLICY, "classification": "INFERRED_TEST_LAB_ONLY", "historical_fidelity": False,
           "support_radius": SUPPORT_RADIUS, "support_count": 6, "support_y_offset": .28,
           "motion_quality": "Discrete", "collision_steps_per_60hz": 4}
REFUSALS = ("SPG_INDIRECT_FIRE_OUT_OF_SCOPE", "AUTOMATIC_GUN_UNSUPPORTED", "MOUNTED_SHOT_OVERRIDE_UNSUPPORTED",
            "SHELL_SOURCE_UNSUPPORTED", "PHYSICS_ENVELOPE_EXCEEDED", "SUPPORT_SOURCE_UNRESOLVED",
            "COLLISION_SOURCE_UNRESOLVED", "COLLISION_SOURCE_UNSUPPORTED")
POLICY = {
    "id": "test_lab.battle-any.v1",
    "classification": "VERIFIED_STATIC_ORIGINAL_717_FACTS_WITH_EXPLICIT_TEST_LAB_PROJECTION",
    "assembly": "catalogue stock defaults only; non-stock modules are not profiled",
    "physics": {"envelope": {k: list(v) for k, v in ENVELOPE.items()},
                "mapping": MAPPING},
    "damage_model": "P06T single-plate test_lab on proxy AABB armour (unchanged by this card)",
    "armament": {"max_clip": MAX_CLIP, "burst": "unsupported"},
    "spg": "refused: indirect fire/artillery view out of scope",
    "battle_admission": "NONE: a generated row is runtime-ineligible until a runtime layer loads it",
    "wire_readiness_code": "BATTLE_PROFILE_UNSUPPORTED",
}
# The seven kinds that already have hand-closed profiles in every layer.
EXISTING = {"vehicle:ussr:MS-1": "ms1", "vehicle:ussr:IS-7": "is7", "vehicle:ussr:T-26": "t26",
            "vehicle:ussr:T-34": "t34", "vehicle:ussr:T-34-85": "t3485",
            "vehicle:germany:Waffentrager_E100": "wt-e100-128", "vehicle:uk:GB48_FV215b_183": "fv215b-183"}


class ProfileError(ValueError):
    pass


SOURCE_ERRORS = (ProfileError, SourceError)


class Refused(Exception):
    def __init__(self, code, detail):
        assert code in REFUSALS
        super().__init__(code)
        self.code, self.detail = code, str(detail)[:160]


def require(condition, message):
    if not condition:
        raise ProfileError(message)


def refuse_if(condition, code, detail):
    if condition:
        raise Refused(code, detail)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pin(raw):
    return {"bytes": len(raw), "sha256": sha(raw)}


def flat(raw):
    return dict(walk(decode(raw, max_bytes=MAX_SOURCE, max_depth=32, max_nodes=60000)))


class Sources:
    """Bounded read-only access to the original client; records every pin."""

    def __init__(self, original):
        self.root = no_links(Path(original)).resolve(strict=True)
        require(self.root.is_dir() and not self.root.is_relative_to(ROOT / "local"), "original root must be outside local")
        self.files, self.packages, self.archives, self._flat = {}, {}, {}, {}

    def file(self, rel):
        if rel not in self.files:
            path = no_links(self.root / rel)
            require(path.is_file() and 0 < path.stat().st_size <= MAX_SOURCE, "source file bound: " + rel)
            with path.open("rb") as stream:
                raw = stream.read(MAX_SOURCE + 1)
            require(0 < len(raw) <= MAX_SOURCE, "source read bound: " + rel)
            self.files[rel] = (raw, pin(raw))
        return self.files[rel][0]

    def xml(self, rel):
        if rel not in self._flat:
            self._flat[rel] = flat(self.file(rel))
        return self._flat[rel]

    def archive(self, rel):
        if rel not in self.archives:
            path = no_links(self.root / rel)
            require(path.is_file() and 0 < path.stat().st_size <= MAX_PACKAGE, "package bound: " + rel)
            digest, size = hashlib.sha256(), 0
            with path.open("rb") as stream:
                while chunk := stream.read(8 * 1024 * 1024):
                    digest.update(chunk)
                    size += len(chunk)
            require(size == path.stat().st_size, "package changed while hashing: " + rel)
            self.packages[rel] = {"bytes": size, "sha256": digest.hexdigest()}
            archive = zipfile.ZipFile(path)
            infos = archive.infolist()
            require(len(infos) <= 200000, "archive entry bound: " + rel)
            self.archives[rel] = (archive, {i.filename: i for i in infos})
        return self.archives[rel]

    def member(self, package, name):
        archive, index = self.archive(package)
        info = index.get(name)
        if info is None:
            return None
        require(not info.is_dir() and not info.flag_bits & 1 and 0 < info.file_size <= MAX_MEMBER
                and 0 < info.compress_size <= MAX_MEMBER, "archive member bound: " + name)
        with archive.open(info) as stream:
            raw = stream.read(MAX_MEMBER + 1)
        require(len(raw) == info.file_size, "archive member length: " + name)
        return raw

    def pins(self):
        return {"files": {k: v[1] for k, v in sorted(self.files.items())},
                "packages": dict(sorted(self.packages.items()))}


def mesh(raw):
    """Positions/indices/groups of xyznuv and xyznuvtb (32-byte stride, P06T vertex01 proof)."""
    sections = primitive_sections(raw)
    require("vertices" in sections and "indices" in sections, "primitive sections")
    v, i = sections["vertices"], sections["indices"]
    vertices, indices = raw[v["offset"]:v["offset"] + v["bytes"]], raw[i["offset"]:i["offset"] + i["bytes"]]
    require(len(vertices) >= 68 and len(indices) >= 72, "truncated mesh")
    fmt = vertices[:64].split(b"\0", 1)[0]
    require(fmt in (b"xyznuv", b"xyznuvtb"), "vertex format")
    count = struct.unpack_from("<I", vertices, 64)[0]
    require(0 < count <= 8192 and len(vertices) == 68 + 32 * count, "vertex count/stride")
    points = [list(struct.unpack_from("<3f", vertices, 68 + 32 * j)) for j in range(count)]
    require(all(math.isfinite(x) and abs(x) <= 10 for p in points for x in p), "vertex bounds")
    width = {b"list": 2, b"list32": 4}.get(indices[:64].split(b"\0", 1)[0])
    total, groups = struct.unpack_from("<II", indices, 64)
    require(width is not None and 0 < total <= 3 * 16384 and total % 3 == 0 and 0 < groups <= 64
            and len(indices) == 72 + width * total + 16 * groups, "index layout")
    ids = struct.unpack_from("<" + ("H" if width == 2 else "I") * total, indices, 72)
    require(all(x < count for x in ids), "index bound")
    rows = [dict(zip(("start_index", "triangle_count", "start_vertex", "vertex_count"),
                     struct.unpack_from("<4I", indices, 72 + width * total + 16 * g))) for g in range(groups)]
    return dict(format=fmt.decode(), vertices=points, ids=ids, groups=rows,
                bounds=dict(min=[min(p[j] for p in points) for j in range(3)], max=[max(p[j] for p in points) for j in range(3)]))


def zero_area(vertices, a, b, c):
    pa, pb, pc = vertices[a], vertices[b], vertices[c]
    u = [pb[k] - pa[k] for k in range(3)]
    w = [pc[k] - pa[k] for k in range(3)]
    cross = (u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0])
    return cross == (0.0, 0.0, 0.0)


def component(src, model_path, index, effective):
    """One collision component; the same bindings P04M `_component` checks."""
    match = re.fullmatch(r"vehicles/([a-z]+)/([A-Za-z0-9_.-]+)/collision/([A-Za-z0-9_.-]+)\.model", model_path or "")
    refuse_if(match is None or match.group(1) not in PACKAGE_FOLDERS, "COLLISION_SOURCE_UNRESOLVED", model_path)
    package = "res/packages/" + PACKAGE_FOLDERS[match.group(1)]
    stem = model_path[:-len(".model")]
    part = match.group(3)
    raws = {}
    for suffix in ("model", "visual", "primitives"):
        raw = src.member(package, stem + "." + suffix)
        refuse_if(raw is None, "COLLISION_SOURCE_UNRESOLVED", stem + "." + suffix)
        raws[suffix] = raw
    try:
        model = flat(raws["model"])
        visual = flat(raws["visual"])
        require(model.get("/nodelessVisual[1]") == stem, "collision model/visual binding")
        require(visual.get("/node[1]/identifier[1]") == "Scene Root" and
                visual.get("/node[1]/transform[1]") == [1., 0., 0., 0., 1., 0., 0., 0., 1., 0., 0., 0.], "nonidentity visual root")
        require(visual.get("/renderSet[1]/treatAsWorldSpaceObject[1]") is False, "world-space collision mesh")
        m = mesh(raws["primitives"])
        groups = {k for k in visual if re.fullmatch(r"/renderSet\[1\]/geometry\[1\]/primitiveGroup\[[0-9]+\]", k)}
        require(len(groups) == len(m["groups"]), "visual primitive group count")
        require(materials._string(visual.get("/renderSet[1]/geometry[1]/vertices[1]"), "vertex reference") == "vertices"
                and visual.get("/renderSet[1]/geometry[1]/primitive[1]") == "indices", "visual primitive references")
        triangles, labels, excluded = [None] * (len(m["ids"]) // 3), set(), []
        for n, group in enumerate(m["groups"], 1):
            path = "/renderSet[1]/geometry[1]/primitiveGroup[" + str(n) + "]"
            label = visual.get(path + "/material[1]/identifier[1]")
            require(label in materials.EXPECTED_KINDS, "unmapped material kind " + str(label))
            require(visual.get(path) == n - 1 and visual.get(path + "/material[1]/materialKind[1]") == materials.EXPECTED_KINDS[label]
                    and visual.get(path + "/material[1]/collisionFlags[1]") == 0, "primitive material binding")
            require(group["start_index"] % 3 == 0 and group["triangle_count"] > 0, "primitive group range")
            labels.add(label)
            for t in range(group["start_index"] // 3, group["start_index"] // 3 + group["triangle_count"]):
                require(t < len(triangles) and triangles[t] is None, "triangle overlap/outside group")
                a, b, c = m["ids"][3 * t:3 * t + 3]
                require(all(group["start_vertex"] <= x < group["start_vertex"] + group["vertex_count"] for x in (a, b, c)),
                        "triangle escapes group vertices")
                triangle = dict(triangle_id=index * 100000 + t, a=a, b=b, c=c, material=label, mesh=part,
                                group="primitiveGroup[" + str(n) + "]")
                if zero_area(m["vertices"], a, b, c):
                    excluded.append(triangle["triangle_id"])
                triangles[t] = triangle
        require(all(t is not None for t in triangles), "triangle coverage gap")
        entries = []
        for label in sorted(set(effective) | labels, key=lambda k: materials.EXPECTED_KINDS[k]):
            record = effective.get(label)
            if record is not None:
                materials._validate_effective(record, materials.EXPECTED_KINDS[label])
            entries.append(dict(name=label, kind=materials.EXPECTED_KINDS[label], effective=record))
        visual_bounds = [vector(visual["/boundingBox[1]/" + edge + "[1]"], 3, "visual bounds") for edge in ("min", "max")]
    except (*SOURCE_ERRORS, materials.BundleError, ValueError, KeyError, TypeError) as error:
        raise Refused("COLLISION_SOURCE_UNSUPPORTED", part + ": " + str(error)) from error
    members = {package + "!" + stem + "." + s: pin(raws[s]) for s in ("model", "visual", "primitives")}
    return dict(name=part, vertex_format=m["format"], vertices=m["vertices"], triangles=triangles, materials=entries,
                visual_bounds=visual_bounds, mesh_bounds=m["bounds"], excluded_degenerate_triangle_ids=excluded), members


def _num(value, label, maximum=1_000_000, minimum=0):
    if isinstance(value, list):
        require(len(value) == 1, label + " scalar count")
        value = value[0]
    return number(value, label, minimum, maximum)


def _int(value, label, maximum):
    result = _num(value, label, maximum)
    require(result == int(result), label + " integer")
    return int(result)


def shots(src, nation, gun, mounted_path, vehicle_flat, guns, shells, factor):
    nf = NATIONS.index(nation)
    shared = "/shared[1]/" + gun + "[1]"
    refuse_if(any(k.startswith(mounted_path + "/shots[") for k in vehicle_flat),
              "MOUNTED_SHOT_OVERRIDE_UNSUPPORTED", gun)
    prefix = shared + "/shots[1]/"
    names = [k[len(prefix):-3] for k in guns if k.startswith(prefix) and k.count("/") == 4]
    refuse_if(not 1 <= len(names) <= 3, "SHELL_SOURCE_UNSUPPORTED", gun + " shot count " + str(len(names)))
    rows = []
    for index, shell in enumerate(names):
        sp, shot = "/" + shell + "[1]", prefix + shell + "[1]"
        family = shells.get(sp + "/kind[1]")
        refuse_if(family not in FAMILIES, "SHELL_SOURCE_UNSUPPORTED", shell + " kind " + str(family))
        radius = shells.get(sp + "/explosionRadius[1]")
        refuse_if((radius is not None) != (family == "HIGH_EXPLOSIVE"), "SHELL_SOURCE_UNSUPPORTED", shell + " HE radius presence")
        item = _int(shells[sp + "/id[1]"], "shell ID", 65535)
        speed, gravity = _num(guns[shot + "/speed[1]"], "speed", 5000), _num(guns[shot + "/gravity[1]"], "gravity", 1000)
        loss = shells.get(sp + "/piercingPowerLossFactorByDistance[1]")
        rows.append(dict(index=index, resource=shell, item_id=item, compact_descr=(item << 8) + (nf << 4) + 10, family=family,
            caliber_mm=_num(shells[sp + "/caliber[1]"], "caliber", 1000),
            damage_hp=_int(shells[sp + "/damage[1]/armor[1]"], "damage", 20000),
            device_damage=_int(shells[sp + "/damage[1]/devices[1]"], "device damage", 10000),
            penetration_mm=vector(guns[shot + "/piercingPower[1]"], 2, "penetration"),
            explosion_radius_m=None if radius is None else _num(radius, "explosion radius", 100),
            raw_speed_mps=speed, speed_mps=speed * factor, raw_gravity_mps2=gravity, gravity_mps2=gravity * factor ** 2,
            max_distance_m=_num(guns[shot + "/maxDistance[1]"], "max distance", 10000),
            premium_gold_flag=sp + "/price[1]/gold[1]" in shells, effects_resource=shells.get(sp + "/effects[1]"),
            piercing_power_loss_factor_by_distance=None if loss is None else _num(loss, "HEAT loss", 1),
            projectile_speed_factor=factor))
    return rows


def _supports(chassis_flat, chassis):
    groups, wheels = [], []
    for index in range(1, 65):
        p = chassis + "/wheels[1]/group[" + str(index) + "]"
        if p in chassis_flat:
            groups.append(dict(template=chassis_flat[p + "/template[1]"], is_left=chassis_flat[p + "/isLeft[1]"],
                               radius=_num(chassis_flat[p + "/radius[1]"], "wheel radius", 10)))
        p = chassis + "/wheels[1]/wheel[" + str(index) + "]"
        if p in chassis_flat:
            wheels.append(dict(name=chassis_flat[p + "/name[1]"], is_left=chassis_flat[p + "/isLeft[1]"],
                               radius=_num(chassis_flat[p + "/radius[1]"], "wheel radius", 10)))
    for collection, field, names, rule in ((groups, "template", ("W_L", "W_R"), "group-W_L-W_R"),
                                           (wheels, "name", ("W_L0", "W_R0"), "named-W_L0-W_R0")):
        rows = [r for r in collection if r[field] in names]
        if len(rows) == 2 and {r[field] for r in rows} == set(names):
            left, right = (next(r for r in rows if r[field] == n) for n in names)
            if left["is_left"] is True and right["is_left"] is False and left["radius"] == right["radius"]:
                return rule, left["radius"], groups, wheels
    raise Refused("SUPPORT_SOURCE_UNRESOLVED", "no equal W_L/W_R group or W_L0/W_R0 wheel pair")


def vehicle_row(src, catalog, vehicle_id, defaults, factor):
    v = catalog.vehicles[vehicle_id]
    nation, resource = v["nation"], v["resource_name"]
    kind = next(t for t in v["tags"] if t in CLASSES)
    d = v["defaults"]
    names = {k: d[k].split(":")[-1] for k in MODULE_KINDS}
    base = PREFIX + nation + "/"
    vf = src.xml(v["source"])
    comp = {k: src.xml(base + "components/" + k + ".xml") for k in COMPONENT_FILES}
    chassis, turret = "/chassis[1]/" + names["chassis"] + "[1]", "/turrets0[1]/" + names["turret"] + "[1]"
    gun = turret + "/guns[1]/" + names["gun"] + "[1]"
    shared_gun = "/shared[1]/" + names["gun"] + "[1]"
    gf = comp["guns"]
    mounted = lambda field: vf.get(gun + "/" + field + "[1]", gf.get(shared_gun + "/" + field + "[1]"))
    mounted_sub = lambda path: vf.get(gun + "/" + path + "[1]", gf.get(shared_gun + "/" + path + "[1]"))
    nid, cid = NATIONS.index(nation), v["nation_id"]
    fix = lambda compact: (compact >> 8 << 8) | (nid << 4) | (compact & 15)
    require(all(catalog.modules[d[k]]["native_compact_id"] >> 4 & 15 == cid for k in MODULE_KINDS)
            and v["native_compact_id"] >> 4 & 15 == cid, vehicle_id + ": catalogue nation nibble")
    raw_cd = descriptor(catalog, dict(vehicle_id=vehicle_id, modules=d))
    require(raw_cd[0] == (cid << 4) | 1, vehicle_id + ": descriptor header")
    cd = (bytes([(nid << 4) | 1]) + raw_cd[1:]).hex()
    mass_kg = (v["hull_mass_grams"] + sum(v["module_mass_grams"][d[k]] for k in MODULE_KINDS)) / 1000
    row = dict(vehicle_id=vehicle_id, nation=nation, native_nation_id=nid, resource=resource, tier=v["tier"],
               vehicle_class=kind, existing_kind=EXISTING.get(vehicle_id),
               research_catalog_nation_id=cid, catalog_nation_correction_required=nid != cid,
               identity=dict(type_compact_id=fix(v["native_compact_id"]), descriptor_hex=cd, modules=d,
                             module_compact_ids={k: fix(catalog.modules[d[k]]["native_compact_id"]) for k in MODULE_KINDS},
                             crew_roles=v["crew_roles"], max_hp=v["hull_max_hp"] + v["turret_max_hp"][d["turret"]],
                             mass_kg=mass_kg, source=v["source"]))
    decision = None
    try:
        clip, burst = mounted("clip"), mounted("burst")
        clip_count = _int(mounted_sub("clip[1]/count"), "clip count", 1000) if clip is not None else 1
        clip_rate = _num(mounted_sub("clip[1]/rate"), "clip rate", 10000) if clip is not None else None
        yaw = mounted("turretYawLimits")
        extra = {k[len(gun + "/extraPitchLimits[1]/"):-3]: vf[k] for k in vf
                 if k.startswith(gun + "/extraPitchLimits[1]/") and k.count("/") == 6}
        row["gun"] = dict(resource=names["gun"], max_ammo=_int(mounted("maxAmmo"), "maxAmmo", 2000),
            reload_seconds=_num(mounted("reloadTime"), "reload", 600), aiming_seconds=_num(mounted("aimingTime"), "aiming", 60),
            shot_dispersion_radius=_num(mounted("shotDispersionRadius"), "dispersion", 10),
            clip_count=clip_count, clip_rate_per_minute=clip_rate,
            clip_interval_seconds=60.0 / clip_rate if clip_count > 1 else 0.0,
            clip_source="MOUNTED_OR_SHARED" if clip is not None else "ORIGINAL_LOADER_DEFAULT",
            burst=burst is not None, pitch_limits=vector(mounted("pitchLimits"), 2, "pitch limits"),
            extra_pitch_limits=extra or None, turret_yaw_limits=None if yaw is None else vector(yaw, 2, "yaw limits"),
            gun_rotation_deg_s=_num(gf[shared_gun + "/rotationSpeed[1]"], "gun yaw"),
            turret_rotation_deg_s=_num(vf[turret + "/rotationSpeed[1]"], "turret yaw"),
            mount_source_path=v["source"] + ":" + gun)
        row["view_range_m"] = _num(vf[turret + "/circularVisionRadius[1]"], "vision radius", 2000)
        movement = dict(engine_power_hp=_num(comp["engines"]["/shared[1]/" + names["engine"] + "[1]/power[1]"], "power", 10000),
            speed_limits_kmh=[_num(vf["/speedLimits[1]/" + n + "[1]"], "speed", 200) for n in ("forward", "backward")],
            chassis_rotation_deg_s=_num(vf[chassis + "/rotationSpeed[1]"], "chassis yaw"),
            brake_force_source=_num(vf[chassis + "/brakeForce[1]"], "brake force", 10_000_000),
            carrying_point=vector(vf[chassis + "/topRightCarryingPoint[1]"], 2, "carrying point"),
            terrain_resistance=vector(vf[chassis + "/terrainResistance[1]"], 3, "terrain resistance"),
            rotation_is_around_center=vf[chassis + "/rotationIsAroundCenter[1]"])
        row["movement"] = movement
        pivots = dict(hull_position=vector(vf[chassis + "/hullPosition[1]"], 3, "hull position"),
                      turret_position=vector(vf["/hull[1]/turretPositions[1]/turret[1]"], 3, "turret position"),
                      gun_position=vector(vf[turret + "/gunPosition[1]"], 3, "gun position"))
        row["pivots"] = pivots
    except (*SOURCE_ERRORS, KeyError, TypeError) as error:
        raise ProfileError(vehicle_id + ": source fact: " + str(error)) from error
    try:
        refuse_if(kind == "SPG", "SPG_INDIRECT_FIRE_OUT_OF_SCOPE", "SPG")
        refuse_if(row["gun"]["burst"] or not 1 <= clip_count <= MAX_CLIP, "AUTOMATIC_GUN_UNSUPPORTED",
                  "burst" if row["gun"]["burst"] else "clip " + str(clip_count))
        try:
            row["shots"] = shots(src, nation, names["gun"], gun, vf, gf, comp["shells"], factor)
        except (*SOURCE_ERRORS, KeyError, TypeError) as error:
            raise ProfileError(vehicle_id + ": shell fact: " + str(error)) from error
        rule, radius, groups, wheels = _supports(vf, chassis)
        carrying, speed = movement["carrying_point"], movement["speed_limits_kmh"]
        node = decode(src.file(v["source"]), max_bytes=MAX_SOURCE, max_depth=32, max_nodes=60000)
        bundle_components, members = [], {}
        for index, (path, label) in enumerate(((("hull",), "/hull[1]"), (("turrets0", names["turret"]), turret),
                                              (("turrets0", names["turret"], "guns", names["gun"]), gun))):
            model = vf.get(label + "/hitTester[1]/collisionModel[1]")
            refuse_if(model is None, "COLLISION_SOURCE_UNRESOLVED", label + " hitTester")
            try:
                fields = materials._children(materials._section(node, path), "active component")
                effective = _effective(fields["armor"], defaults)
            except (*SOURCE_ERRORS, materials.BundleError, KeyError) as error:
                raise Refused("COLLISION_SOURCE_UNSUPPORTED", label + " armour: " + str(error)) from error
            built, pins = component(src, model, index, effective)
            bundle_components.append(built)
            members.update(pins)
        hull = bundle_components[0]["mesh_bounds"]
        lo, hi, hp = hull["min"], hull["max"], pivots["hull_position"]
        physics = dict(body_half_extents=[(hi[j] - lo[j]) / 2 for j in range(3)],
            body_center_offset=[(hi[j] + lo[j]) / 2 + hp[j] for j in range(3)],
            wheel_points=[[x, radius + .28, z] for x in (-carrying[0], carrying[0]) for z in (-carrying[1], 0, carrying[1])],
            mass_kg=mass_kg, max_forward_mps=speed[0] * .27778, max_reverse_mps=speed[1] * .27778,
            engine_max_torque_nm=movement["engine_power_hp"] * 735.5 / (2 * math.pi * 2500 / 60), wheel_radius=radius,
            suspension_min=.1, suspension_max=.35, track_max_brake_torque=movement["brake_force_source"] * 9.81 * radius / 2,
            longitudinal_friction=1.2, lateral_friction=1., stationary_steering_ratio=.2)
        handling = dict(version=1, policy="p05b-track-yaw-v1", max_yaw_rate_rad_s=math.radians(movement["chassis_rotation_deg_s"]))
        for field, (low, high) in ENVELOPE.items():
            value = handling[field] if field in handling else physics[field]
            refuse_if(not low <= value <= high, "PHYSICS_ENVELOPE_EXCEEDED", field + "=" + repr(value))
        refuse_if(not all(.1 <= x <= 5 for x in physics["body_half_extents"]) or
                  not all(-5 <= x <= 5 for x in physics["body_center_offset"]) or
                  not all(-5 <= x <= 5 for p in physics["wheel_points"] for x in p), "PHYSICS_ENVELOPE_EXCEEDED", "body/support bounds")
        bundle = dict(schema=BUNDLE_SCHEMA, vehicle_id=vehicle_id, classification="VERIFIED_STATIC_ORIGINAL_717",
            identity=row["identity"], members=dict(sorted(members.items())),
            wheel_source=dict(groups=groups, individual_wheels=wheels),
            geometry=dict(**pivots, components=bundle_components), battle_admission=False)
        raw = canonical(bundle) + b"\n"
        require(len(raw) <= MAX_BUNDLE, vehicle_id + ": bundle size bound")
        row["physics"] = physics
        row["handling"] = handling
        row["support_rule"] = rule
        row["hull_aabb"] = hull
        row["geometry"] = dict(bundle=bundle_name(row), bytes=len(raw), sha256=sha(raw),
                               components=[dict(name=c["name"], vertex_format=c["vertex_format"],
                                                vertices=len(c["vertices"]), triangles=len(c["triangles"]),
                                                excluded_degenerate=len(c["excluded_degenerate_triangle_ids"]))
                                           for c in bundle_components])
        decision = dict(status="generated", refusal=None, detail=None)
    except Refused as refusal:
        raw = None
        decision = dict(status="refused", refusal=refusal.code, detail=refusal.detail)
    row.update(decision)
    row["battle_admission"] = False
    row["readiness_code"] = "BATTLE_PROFILE_UNSUPPORTED"
    return row, raw


def bundle_name(row):
    return row["nation"] + "-" + row["resource"] + ".json"


def build(original):
    src = Sources(original)
    catalog = load_catalog(src.root)
    require(catalog.sha256 == CATALOG_SHA256, "research catalogue differs")
    # Pinned material sources first: the same defaults as P04M/MS-1 bundles.
    for rel, expected in materials.FILE_PINS.items():
        if rel.startswith("res/"):
            raw = src.file(rel)
            require(pin(raw) == expected, "material source pin differs: " + rel)
    for rel in (materials.KINDS_LOADER_REL, materials.VEHICLE_REL):
        parse_pyc(src.file(rel))
    nations = parse_pyc(src.file("res/scripts/common/nations.pyc"))
    require([n.encode() for n in NATIONS] in nations["consts"] and b"NAMES" in nations["names"], "original nation IDs differ")
    kinds = src.member(materials.MISC_REL, materials.KINDS_MEMBER)
    require(src.packages[materials.MISC_REL] == materials.PACKAGE_PINS[materials.MISC_REL], "misc package pin differs")
    require(kinds is not None and pin(kinds) == materials.MEMBER_PINS[materials.KINDS_KEY], "material kinds pin differs")
    loader = materials._loader_defaults(src.file(materials.LOADER_REL))
    mapping = materials._kind_mapping(decode(kinds, max_bytes=MAX_MEMBER))
    defaults = materials._common_materials(decode(src.file(materials.COMMON_REL), max_bytes=MAX_MEMBER), mapping, loader)
    common = src.xml(materials.COMMON_REL)
    factor = _num(common["/miscParams[1]/projectileSpeedFactor[1]"], "projectile factor", 1)
    require(factor == .8, "projectile speed factor differs")
    rows, bundles = [], {}
    for vehicle_id in sorted(catalog.vehicles):
        row, raw = vehicle_row(src, catalog, vehicle_id, defaults, factor)
        rows.append(row)
        if raw is not None:
            bundles[bundle_name(row)] = raw
    table = dict(schema=SCHEMA, target="v.0.9.1 #717 RU", research_catalog_sha256=CATALOG_SHA256, policy=POLICY,
                 source_pins=src.pins(), vehicles=rows)
    raw = canonical(table) + b"\n"
    require(len(raw) <= MAX_TABLE, "table size bound")
    return raw, bundles


def export(original, out, update=False):
    local = no_links(ROOT / "local").resolve(strict=True)
    out = owned(local, Path(out).absolute())
    require(not out.exists() and out.parent.is_dir(), "fresh output with existing parent required")
    raw, bundles = build(original)
    committed = TABLE.read_bytes() if TABLE.is_file() else None
    require(update or committed is None or committed == raw, "generated table differs from committed; use --update")
    out.mkdir()
    (out / "bundles").mkdir()
    for name, data in sorted(bundles.items()):
        with (out / "bundles" / name).open("xb") as stream:
            stream.write(data)
    with (out / "battle_profiles.v1.json").open("xb") as stream:
        stream.write(raw)
    if update or committed is None:
        TABLE.write_bytes(raw)
        BINDING.write_bytes(binding(raw))
    table = json.loads(raw)
    counts = {}
    for row in table["vehicles"]:
        key = row["status"] if row["refusal"] is None else row["refusal"]
        counts[key] = counts.get(key, 0) + 1
    receipt = dict(schema="battle-any-export.v1", status="PASS_PINNED_SOURCE_EXPORT", table_sha256=sha(raw), table_bytes=len(raw),
                   vehicles=len(table["vehicles"]), counts=dict(sorted(counts.items())), bundles=len(bundles),
                   bundles_sha256=sha(canonical({k: sha(v) for k, v in sorted(bundles.items())})),
                   committed_table_changed=committed is not None and committed != raw,
                   runtime_registration=False, native="NOT_RUN", client_bytecode_executed=False)
    with (out / "receipt.json").open("xb") as stream:
        stream.write(canonical(receipt) + b"\n")
    return receipt


def binding(raw):
    lines = ('"""GENERATED by tools/battle_any_profiles.py from config/catalog/battle_profiles.v1.json; do not edit."""',
             "SCHEMA = %r" % SCHEMA, "TABLE_SHA256 = %r" % sha(raw), "TABLE_BYTES = %d" % len(raw))
    return ("\n".join(lines) + "\n").encode("ascii")


def check(path=TABLE):
    raw = path.read_bytes()
    require(0 < len(raw) <= MAX_TABLE, "table size")
    table = json.loads(raw)
    require(canonical(table) + b"\n" == raw, "table is not canonical")
    require(table["schema"] == SCHEMA and table["policy"] == POLICY and table["research_catalog_sha256"] == CATALOG_SHA256, "table header")
    seen = set()
    for row in table["vehicles"]:
        require(row["vehicle_id"] not in seen, "duplicate vehicle")
        seen.add(row["vehicle_id"])
        require(row["battle_admission"] is False and row["readiness_code"] == "BATTLE_PROFILE_UNSUPPORTED", "row grants admission")
        require((row["status"] == "generated") == (row["refusal"] is None) and row["status"] in ("generated", "refused"), "row decision")
        require(row["refusal"] is None or row["refusal"] in REFUSALS, "unknown refusal")
        if row["status"] == "generated":
            require({"physics", "handling", "geometry", "shots", "gun"} <= set(row), "generated row incomplete")
    require([r["vehicle_id"] for r in table["vehicles"]] == sorted(seen), "vehicle order")
    require(path != TABLE or BINDING.read_bytes() == binding(raw), "generated binding differs from table")
    return dict(status="PASS", table_sha256=sha(raw), vehicles=len(seen),
                generated=sum(r["status"] == "generated" for r in table["vehicles"]))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build")
    b.add_argument("--original", type=Path, required=True)
    b.add_argument("--out", type=Path, required=True)
    b.add_argument("--update", action="store_true")
    sub.add_parser("check")
    args = parser.parse_args(argv)
    try:
        result = export(args.original, args.out, args.update) if args.command == "build" else check()
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps(dict(status="FAIL_BATTLE_ANY", reason=str(error))))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
