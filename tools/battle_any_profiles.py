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
import test_vehicles  # noqa: E402
# TESTVEH-01: WOT091_TEST_LAB=1 builds/checks the test_lab variant (config/test_lab,
# *_test_lab bindings); the main variant never contains a test vehicle.
TEST_LAB = test_vehicles.enabled()
# CONTENT-0 2.5b (test_lab): collision primitive groups and component <armor> records may also name the
# device/crew kinds of material_kinds.xml (ms1_contact_bundle.DEVICE_KINDS); main keeps the MS-1 set.
KINDS = materials.ALL_KINDS  # CONTENT-0 main transfer (owner 12.11): device/crew kinds for main too
# SPG-01 (owner 2026-11-09): the SPGs admitted on a test_lab stand, those the runtime can take now.
# The main variant refuses every SPG; one- and two-shell SPGs need a separate card.
STAND_SPG = frozenset("vehicle:" + name for name in (
    "france:Bat_Chatillon155_58", "france:Lorraine155_51", "germany:Bison_I", "germany:G_E", "germany:Grille",
    "germany:Sturmpanzer_II", "uk:GB28_Bishop", "uk:GB78_Sexton_I", "usa:Sexton_I", "usa:T92", "ussr:Object_212",
    "ussr:Object_261", "ussr:S-51", "ussr:SU-14", "ussr:SU-5"))
_DIR = test_vehicles.TEST_LAB_DIR if TEST_LAB else ROOT / "config" / "catalog"
_SUFFIX = "_test_lab" if TEST_LAB else ""
TABLE = _DIR / "battle_profiles.v1.json"
BINDING = TOOLS / ("battle_any_data%s.py" % _SUFFIX)
# CONTENT-0 3.3: exact pin of the build table for the domain reader (tools/content0_builds.py).
BUILDS_BINDING = TOOLS / ("battle_builds_data%s.py" % _SUFFIX)
PHYSICS_DEFINITIONS = (_DIR / "generated-definitions.json" if TEST_LAB
                       else ROOT / "server" / "physics" / "Profiles" / "generated-definitions.json")
GENERATED_POLICY = "battle-any-generated-v1"
QUALIFICATION = _DIR / "battle_qualification.v1.json"
QUALIFICATION_SCHEMA = "wot091-battle-qualification.v1"
RUST_PINS = ROOT / "server" / "gateway" / "src" / "shared" / ("battle_any_pins%s.rs" % _SUFFIX)
CATALOG_SHA256 = test_vehicles.research_sha256()
# Original res/scripts/common/nations.pyc order (verified in build, as P06T does).
# Since CAT-NATIONS the P09E research catalogue uses the same order; a row whose
# catalogue nation differs is a build failure (the fields stay as the guard).
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
MAX_BUNDLE = 512 * 1024  # gateway geometry::MAX_BYTES
# Mounted single-shot/drum limit of the accepted P06T armament state machine
# (`battle/armament.rs`, clip_count 1..=6, no burst). Not a historical rule.
MAX_CLIP = 6
# CONTENT-0 2.6 (test_lab only): server-scheduled bursts and long clips of the
# automatic guns (`battle/armament.rs` MAX_CLIP/MAX_BURST). The 0.9.1 loader
# reads `clip` and `burst` as whole sections (vehicle section overrides the
# shared one; absent = (1, 0.0)); interval = 60/rate when count > 1, else 0.
MAX_CLIP_TEST_LAB = 64
MAX_BURST = 10
PHYSICS_POLICY = "p06t-extended-six-support-v2"
SUPPORT_RADIUS = "named-equal-main-W_L0-W_R0-or-group-W_L-W_R"
# Numeric envelope enforced by server/physics StockVehicleProfiles/Extended
# ValidateProjection; a vehicle outside it is refused, never clamped.
ENVELOPE = {"mass_kg": (1000, 200000), "max_forward_mps": (1, 25), "max_reverse_mps": (.5, 15),
            "engine_max_torque_nm": (10, 10000), "wheel_radius": (.05, 1),
            "track_max_brake_torque": (100, 300000), "max_yaw_rate_rad_s": (.1, 1.5)}
# Constant per-row projection mapping, identical to extended-definitions.json.
MAPPING = {"policy": PHYSICS_POLICY, "classification": "INFERRED_TEST_LAB_ONLY", "historical_fidelity": False,
           "support_radius": SUPPORT_RADIUS, "support_count": 6, "support_y_offset": .28,
           "motion_quality": "Discrete", "collision_steps_per_60hz": 4}
REFUSALS = ("SPG_INDIRECT_FIRE_OUT_OF_SCOPE", "AUTOMATIC_GUN_UNSUPPORTED", "MOUNTED_SHOT_OVERRIDE_UNSUPPORTED",
            "SHELL_SOURCE_UNSUPPORTED", "PHYSICS_ENVELOPE_EXCEEDED", "SUPPORT_SOURCE_UNRESOLVED",
            "COLLISION_SOURCE_UNRESOLVED", "COLLISION_SOURCE_UNSUPPORTED", "AIM_ENVELOPE_UNSUPPORTED")
POLICY = {
    "id": "test_lab.battle-any.v1",
    "classification": "VERIFIED_STATIC_ORIGINAL_717_FACTS_WITH_EXPLICIT_TEST_LAB_PROJECTION",
    "assembly": "catalogue stock defaults only; non-stock modules are not profiled",
    "physics": {"envelope": {k: list(v) for k, v in ENVELOPE.items()},
                "mapping": MAPPING},
    "damage_model": "P06T single-plate test_lab on proxy AABB armour (unchanged by this card)",
    "armament": {"max_clip": MAX_CLIP_TEST_LAB, "max_burst": MAX_BURST, "burst": "server-scheduled-test_lab-v1"},
    "spg": "admitted: SPG-01/02 rules (one to three shells); bots take no SPG until indirect fire (8a decision B)",
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


def _f32(x):
    return struct.unpack("<f", struct.pack("<f", x))[0]


def _rad32(degrees):
    # Gateway `rad`: (deg * (PI / 180)) in f64, then one cast to f32.
    return _f32(degrees * (math.pi / 180.0))


def aim_envelope_supported(envelope, yaw_limits):
    """Same bounds as gateway `SourceEnvelope::validate` (f32): limits within
    +-pi/2 and ordered, transition in (0, pi], sectors in [0, pi] and
    front + back + 2 * transition <= pi, turret yaw within +-pi. How #717
    resolves overlapping front/back sectors is UNKNOWN, so it is refused."""
    half, pi = _f32(math.pi / 2), _f32(math.pi)
    basic = [_rad32(x) for x in envelope["basic"]]
    extra = {k: None if envelope[k] is None else [_rad32(x) for x in envelope[k]] for k in ("front", "back")}
    transition = _f32(0.4) if envelope["transition_degrees"] is None else _rad32(envelope["transition_degrees"])
    front, back = (extra[k] or basic + [0.0] for k in ("front", "back"))
    limits = [basic, front[:2], back[:2], [min(basic[0], front[0], back[0]), max(basic[1], front[1], back[1])]]
    if not all(-half <= lo <= hi <= half for lo, hi in limits) or not 0 < transition <= pi:
        return False
    if not all(0 <= x <= pi for x in (front[2], back[2])):
        return False
    if _f32(_f32(front[2] + back[2]) + _f32(2 * transition)) > pi:
        return False
    if yaw_limits is not None and not (yaw_limits[0] <= -180 and yaw_limits[1] >= 180):
        lo, hi = _rad32(yaw_limits[0]), _rad32(yaw_limits[1])
        if not -pi <= lo <= hi <= pi:
            return False
    return True


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


def _regen(value):
    """maxRegenHealth; a fractional source value (GB28_Bishop 27.5) rounds down (SPG-01, project policy)."""
    number = float(value)
    require(0 < number <= 100000, "device regen")
    return int(number)


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


def child_section(node, name, label):
    """CONTENT-0 2.5b (test_lab): the one child `name` of a packed-XML section, like a DataSection
    lookup. Other children may repeat (IS `_85mm_D-5T` has two `animateEmblemSlots`, True/False); the
    needed section itself must be unique."""
    require(isinstance(node, dict) and set(node) == {"value", "children"} and isinstance(node["children"], list)
            and len(node["children"]) <= 1024, label + " is not a bounded XML section")
    require(all(isinstance(c, dict) and set(c) == {"name", "data"} and isinstance(c["name"], str)
                and 0 < len(c["name"]) <= 128 for c in node["children"]), label + " invalid XML child")
    found = [c["data"] for c in node["children"] if c["name"] == name]
    require(len(found) == 1, label + " missing/duplicate " + name)
    return found[0]


def active_armor(node, path):
    """The <armor> section of one active component (hull, turret, gun)."""
    for name in path:
        node = child_section(node, name, "active component")
    return child_section(node, "armor", "active component")


def visual_binding(model, visual, stem):
    """The collision .model names its visual. Main: `nodelessVisual` equal to the stem. CONTENT-0 2.5b
    (test_lab): `nodefullVisual` too (all 22 such #717 collision models, VK4502P and GB22_Comet), when its
    render set is bound to the identity `Scene Root` alone and the mesh lies inside the visual bounding
    box, i.e. the vertices are in the component frame like a nodeless visual's (INFERRED, the child node
    transforms are not applied). Returns the visual box a nodefull mesh must lie in, else None."""
    keys = [k for k in ("/nodelessVisual[1]", "/nodefullVisual[1]") if k in model]
    allowed = [["/nodelessVisual[1]"], ["/nodefullVisual[1]"]]
    require(keys in allowed and model[keys[0]] == stem, "collision model/visual binding")
    require(visual.get("/node[1]/identifier[1]") == "Scene Root" and
            visual.get("/node[1]/transform[1]") == [1., 0., 0., 0., 1., 0., 0., 0., 1., 0., 0., 0.], "nonidentity visual root")
    require(visual.get("/renderSet[1]/treatAsWorldSpaceObject[1]") is False, "world-space collision mesh")
    if keys[0] != "/nodefullVisual[1]":
        return None
    require(visual.get("/renderSet[1]/node[1]") == "Scene Root" and "/renderSet[1]/node[2]" not in visual
            and "/renderSet[2]" not in visual and "/node[2]" not in visual, "nodefull render set binding")
    return [vector(visual["/boundingBox[1]/" + edge + "[1]"], 3, "visual bounds") for edge in ("min", "max")]


def inside_box(bounds, box, tolerance=1e-3):
    return all(box[0][j] - tolerance <= bounds["min"][j] and bounds["max"][j] <= box[1][j] + tolerance for j in range(3))


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
        nodefull_box = visual_binding(model, visual, stem)
        m = mesh(raws["primitives"])
        require(nodefull_box is None or inside_box(m["bounds"], nodefull_box), "nodefull mesh outside visual bounds")
        groups = {k for k in visual if re.fullmatch(r"/renderSet\[1\]/geometry\[1\]/primitiveGroup\[[0-9]+\]", k)}
        require(len(groups) == len(m["groups"]), "visual primitive group count")
        require(materials._string(visual.get("/renderSet[1]/geometry[1]/vertices[1]"), "vertex reference") == "vertices"
                and visual.get("/renderSet[1]/geometry[1]/primitive[1]") == "indices", "visual primitive references")
        triangles, labels, excluded = [None] * (len(m["ids"]) // 3), set(), []
        for n, group in enumerate(m["groups"], 1):
            path = "/renderSet[1]/geometry[1]/primitiveGroup[" + str(n) + "]"
            label = visual.get(path + "/material[1]/identifier[1]")
            # Packed XML keeps some strings base64 ("fuelTank" of A18_M41/G73_E50_Ausf_M Hull), as for kind names.
            label = materials._string(label, "primitive material") if isinstance(label, dict) else label
            require(label in KINDS, "unmapped material kind " + str(label))
            require(visual.get(path) == n - 1 and visual.get(path + "/material[1]/materialKind[1]") == KINDS[label]
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
        for label in sorted(set(effective) | labels, key=lambda k: KINDS[k]):
            record = effective.get(label)
            if record is not None:
                materials._validate_effective(record, KINDS[label])
            entries.append(dict(name=label, kind=KINDS[label], effective=record))
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


def shots(src, nation, gun, mounted_path, vehicle_flat, guns, shells, factor, effects):
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
        effect = materials._string(shells[sp + "/effects[1]"], "shot effects")
        refuse_if(effect not in effects, "SHELL_SOURCE_UNSUPPORTED", shell + " effects " + effect)
        rows.append(dict(index=index, resource=shell, item_id=item, compact_descr=(item << 8) + (nf << 4) + 10, family=family,
            caliber_mm=_num(shells[sp + "/caliber[1]"], "caliber", 1000),
            damage_hp=_int(shells[sp + "/damage[1]/armor[1]"], "damage", 20000),
            device_damage=_int(shells[sp + "/damage[1]/devices[1]"], "device damage", 10000),
            penetration_mm=vector(guns[shot + "/piercingPower[1]"], 2, "penetration"),
            explosion_radius_m=None if radius is None else _num(radius, "explosion radius", 100),
            raw_speed_mps=speed, speed_mps=speed * factor, raw_gravity_mps2=gravity, gravity_mps2=gravity * factor ** 2,
            max_distance_m=_num(guns[shot + "/maxDistance[1]"], "max distance", 10000),
            premium_gold_flag=sp + "/price[1]/gold[1]" in shells, effects_resource=effect,
            effects_index=effects.index(effect),
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
    # CONTENT-0 2.3 (main since the 12.11 transfer): many #717 chassis list several W_L/W_R road-wheel groups, or the two sides differ by
    # the client's float rounding (Tiger II 0.41715100 / 0.41715, M48A1 0.2 mm). Every W_L group on the left and every
    # W_R group on the right, each side within 1 mm, the two sides within 2 mm: the support radius is their mean.
    left = [g["radius"] for g in groups if g["template"] == "W_L" and g["is_left"] is True]
    right = [g["radius"] for g in groups if g["template"] == "W_R" and g["is_left"] is False]
    if (left and right and max(left) - min(left) <= 0.001 and max(right) - min(right) <= 0.001
            and abs(sum(left) / len(left) - sum(right) / len(right)) <= 0.002):
        return "groups-W_L-W_R-2mm", (sum(left) + sum(right)) / (len(left) + len(right)), groups, wheels
    # CONTENT-0 2.3b: four more #717 chassis. B1 mixes 101.9 and 99.7 mm bogie wheels on one side, FV206
    # 267.3 and 268.9 mm; ELC AMX lists 272.3 mm left and 263.7 mm right; TOG II names every road wheel group
    # WD_L/WD_R and has no W_ group. The radius only sets the ride height: road groups W_ (WD_ when no W_ group
    # exists), each side within 5 mm, the sides within 10 mm, the mean radius.
    has_w = any(g["template"] in ("W_L", "W_R") for g in groups)
    prefix = "W" if has_w else "WD"
    left = [g["radius"] for g in groups if g["template"] == prefix + "_L" and g["is_left"] is True]
    right = [g["radius"] for g in groups if g["template"] == prefix + "_R" and g["is_left"] is False]
    if (left and right and max(left) - min(left) <= 0.005 and max(right) - min(right) <= 0.005
            and abs(sum(left) / len(left) - sum(right) / len(right)) <= 0.010):
        return "groups-" + prefix + "_L-" + prefix + "_R-10mm", (sum(left) + sum(right)) / (len(left) + len(right)), groups, wheels
    raise Refused("SUPPORT_SOURCE_UNRESOLVED", "no equal W_L/W_R group or W_L0/W_R0 wheel pair")


# ---- CONTENT-0 3.2: per-module source tables and the pure build assembly ---------------------------------------------
#
# Every profile field comes from exactly one module table (hull, chassis, engine, fuel tank, radio, turret, the
# turret x gun mount) or is computed from them (identity, mass, physics, devices, bundle). `vehicle_row` of any
# mountable build is `assemble` of the tables of its modules; the stock table stays byte-identical.

class VehicleSource:
    """Parsed client sources of one catalogue vehicle (read-only, bounded by `Sources`)."""

    def __init__(self, src, catalog, vehicle_id):
        self.src, self.catalog, self.vehicle_id = src, catalog, vehicle_id
        self.v = v = catalog.vehicles[vehicle_id]
        self.nation = v["nation"]
        base = PREFIX + self.nation + "/"
        self.vf = src.xml(v["source"])
        self.comp = {k: src.xml(base + "components/" + k + ".xml") for k in COMPONENT_FILES}
        self.nid, self.cid = NATIONS.index(self.nation), v["nation_id"]
        require(self.nid == self.cid, vehicle_id + ": research catalogue nation differs from the client")
        self._node = None

    def node(self):
        if self._node is None:
            self._node = decode(self.src.file(self.v["source"]), max_bytes=MAX_SOURCE, max_depth=32, max_nodes=60000)
        return self._node

    def fact(self, read, what="source fact"):
        try:
            return read()
        except (*SOURCE_ERRORS, KeyError, TypeError) as error:
            raise ProfileError(self.vehicle_id + ": " + what + ": " + str(error)) from error


def _cap(tree, prefix):
    return dict(max_health=_int(tree[prefix + "/maxHealth[1]"], "device max", 100000),
                max_regen_health=_regen(tree[prefix + "/maxRegenHealth[1]"]))


def _part(vs, defaults, path, label, index):
    """One collision part (hull 0, turret 1, gun 2): the component and its member pins, or a refusal."""
    try:
        model = vs.vf.get(label + "/hitTester[1]/collisionModel[1]")
        refuse_if(model is None, "COLLISION_SOURCE_UNRESOLVED", label + " hitTester")
        try:
            effective = _effective(active_armor(vs.node(), path), defaults, KINDS)
        except (*SOURCE_ERRORS, materials.BundleError, KeyError) as error:
            raise Refused("COLLISION_SOURCE_UNSUPPORTED", label + " armour: " + str(error)) from error
        built, pins = component(vs.src, model, index, effective)
        return dict(component=built, members=pins, refusal=None)
    except Refused as refusal:
        return dict(component=None, members=None, refusal=[refusal.code, refusal.detail])


def hull_table(vs, defaults):
    vf = vs.vf
    facts = vs.fact(lambda: dict(
        speed_limits_kmh=[_num(vf["/speedLimits[1]/" + n + "[1]"], "speed", 200) for n in ("forward", "backward")],
        turret_position=vector(vf["/hull[1]/turretPositions[1]/turret[1]"], 3, "turret position"),
        ammo_bay=_cap(vf, "/hull[1]/ammoBayHealth[1]")))
    return dict(facts, part=_part(vs, defaults, ("hull",), "/hull[1]", 0))


def chassis_table(vs, name):
    vf, chassis = vs.vf, "/chassis[1]/" + name + "[1]"
    facts = vs.fact(lambda: dict(
        dispersion_vehicle_movement=_num(vf[chassis + "/shotDispersionFactors[1]/vehicleMovement[1]"], "movement dispersion", 10),
        dispersion_vehicle_rotation=_num(vf[chassis + "/shotDispersionFactors[1]/vehicleRotation[1]"], "rotation dispersion", 10),
        chassis_rotation_deg_s=_num(vf[chassis + "/rotationSpeed[1]"], "chassis yaw"),
        brake_force_source=_num(vf[chassis + "/brakeForce[1]"], "brake force", 10_000_000),
        carrying_point=vector(vf[chassis + "/topRightCarryingPoint[1]"], 2, "carrying point"),
        terrain_resistance=vector(vf[chassis + "/terrainResistance[1]"], 3, "terrain resistance"),
        rotation_is_around_center=vf[chassis + "/rotationIsAroundCenter[1]"],
        hull_position=vector(vf[chassis + "/hullPosition[1]"], 3, "hull position"),
        track=_cap(vf, chassis)))
    try:
        rule, radius, groups, wheels = _supports(vf, chassis)
        supports = dict(rule=rule, radius=radius, groups=groups, wheels=wheels, refusal=None)
    except Refused as refusal:
        supports = dict(rule=None, radius=None, groups=None, wheels=None, refusal=[refusal.code, refusal.detail])
    return dict(facts, supports=supports)


def engine_table(vs, name):
    engines, engine = vs.comp["engines"], "/shared[1]/" + name + "[1]"
    return vs.fact(lambda: dict(engine_power_hp=_num(engines[engine + "/power[1]"], "power", 10000),
                                fire_starting_chance=_num(engines[engine + "/fireStartingChance[1]"], "fire chance", 1),
                                device=_cap(engines, engine)))


def device_table(vs, component_file, name):
    return dict(device=vs.fact(lambda: _cap(vs.comp[component_file], "/shared[1]/" + name + "[1]")))


def turret_table(vs, defaults, name):
    vf, turret = vs.vf, "/turrets0[1]/" + name + "[1]"
    facts = vs.fact(lambda: dict(
        turret_rotation_deg_s=_num(vf[turret + "/rotationSpeed[1]"], "turret yaw"),
        view_range_m=_num(vf[turret + "/circularVisionRadius[1]"], "vision radius", 2000),
        gun_position=vector(vf[turret + "/gunPosition[1]"], 3, "gun position"),
        rotator=_cap(vf, turret + "/turretRotatorHealth[1]"),
        surveying=_cap(vf, turret + "/surveyingDeviceHealth[1]")))
    return dict(facts, part=_part(vs, defaults, ("turrets0", name), turret, 1))


def mount_table(vs, defaults, factor, effects, turret_name, gun_name):
    """The turret x gun mount: every `gun` field but the chassis/turret ones, shots, refusal, gun part, gun device."""
    vf, gf, v = vs.vf, vs.comp["guns"], vs.v
    turret = "/turrets0[1]/" + turret_name + "[1]"
    gun = turret + "/guns[1]/" + gun_name + "[1]"
    shared_gun = "/shared[1]/" + gun_name + "[1]"
    mounted = lambda field: vf.get(gun + "/" + field + "[1]", gf.get(shared_gun + "/" + field + "[1]"))
    mounted_sub = lambda path: vf.get(gun + "/" + path + "[1]", gf.get(shared_gun + "/" + path + "[1]"))

    def read():
        clip, burst = mounted("clip"), mounted("burst")

        def section(name):
            # Client `_readGunLocals`/`_readGun`: a vehicle section replaces the shared one as a whole.
            if gun + "/" + name + "[1]" in vf:
                tree, base = vf, gun + "/" + name + "[1]/"
            elif shared_gun + "/" + name + "[1]" in gf:
                tree, base = gf, shared_gun + "/" + name + "[1]/"
            else:
                return 1, None
            count = tree.get(base + "count[1]")
            return (1 if count is None else _int(count, name + " count", 1000)), _num(tree.get(base + "rate[1]"), name + " rate", 10000)
        clip_count, clip_rate = section("clip")
        burst_count, burst_rate = section("burst")
        yaw = mounted("turretYawLimits")
        extra = {k[len(gun + "/extraPitchLimits[1]/"):-3]: vf[k] for k in vf
                 if k.startswith(gun + "/extraPitchLimits[1]/") and k.count("/") == 6}
        if not extra:
            extra = {k[len(shared_gun + "/extraPitchLimits[1]/"):-3]: gf[k] for k in gf
                     if k.startswith(shared_gun + "/extraPitchLimits[1]/") and k.count("/") == 4}
        require(set(extra) <= {"front", "back", "transition"}, "extra pitch fields")
        envelope = dict(basic=vector(mounted("pitchLimits"), 2, "pitch limits"),
            front=None if "front" not in extra else vector(extra["front"], 3, "front pitch"),
            back=None if "back" not in extra else vector(extra["back"], 3, "back pitch"),
            transition_degrees=None if "transition" not in extra else _num(extra["transition"], "pitch transition", 180))
        return dict(resource=gun_name, max_ammo=_int(mounted("maxAmmo"), "maxAmmo", 2000),
            reload_seconds=_num(mounted("reloadTime"), "reload", 600), aiming_seconds=_num(mounted("aimingTime"), "aiming", 60),
            shot_dispersion_radius=_num(mounted("shotDispersionRadius"), "dispersion", 10),
            clip_count=clip_count, clip_rate_per_minute=clip_rate,
            clip_interval_seconds=60.0 / clip_rate if clip_count > 1 else 0.0,
            clip_source="MOUNTED_OR_SHARED" if clip is not None else "ORIGINAL_LOADER_DEFAULT",
            burst=burst is not None, burst_count=burst_count, burst_rate_per_minute=burst_rate,
            burst_interval_seconds=60.0 / burst_rate if burst_count > 1 else 0.0,
            pitch_limits=vector(mounted("pitchLimits"), 2, "pitch limits"),
            extra_pitch_limits=extra or None, pitch_envelope=envelope,
            dispersion_turret_rotation=_num(mounted_sub("shotDispersionFactors[1]/turretRotation"), "turret dispersion", 10),
            turret_yaw_limits=None if yaw is None else vector(yaw, 2, "yaw limits"),
            gun_rotation_deg_s=_num(gf[shared_gun + "/rotationSpeed[1]"], "gun yaw"),
            mount_source_path=v["source"] + ":" + gun)
    facts = vs.fact(read)
    shot_rows, refusal = None, None
    try:
        # SPG-02 / CONTENT-0 2.6 (main since the 12.11 transfer): bursts and long clips; a burst needs a clip
        # (the client rejects burst > clip > 1; burst on a single-shot gun is not admitted by the runtime).
        clip_count, burst_count = facts["clip_count"], facts["burst_count"]
        refuse_if(not 1 <= clip_count <= MAX_CLIP_TEST_LAB or not 1 <= burst_count <= MAX_BURST
                  or burst_count > 1 and (clip_count == 1 or burst_count > clip_count), "AUTOMATIC_GUN_UNSUPPORTED",
                  "clip %d burst %d" % (clip_count, burst_count))
        refuse_if(not aim_envelope_supported(facts["pitch_envelope"], facts["turret_yaw_limits"]), "AIM_ENVELOPE_UNSUPPORTED",
                  "pitch envelope " + json.dumps(facts["pitch_envelope"], sort_keys=True))
        shot_rows = vs.fact(lambda: shots(vs.src, vs.nation, gun_name, gun, vf, gf, vs.comp["shells"], factor, effects),
                            "shell fact")
        # One to three source shots; the runtime keeps three cells and marks the missing ones absent.
        refuse_if(not (1 <= len(shot_rows) <= 3), "SHELL_SOURCE_UNSUPPORTED", "%d source shots, runtime needs 3" % len(shot_rows))
    except Refused as error:
        refusal = [error.code, error.detail]
    device = vs.fact(lambda: _cap(gf, shared_gun))
    part = _part(vs, defaults, ("turrets0", turret_name, "guns", gun_name), gun, 2)
    return dict(gun=facts, shots=shot_rows, refusal=refusal, device=device, part=part)


def module_tables(src, catalog, vehicle_id, defaults, factor, effects, builds=None):
    """Tables of every module used by `builds` (default: every mountable build of the vehicle)."""
    vs = VehicleSource(src, catalog, vehicle_id)
    builds = configurations(vs.v) if builds is None else builds
    used = {k: sorted({b[k] for b in builds}) for k in MODULE_KINDS}
    name = lambda module: module.split(":")[-1]
    mounts = sorted({(b["turret"], b["gun"]) for b in builds})
    return dict(vehicle_id=vehicle_id, hull=hull_table(vs, defaults),
                chassis={m: chassis_table(vs, name(m)) for m in used["chassis"]},
                engine={m: engine_table(vs, name(m)) for m in used["engine"]},
                fuelTank={m: device_table(vs, "fueltanks", name(m)) for m in used["fuelTank"]},
                radio={m: device_table(vs, "radios", name(m)) for m in used["radio"]},
                turret={m: turret_table(vs, defaults, name(m)) for m in used["turret"]},
                mount={t + "/" + g: mount_table(vs, defaults, factor, effects, name(t), name(g)) for t, g in mounts})


def assemble(catalog, tables, modules):
    """The battle profile row and source bundle of one build: a pure function of the module tables.

    Refusal order is the module order of the original stock generator: the turret x gun mount (automatic gun, aim
    envelope, shells), the chassis supports, the hull/turret/gun collision parts, then the physics envelope.
    """
    vehicle_id = tables["vehicle_id"]
    v = catalog.vehicles[vehicle_id]
    d = {k: modules[k] for k in MODULE_KINDS}
    nation, resource = v["nation"], v["resource_name"]
    kind = next(t for t in v["tags"] if t in CLASSES)
    nid, cid = NATIONS.index(nation), v["nation_id"]
    fix = lambda compact: (compact >> 8 << 8) | (nid << 4) | (compact & 15)
    require(all(catalog.modules[d[k]]["native_compact_id"] >> 4 & 15 == cid for k in MODULE_KINDS)
            and v["native_compact_id"] >> 4 & 15 == cid, vehicle_id + ": catalogue nation nibble")
    raw_cd = descriptor(catalog, dict(vehicle_id=vehicle_id, modules=d))
    require(raw_cd[0] == (cid << 4) | 1, vehicle_id + ": descriptor header")
    cd = (bytes([(nid << 4) | 1]) + raw_cd[1:]).hex()
    mass_kg = (v["hull_mass_grams"] + sum(v["module_mass_grams"][d[k]] for k in MODULE_KINDS)) / 1000
    hull, chassis, engine = tables["hull"], tables["chassis"][d["chassis"]], tables["engine"][d["engine"]]
    turret, mount = tables["turret"][d["turret"]], tables["mount"][d["turret"] + "/" + d["gun"]]
    row = dict(vehicle_id=vehicle_id, nation=nation, native_nation_id=nid, resource=resource, tier=v["tier"],
               vehicle_class=kind, existing_kind=EXISTING.get(vehicle_id),
               research_catalog_nation_id=cid, catalog_nation_correction_required=nid != cid,
               identity=dict(type_compact_id=fix(v["native_compact_id"]), descriptor_hex=cd, modules=d,
                             module_compact_ids={k: fix(catalog.modules[d[k]]["native_compact_id"]) for k in MODULE_KINDS},
                             crew_roles=v["crew_roles"], max_hp=v["hull_max_hp"] + v["turret_max_hp"][d["turret"]],
                             mass_kg=mass_kg, source=v["source"]))
    row["gun"] = dict(mount["gun"], dispersion_vehicle_movement=chassis["dispersion_vehicle_movement"],
                      dispersion_vehicle_rotation=chassis["dispersion_vehicle_rotation"],
                      turret_rotation_deg_s=turret["turret_rotation_deg_s"])
    row["view_range_m"] = turret["view_range_m"]
    movement = dict(engine_power_hp=engine["engine_power_hp"], speed_limits_kmh=hull["speed_limits_kmh"],
                    **{k: chassis[k] for k in ("chassis_rotation_deg_s", "brake_force_source", "carrying_point",
                                               "terrain_resistance", "rotation_is_around_center")})
    row["movement"] = movement
    pivots = dict(hull_position=chassis["hull_position"], turret_position=hull["turret_position"],
                  gun_position=turret["gun_position"])
    row["pivots"] = pivots
    raw = None
    try:
        if mount["refusal"] is not None:
            raise Refused(*mount["refusal"])
        row["shots"] = mount["shots"]
        s = chassis["supports"]
        if s["refusal"] is not None:
            raise Refused(*s["refusal"])
        parts = (hull["part"], turret["part"], mount["part"])
        for part in parts:
            if part["refusal"] is not None:
                raise Refused(*part["refusal"])
        bundle_components = [p["component"] for p in parts]
        members = {}
        for p in parts:
            members.update(p["members"])
        radius, carrying, speed = s["radius"], movement["carrying_point"], movement["speed_limits_kmh"]
        hull_bounds = bundle_components[0]["mesh_bounds"]
        lo, hi, hp = hull_bounds["min"], hull_bounds["max"], pivots["hull_position"]
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
        refuse_if(not all(.1 <= x <= 6 for x in physics["body_half_extents"]) or
                  not all(-5 <= x <= 5 for x in physics["body_center_offset"]) or
                  not all(-5 <= x <= 5 for p in physics["wheel_points"] for x in p), "PHYSICS_ENVELOPE_EXCEEDED",
                  "body/support bounds half=%r center=%r supports=%r" % (
                      [round(x, 3) for x in physics["body_half_extents"]],
                      [round(x, 3) for x in physics["body_center_offset"]],
                      [round(x, 3) for x in physics["wheel_points"][0] + physics["wheel_points"][-1]]))
        bundle = dict(schema=BUNDLE_SCHEMA, vehicle_id=vehicle_id, classification="VERIFIED_STATIC_ORIGINAL_717",
            identity=row["identity"], members=dict(sorted(members.items())),
            wheel_source=dict(groups=s["groups"], individual_wheels=s["wheels"]),
            geometry=dict(**pivots, components=bundle_components), battle_admission=False)
        raw = canonical(bundle) + b"\n"
        require(len(raw) <= MAX_BUNDLE, vehicle_id + ": bundle size bound")
        row["physics"] = physics
        row["handling"] = handling
        row["support_rule"] = s["rule"]
        row["hull_aabb"] = hull_bounds
        row["geometry"] = dict(bundle=bundle_name(row), bytes=len(raw), sha256=sha(raw),
                               components=[dict(name=c["name"], vertex_format=c["vertex_format"],
                                                vertices=len(c["vertices"]), triangles=len(c["triangles"]),
                                                excluded_degenerate=len(c["excluded_degenerate_triangle_ids"]),
                                                armor_ids=[m["kind"] for m in c["materials"] if m["kind"] <= 16],
                                                material_kinds=[m["kind"] for m in c["materials"]])
                                           for c in bundle_components])
        row.update(runtime_facts(v, tables, d, row))
        decision = dict(status="generated", refusal=None, detail=None)
    except Refused as refusal:
        raw = None
        decision = dict(status="refused", refusal=refusal.code, detail=refusal.detail)
    row.update(decision)
    row["battle_admission"] = False
    row["readiness_code"] = "BATTLE_PROFILE_UNSUPPORTED"
    return row, raw


def vehicle_row(src, catalog, vehicle_id, defaults, factor, effects, modules=None):
    """The profile row and bundle of one build (stock when `modules` is None)."""
    d = catalog.vehicles[vehicle_id]["defaults"] if modules is None else modules
    build = {k: d[k] for k in MODULE_KINDS}
    return assemble(catalog, module_tables(src, catalog, vehicle_id, defaults, factor, effects, [build]), build)


# Rust/Python device order and extras of common/vehicle.xml (index + 1), as P06T.
DEVICES = ("engine", "ammoBay", "fuelTank", "radio", "leftTrack", "rightTrack", "gun", "turretRotator", "surveyingDevice")
CREW_EXTRAS = {"commander": (35,), "driver": (36,), "radioman": (37, 38), "gunner": (39, 40), "loader": (41, 42)}
ROLE_BITS = {"commander": 1, "gunner": 2, "driver": 4, "loader": 8, "radioman": 16}
FAMILY_SUFFIX = {"ARMOR_PIERCING": "ap", "ARMOR_PIERCING_CR": "apcr", "HOLLOW_CHARGE": "heat", "HIGH_EXPLOSIVE": "he"}
LEGACY_SUFFIXES = {"ms1": ("ap", "heat", "he"), "is7": ("ap", "apcr", "he"), "t26": ("ap", "apcr", "he"),
                   "t34": ("ap", "heat", "he"), "t3485": ("ap", "apcr", "he")}


def configurations(v):
    """CONTENT-0 3.2: every mountable build of a catalogue vehicle, stock first, then sorted.

    The 0.9.1 client (`VehicleDescr.__computeWeight`, `mayInstallComponent`) and the P09E store (3.1): chassis x engine
    x radio x (turret, gun of that turret); the fuel tank stays stock; total mass must not exceed the chassis maxLoad.
    """
    c, d = v["compatible"], v["defaults"]
    grams = v["module_mass_grams"]
    builds = []
    for chassis in sorted(c["chassis"]):
        for engine in sorted(c["engine"]):
            for radio in sorted(c["radio"]):
                for turret in sorted(c["turret"]):
                    for gun in sorted(v["turret_guns"][turret]):
                        m = dict(chassis=chassis, engine=engine, fuelTank=d["fuelTank"], radio=radio, turret=turret, gun=gun)
                        if v["hull_mass_grams"] + sum(grams[m[k]] for k in MODULE_KINDS) <= v["module_max_load_grams"][chassis]:
                            builds.append(m)
    stock = {k: d[k] for k in MODULE_KINDS}
    require(stock in builds, v["vehicle_id"] + ": stock build is not mountable")
    builds.remove(stock)
    return [stock] + builds


def kind_label(row):
    """The five legacy kinds keep their labels; any other row is `<nation>-<resource>`."""
    legacy = row["existing_kind"]
    return legacy if legacy in LEGACY_SUFFIXES else row["nation"] + "-" + row["resource"]


def runtime_facts(v, tables, modules, row):
    """Device caps, crew seats, stack suffixes and labels the battle runtime binds (P06T rules)."""
    chassis, turret = tables["chassis"][modules["chassis"]], tables["turret"][modules["turret"]]
    engine = tables["engine"][modules["engine"]]
    caps = (engine["device"], tables["hull"]["ammo_bay"], tables["fuelTank"][modules["fuelTank"]]["device"],
            tables["radio"][modules["radio"]]["device"], chassis["track"], chassis["track"],
            tables["mount"][modules["turret"] + "/" + modules["gun"]]["device"], turret["rotator"], turret["surveying"])
    devices = [dict(device=d, extra_index=26 + i, **cap) for i, (d, cap) in enumerate(zip(DEVICES, caps))]
    chance = engine["fire_starting_chance"]
    seats, used = [], {}
    for index, roles in enumerate(v["crew_roles"]):
        require(roles and all(r in ROLE_BITS for r in roles) and len(set(roles)) == len(roles), "crew roles")
        n = used.get(roles[0], 0)
        require(n < len(CREW_EXTRAS[roles[0]]), "crew extra slots")
        used[roles[0]] = n + 1
        seats.append(dict(seat=index, extra_index=CREW_EXTRAS[roles[0]][n], roles=list(roles),
                          role_bits=sum(ROLE_BITS[r] for r in roles)))
    kind = kind_label(row)
    if kind in LEGACY_SUFFIXES and all(modules[role] == v["defaults"][role] for role in ("turret", "gun")):
        suffixes = list(LEGACY_SUFFIXES[kind])
    else:
        suffixes = []
        for shot in row["shots"]:
            base = FAMILY_SUFFIX[shot["family"]]
            suffixes.append(base if base not in suffixes else base + str(1 + sum(x.startswith(base) for x in suffixes)))
    weights = dict(hull=v["hull_mass_grams"] / 1000, **{k: v["module_mass_grams"][modules[m]] / 1000 for k, m in
                   (("chassis", "chassis"), ("turret", "turret"), ("gun", "gun"), ("engines", "engine"),
                    ("fueltanks", "fuelTank"), ("radios", "radio"))})
    total = 0.0
    for key in sorted(weights):
        total += weights[key]
    # The physics worker recomputes the assembly mass from these weights in
    # sorted-key order; any rounding difference is a source error, not clamped.
    require(total == row["identity"]["mass_kg"], "weights sum differs from assembly mass")
    return dict(kind=kind, shell_suffixes=suffixes, devices=devices, engine_fire_starting_chance=chance,
                crew_seats=seats, weights_kg=weights)


# ---- CONTENT-0 3.3: the build table the gateway embeds --------------------------------------------------------------
#
# The gateway copies, never computes: every number of a build's runtime profile is in this table, written here from
# the same module tables `assemble` uses. Per vehicle: the hull part and crew; per module the facts the runtime binds;
# per chassis x engine the physics without the mass; per build its label, modules, descriptor, mass, HP and decision.
# Collision parts (hull, turret, turret x gun) are separate pinned files.

BUILDS_SCHEMA = "wot091-battle-builds.v1"
PART_SCHEMA = "battle-any-part.v1"
BUILDS = _DIR / "battle_builds.v1.json"
MAX_BUILDS_TABLE = 32 * 1024 * 1024
MAX_PART = 512 * 1024
MAX_BUILD_LABEL = 96


def build_label(kind, row, stock):
    """Stock keeps the kind label; another build is `<kind>--<8 hex of its descriptor>`."""
    return kind if stock else kind + "--" + sha(row["identity"]["descriptor_hex"].encode("ascii"))[:8]


def part_document(vehicle_id, slot, part):
    raw = canonical(dict(schema=PART_SCHEMA, vehicle_id=vehicle_id, slot=slot, component=part["component"],
                         members=dict(sorted(part["members"].items())))) + b"\n"
    require(len(raw) <= MAX_PART, vehicle_id + ": part size bound")
    return raw


def _summary(component):
    return dict(name=component["name"], vertex_format=component["vertex_format"], vertices=len(component["vertices"]),
                triangles=len(component["triangles"]), excluded_degenerate=len(component["excluded_degenerate_triangle_ids"]),
                armor_ids=[m["kind"] for m in component["materials"] if m["kind"] <= 16],
                material_kinds=[m["kind"] for m in component["materials"]])


def _part_ref(vehicle_id, slot, part, parts):
    raw = part_document(vehicle_id, slot, part)
    key = sha(raw)
    parts[key] = raw
    return dict(sha256=key, bytes=len(raw), **_summary(part["component"]))


DRIVE_FIELDS = ("body_half_extents", "body_center_offset", "wheel_points", "max_forward_mps", "max_reverse_mps",
                "engine_max_torque_nm", "wheel_radius", "suspension_min", "suspension_max", "track_max_brake_torque",
                "longitudinal_friction", "lateral_friction", "stationary_steering_ratio")


def _chassis_armor_ref(chassis_armor, module, parts):
    """SHELL-02 track armour part of one chassis module (`chassis-armor-part.v1`) or its explicit refusal."""
    raw, refusal = chassis_armor(module.split(":")[-1])
    if raw is None:
        return dict(sha256=None, bytes=None, refusal=refusal)
    key = sha(raw)
    parts[key] = raw
    return dict(sha256=key, bytes=len(raw), refusal=None)


def vehicle_builds(catalog, tables, builds, chassis_armor=None):
    """(vehicle record, {part sha: bytes}, [(label, full row)]) of every build of one vehicle."""
    vehicle_id = tables["vehicle_id"]
    parts, rows, out = {}, [], dict(builds=[], chassis={}, engines={}, radios={}, fuel_tanks={}, turrets={}, mounts={},
                                    drives={})
    stock_modules = builds[0]
    for m in builds:
        row, raw = assemble(catalog, tables, m)
        stock = m == stock_modules
        kind = kind_label(row)
        entry = dict(modules=m, status=row["status"], refusal=row["refusal"], detail=row["detail"],
                     descriptor_hex=row["identity"]["descriptor_hex"], module_compact_ids=row["identity"]["module_compact_ids"],
                     max_hp=row["identity"]["max_hp"], mass_kg=row["identity"]["mass_kg"], stock=stock)
        if entry["status"] == "generated":
            label = build_label(kind, row, stock)
            require(len(label) <= MAX_BUILD_LABEL, vehicle_id + ": build label bound")
            entry.update(label=label, weights_kg=row["weights_kg"])
            rows.append((label, row))
            t, g, c, e = m["turret"], m["gun"], m["chassis"], m["engine"]
            mount = tables["mount"][t + "/" + g]
            turret = tables["turret"][t]
            out["mounts"].setdefault(t + "/" + g, dict(gun=mount["gun"], shots=row["shots"], shell_suffixes=row["shell_suffixes"],
                device=mount["device"], part=_part_ref(vehicle_id, 2, mount["part"], parts)))
            out["turrets"].setdefault(t, dict(turret_rotation_deg_s=turret["turret_rotation_deg_s"], view_range_m=turret["view_range_m"],
                gun_position=turret["gun_position"], rotator=turret["rotator"], surveying=turret["surveying"],
                part=_part_ref(vehicle_id, 1, turret["part"], parts)))
            ch = tables["chassis"][c]
            out["chassis"].setdefault(c, dict(dispersion_vehicle_movement=ch["dispersion_vehicle_movement"],
                dispersion_vehicle_rotation=ch["dispersion_vehicle_rotation"], hull_position=ch["hull_position"],
                track=ch["track"], handling=row["handling"], support_rule=row["support_rule"],
                movement={k: row["movement"][k] for k in ("chassis_rotation_deg_s", "brake_force_source", "carrying_point",
                                                         "terrain_resistance", "rotation_is_around_center")},
                armor=_chassis_armor_ref(chassis_armor, c, parts) if chassis_armor else None))
            out["engines"].setdefault(e, dict(engine_power_hp=row["movement"]["engine_power_hp"],
                fire_starting_chance=row["engine_fire_starting_chance"], device=tables["engine"][e]["device"]))
            out["radios"].setdefault(m["radio"], tables["radio"][m["radio"]])
            out["fuel_tanks"].setdefault(m["fuelTank"], tables["fuelTank"][m["fuelTank"]])
            drive = {k: row["physics"][k] for k in DRIVE_FIELDS}
            require(out["drives"].setdefault(c + "/" + e, drive) == drive, vehicle_id + ": drive physics depends on more than chassis x engine")
            if "hull" not in out:
                out["hull"] = dict(kind=kind, part=_part_ref(vehicle_id, 0, tables["hull"]["part"], parts), hull_aabb=row["hull_aabb"],
                                   speed_limits_kmh=row["movement"]["speed_limits_kmh"], turret_position=row["pivots"]["turret_position"],
                                   ammo_bay=tables["hull"]["ammo_bay"], crew_seats=row["crew_seats"])
            entry["geometry_sha256"] = sha(canonical([out["hull"]["part"]["sha256"], out["turrets"][t]["part"]["sha256"],
                                                      out["mounts"][t + "/" + g]["part"]["sha256"]]))
        out["builds"].append(entry)
    return out, parts, rows


def project(row, qualified_kind=None):
    """The runtime facts of one full profile row (what the gateway Entry binds): the check of the build table."""
    g = row["gun"]
    return dict(kind=qualified_kind or row["kind"], vehicle_id=row["vehicle_id"], nation=row["native_nation_id"],
                descriptor=row["identity"]["descriptor_hex"], type_compact_id=row["identity"]["type_compact_id"],
                gun_compact_id=row["identity"]["module_compact_ids"]["gun"], max_hp=row["identity"]["max_hp"],
                mass_kg=row["identity"]["mass_kg"], view_range_m=row["view_range_m"], gun=g, shots=row["shots"],
                pivots=row["pivots"], shell_suffixes=row["shell_suffixes"], devices=row["devices"], crew_seats=row["crew_seats"],
                engine_fire_starting_chance=row["engine_fire_starting_chance"], physics=row["physics"], handling=row["handling"],
                components=row["geometry"]["components"], weights_kg=row["weights_kg"], movement=row["movement"],
                hull_aabb=row["hull_aabb"], support_rule=row["support_rule"])


def project_build(vehicle, entry):
    """The same runtime facts read from the build table only (copy, no arithmetic): the gateway's rule."""
    m = entry["modules"]
    t, g, c, e = m["turret"], m["gun"], m["chassis"], m["engine"]
    hull, mount, turret, chassis, engine = (vehicle["hull"], vehicle["mounts"][t + "/" + g], vehicle["turrets"][t],
                                            vehicle["chassis"][c], vehicle["engines"][e])
    gun = dict(mount["gun"], dispersion_vehicle_movement=chassis["dispersion_vehicle_movement"],
               dispersion_vehicle_rotation=chassis["dispersion_vehicle_rotation"], turret_rotation_deg_s=turret["turret_rotation_deg_s"])
    caps = (engine["device"], hull["ammo_bay"], vehicle["fuel_tanks"][m["fuelTank"]]["device"], vehicle["radios"][m["radio"]]["device"],
            chassis["track"], chassis["track"], mount["device"], turret["rotator"], turret["surveying"])
    physics = dict(vehicle["drives"][c + "/" + e], mass_kg=entry["mass_kg"])
    summary = lambda ref: {k: v for k, v in ref.items() if k not in ("sha256", "bytes")}
    movement = dict(chassis["movement"], engine_power_hp=engine["engine_power_hp"], speed_limits_kmh=hull["speed_limits_kmh"])
    return dict(kind=hull["kind"], vehicle_id=vehicle["vehicle_id"], nation=vehicle["native_nation_id"],
                descriptor=entry["descriptor_hex"], type_compact_id=vehicle["type_compact_id"],
                gun_compact_id=entry["module_compact_ids"]["gun"], max_hp=entry["max_hp"], mass_kg=entry["mass_kg"],
                view_range_m=turret["view_range_m"], gun=gun, shots=mount["shots"],
                pivots=dict(hull_position=chassis["hull_position"], turret_position=hull["turret_position"], gun_position=turret["gun_position"]),
                shell_suffixes=mount["shell_suffixes"],
                devices=[dict(device=d, extra_index=26 + i, **cap) for i, (d, cap) in enumerate(zip(DEVICES, caps))],
                crew_seats=hull["crew_seats"], engine_fire_starting_chance=engine["fire_starting_chance"], physics=physics,
                handling=chassis["handling"], components=[summary(hull["part"]), summary(turret["part"]), summary(mount["part"])],
                weights_kg=entry["weights_kg"], movement=movement, hull_aabb=hull["hull_aabb"], support_rule=chassis["support_rule"])


def build_table(original, profile_raw=None):
    """(build table bytes, {part sha: bytes}, [(label, full row)] of every generated build)."""
    src, catalog, defaults, factor, effects = context(original)
    tests = {v["vehicle_id"] for v in test_vehicles.load()[0]["vehicles"]} if TEST_LAB else set()
    import chassis_armor_export  # imports this module; loaded only when the build table is made
    common, kinds_by_label = chassis_armor_export.context(src)
    vehicles, parts, rows = {}, {}, []
    for vehicle_id in sorted(catalog.vehicles):
        if vehicle_id in tests:
            continue
        v = catalog.vehicles[vehicle_id]
        builds = configurations(v)
        tables = module_tables(src, catalog, vehicle_id, defaults, factor, effects, builds)
        armor = lambda chassis, vid=vehicle_id: chassis_armor_export.chassis_part(src, catalog, vid, chassis, common, kinds_by_label)
        record, vehicle_parts, vehicle_rows = vehicle_builds(catalog, tables, builds, armor)
        if not vehicle_rows:
            continue
        stock_row = vehicle_rows[0][1]  # vehicle-level facts are the same in every build
        record.update(vehicle_id=vehicle_id, native_nation_id=stock_row["native_nation_id"],
                      type_compact_id=stock_row["identity"]["type_compact_id"], tier=v["tier"], vehicle_class=stock_row["vehicle_class"])
        vehicles[vehicle_id] = record
        parts.update(vehicle_parts)
        rows.extend(vehicle_rows)
    labels = [label for label, _ in rows]
    require(len(labels) == len(set(labels)), "duplicate build label")
    table = dict(schema=BUILDS_SCHEMA, target="v.0.9.1 #717 RU", research_catalog_sha256=CATALOG_SHA256, policy=POLICY,
                 profile_table_sha256=sha(TABLE.read_bytes() if profile_raw is None else profile_raw), builds=len(rows), vehicles=vehicles)
    raw = canonical(table) + b"\n"
    require(len(raw) <= MAX_BUILDS_TABLE, "build table size bound")
    return raw, parts, rows


def physics_definitions(table, builds=()):
    """Embedded C# definitions of every generated non-legacy kind (exact canonical rows), then (CONTENT-0 3.3) every
    generated non-stock build `(label, row)` in label order; a build's definition kind is its label."""
    rows = []
    stock = [(r.get("kind"), r) for r in table["vehicles"]]
    for kind, r in stock + sorted(builds, key=lambda b: b[0]):
        if r["status"] != "generated" or kind in LEGACY_SUFFIXES:
            continue
        m = r["movement"]
        rows.append(dict(kind=kind, vehicle=r["vehicle_id"], physics=r["physics"], handling=r["handling"], mapping=MAPPING,
            source=dict(weights_kg=r["weights_kg"], speed_limits_kmh=m["speed_limits_kmh"], engine_power_hp=m["engine_power_hp"],
                        brake_force_source=m["brake_force_source"], yaw_rate_degrees_s=m["chassis_rotation_deg_s"],
                        carrying_point=m["carrying_point"], hull_aabb=r["hull_aabb"],
                        hull_position=r["pivots"]["hull_position"], support_rule=r["support_rule"])))
    return dict(version=1, profile="test_lab", policy=GENERATED_POLICY, profiles=rows)


def definition_sha256(row):
    """C# hashes the embedded row's raw text + LF; the file is canonical JSON."""
    return sha(canonical(row) + b"\n")


def bundle_name(row):
    return row["nation"] + "-" + row["resource"] + ".json"


def derived_test_row(base, base_bundle, spec, catalog):
    """TESTVEH-01: a stand-only test vehicle is its base vehicle's row and bundle with the
    test identity (research overlay ids, own chassis/turret modules). Tier, geometry,
    physics, shots and devices stay the base source facts (the tier label 11 is client
    text only); armour is a stand manifest flag."""
    from p09e_research_projection import descriptor
    vehicle = catalog.vehicles[spec["vehicle_id"]]
    defaults = dict(vehicle["defaults"])
    row = copy.deepcopy(base)
    require(base["status"] == "generated" and base_bundle is not None, "test vehicle base must be generated")
    row["vehicle_id"] = spec["vehicle_id"]
    row["resource"] = spec["resource_name"]
    identity = row["identity"]
    identity["modules"] = defaults
    identity["module_compact_ids"] = {role: catalog.modules[m]["native_compact_id"] for role, m in defaults.items()}
    identity["descriptor_hex"] = descriptor(catalog, {"vehicle_id": spec["vehicle_id"], "modules": defaults}).hex()
    if "type_compact_id" in identity:
        identity["type_compact_id"] = vehicle["native_compact_id"]
    row["kind"] = kind_label(row)
    bundle = json.loads(base_bundle)
    bundle["vehicle_id"] = spec["vehicle_id"]
    # The gateway checks the bundle identity against the registry row
    # (geometry.rs from_generated_source): it carries the test identity too.
    bundle["identity"] = dict(bundle["identity"], modules=defaults,
                              **{k: identity[k] for k in ("descriptor_hex", "type_compact_id", "module_compact_ids")
                                 if k in bundle["identity"]})
    raw = canonical(bundle) + b"\n"
    row["geometry"] = dict(row["geometry"], bundle=bundle_name(row), bytes=len(raw), sha256=sha(raw))
    return row, raw


def context(original):
    """Pinned sources, research catalogue, material defaults, projectile factor and shot effects order."""
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
    defaults = materials._common_materials(decode(src.file(materials.COMMON_REL), max_bytes=MAX_MEMBER), mapping, loader, KINDS)
    common = src.xml(materials.COMMON_REL)
    factor = _num(common["/miscParams[1]/projectileSpeedFactor[1]"], "projectile factor", 1)
    require(factor == .8, "projectile speed factor differs")
    # Native shot effectsIndex = order of shot_effects.xml (P06T wire audit rule).
    effects = [k[1:].split("[", 1)[0] for k in src.xml(PREFIX + "common/shot_effects.xml") if k.count("/") == 1 and k != "/"]
    require(len(effects) == len(set(effects)) and 0 < len(effects) <= 255, "shot effects order")
    return src, catalog, defaults, factor, effects


def build(original):
    src, catalog, defaults, factor, effects = context(original)
    rows, bundles = [], {}
    tests = {v["vehicle_id"]: v for v in test_vehicles.load()[0]["vehicles"]} if TEST_LAB else {}
    for vehicle_id in sorted(catalog.vehicles):
        if vehicle_id in tests:
            continue
        row, raw = vehicle_row(src, catalog, vehicle_id, defaults, factor, effects)
        rows.append(row)
        if raw is not None:
            bundles[bundle_name(row)] = raw
    for vehicle_id, spec in sorted(tests.items()):
        base = next(r for r in rows if r["vehicle_id"] == spec["base_vehicle_id"])
        row, raw = derived_test_row(base, bundles.get(bundle_name(base)), spec, catalog)
        rows.append(row)
        bundles[bundle_name(row)] = raw
    rows.sort(key=lambda r: r["vehicle_id"])
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
    builds_raw, parts, build_rows = build_table(original, raw)
    out.mkdir()
    (out / "bundles").mkdir()
    for name, data in sorted(bundles.items()):
        with (out / "bundles" / name).open("xb") as stream:
            stream.write(data)
    # CONTENT-0 3.3: collision parts of every build, by SHA-256 (hull, turret, turret x gun).
    (out / "parts").mkdir()
    for key, data in sorted(parts.items()):
        with (out / "parts" / (key + ".json")).open("xb") as stream:
            stream.write(data)
    with (out / "battle_builds.v1.json").open("xb") as stream:
        stream.write(builds_raw)
    with (out / "battle_profiles.v1.json").open("xb") as stream:
        stream.write(raw)
    if update or committed is None:
        TABLE.write_bytes(raw)
        BUILDS.write_bytes(builds_raw)
        BUILDS_BINDING.write_bytes(builds_binding(builds_raw))
        BINDING.write_bytes(binding(raw))
        if QUALIFICATION.is_file():  # a first test_lab build: `qualify` writes the pins
            RUST_PINS.write_bytes(rust_pins())
        extra = [(label, row) for label, row in build_rows if label != row["kind"]]
        PHYSICS_DEFINITIONS.write_bytes(canonical(physics_definitions(json.loads(raw), extra)) + b"\n")
    table = json.loads(raw)
    counts = {}
    for row in table["vehicles"]:
        key = row["status"] if row["refusal"] is None else row["refusal"]
        counts[key] = counts.get(key, 0) + 1
    receipt = dict(schema="battle-any-export.v1", status="PASS_PINNED_SOURCE_EXPORT", table_sha256=sha(raw), table_bytes=len(raw),
                   vehicles=len(table["vehicles"]), counts=dict(sorted(counts.items())), bundles=len(bundles),
                   bundles_sha256=sha(canonical({k: sha(v) for k, v in sorted(bundles.items())})),
                   builds_table_sha256=sha(builds_raw), builds=json.loads(builds_raw)["builds"], parts=len(parts),
                   committed_table_changed=committed is not None and committed != raw,
                   runtime_registration=False, native="NOT_RUN", client_bytecode_executed=False)
    with (out / "receipt.json").open("xb") as stream:
        stream.write(canonical(receipt) + b"\n")
    return receipt


def builds_binding(raw):
    lines = ('"""GENERATED by tools/battle_any_profiles.py from %s; do not edit."""' % BUILDS.relative_to(ROOT).as_posix(),
             "SCHEMA = %r" % BUILDS_SCHEMA, "BUILDS_SHA256 = %r" % sha(raw), "BUILDS_BYTES = %d" % len(raw))
    return ("\n".join(lines) + "\n").encode("ascii")


def binding(raw):
    lines = ('"""GENERATED by tools/battle_any_profiles.py from %s; do not edit."""' % TABLE.relative_to(ROOT).as_posix(),
             "SCHEMA = %r" % SCHEMA, "TABLE_SHA256 = %r" % sha(raw), "TABLE_BYTES = %d" % len(raw))
    return ("\n".join(lines) + "\n").encode("ascii")


def qualification_record(out_dir, table_raw):
    """Closed record of a worker `--qualify-generated-profiles` run: every embedded
    definition qualified once, file bytes/SHA and native getter bits."""
    # CONTENT-0 3.3: the committed definitions file (stock kinds, then every non-stock build) is the expectation.
    definitions = json.loads(PHYSICS_DEFINITIONS.read_bytes())
    stock = physics_definitions(json.loads(table_raw))["profiles"]
    require(definitions["profiles"][:len(stock)] == stock, "definitions do not start with the stock table")
    expected = {row["kind"]: definition_sha256(row) for row in definitions["profiles"]}
    manifest = json.loads((out_dir / "qualified-manifest.json").read_bytes())
    require(manifest["version"] == 1 and manifest["policy"] == GENERATED_POLICY and manifest["battle_admission"] is False,
            "qualification manifest policy")
    rows = []
    for entry in manifest["profiles"]:
        raw = (out_dir / entry["file"]).read_bytes()
        require(entry["file"] == entry["kind"] + "-qualified-profile.json" and pin(raw) == dict(bytes=entry["bytes"], sha256=entry["sha256"]),
                "qualified profile pin")
        document = json.loads(raw)
        require(document["kind"] == entry["kind"] and document["definition_sha256"] == expected.get(entry["kind"])
                and document["native_binding"] == entry["native_binding"] and document["battle_admission"] is False,
                "qualified profile definition binding")
        n = entry["native_binding"]
        rows.append(dict(kind=entry["kind"], file=entry["file"], bytes=entry["bytes"], sha256=entry["sha256"],
                         definition_sha256=entry["definition_sha256"], inverse_mass_bits=n["inverse_mass_bits"],
                         principal_inverse_bits=n["principal_inverse_bits"], inertia_rotation_bits_xyzw=n["inertia_rotation_bits_xyzw"]))
    require(sorted(r["kind"] for r in rows) == sorted(expected), "qualification covers every generated definition")
    return dict(schema=QUALIFICATION_SCHEMA,
                definitions_sha256=sha(canonical(definitions) + b"\n"), policy=GENERATED_POLICY, runtime=manifest["runtime"],
                classification=manifest["classification"], profiles=sorted(rows, key=lambda r: r["kind"]))


def qualify(worker, out):
    """Run the built physics worker over the embedded definitions; record the result."""
    import subprocess
    local = no_links(ROOT / "local").resolve(strict=True)
    out = owned(local, Path(out).absolute())
    require(not out.exists() and out.parent.is_dir(), "fresh output with existing parent required")
    worker = Path(worker).resolve(strict=True)
    result = subprocess.run([str(worker), "--qualify-generated-profiles", "--local-root", str(local), "--out", str(out)],
                            capture_output=True, timeout=600, check=False)
    require(result.returncode == 0, "worker qualification failed: " + result.stderr.decode("utf-8", "replace")[-400:])
    record = qualification_record(out, TABLE.read_bytes())
    raw = canonical(record) + b"\n"
    QUALIFICATION.write_bytes(raw)
    RUST_PINS.write_bytes(rust_pins())
    return dict(status="PASS_GENERATED_QUALIFIED", profiles=len(record["profiles"]), qualification_sha256=sha(raw),
                worker_sha256=record["runtime"]["qualified_worker_sha256"], out=str(out))


def rust_pins():
    """Gateway pins of the embedded table and qualification record (exact bytes)."""
    lines = ("// GENERATED by tools/battle_any_profiles.py; do not edit. Exact-byte pins of the embedded",
             "// %s and battle_qualification.v1.json." % TABLE.relative_to(ROOT).as_posix(),
             "pub const TABLE_SHA256:&str=\"%s\";" % sha(TABLE.read_bytes()),
             "pub const QUALIFICATION_SHA256:&str=\"%s\";" % sha(QUALIFICATION.read_bytes()),
             "// CONTENT-0 3.3: battle_builds.v1.json (every mountable build).",
             "pub const BUILDS_SHA256:&str=\"%s\";" % sha(BUILDS.read_bytes()))
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
    require(path != TABLE or BUILDS_BINDING.read_bytes() == builds_binding(BUILDS.read_bytes()), "build binding differs from build table")
    if path == TABLE:
        # CONTENT-0 3.3: stock definitions first, then one per non-stock build of the build table, in label order.
        definitions = PHYSICS_DEFINITIONS.read_bytes()
        loaded = json.loads(definitions)
        stock = physics_definitions(table)["profiles"]
        builds = json.loads(BUILDS.read_bytes())
        extra = sorted(e["label"] for v in builds["vehicles"].values() for e in v["builds"] if "label" in e and not e["stock"])
        require(canonical(loaded) + b"\n" == definitions and loaded["profiles"][:len(stock)] == stock
                and [r["kind"] for r in loaded["profiles"][len(stock):]] == extra
                and builds["profile_table_sha256"] == sha(raw), "generated physics definitions differ from table/builds")
        record = json.loads(QUALIFICATION.read_bytes())
        require(record["schema"] == QUALIFICATION_SCHEMA and record["definitions_sha256"] == sha(definitions)
                and [r["kind"] for r in record["profiles"]] == sorted(r["kind"] for r in loaded["profiles"]),
                "qualification record does not cover the current physics definitions; run qualify")
        require(RUST_PINS.read_bytes() == rust_pins(), "gateway pins differ from table/qualification")
    return dict(status="PASS", table_sha256=sha(raw), vehicles=len(seen),
                generated=sum(r["status"] == "generated" for r in table["vehicles"]))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build")
    b.add_argument("--original", type=Path, required=True)
    b.add_argument("--out", type=Path, required=True)
    b.add_argument("--update", action="store_true")
    q = sub.add_parser("qualify")
    q.add_argument("--worker", type=Path, required=True)
    q.add_argument("--out", type=Path, required=True)
    sub.add_parser("check")
    args = parser.parse_args(argv)
    try:
        result = (export(args.original, args.out, args.update) if args.command == "build"
                  else qualify(args.worker, args.out) if args.command == "qualify" else check())
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps(dict(status="FAIL_BATTLE_ANY", reason=str(error))))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
