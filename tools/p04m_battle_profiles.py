"""Bounded read-only #717 stock T-26/T-34/T-34-85 source assembly importer.

Exports facts and component collision meshes, not admitted runtime profiles.
Original bytecode is inspected as inert data by existing pinned material readers.
No physics/controller defaults, inventory/crew grants or runtime registration.
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

TOOLS = Path(__file__).resolve().parent
for directory in (TOOLS.parent, TOOLS):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))
import is7_collision_bundle as geometry
import ms1_contact_bundle as materials
from geometry_spike import collision_mesh
from packed_xml import decode, walk
from p09e_research_catalog import load_catalog
from p09e_research_projection import descriptor
from py27_static import parse_pyc
from vehicle_physics_profile import no_links, owned

ROOT = TOOLS.parent
SCHEMA = "p04m-battle-source.v1"
MAX_SOURCE = 256 * 1024
MAX_PROFILE = 1024 * 1024
CATALOG_SHA256 = "1f6b20d1ba564e00186fed77a3da74c3bd9b135f0db30ffdef740fd5888ced80"
# CAT-NATIONS: the five P04M specs were derived from the research catalogue before
# its nation fix. They are USSR rows (nation 0), identical in both catalogues, so
# their provenance stays frozen: the source revision, the P04M definition/registry
# and the pool/crew policy hashes pinned by the gateway, web and stands do not move.
# Builds and runtime still check the current catalogue (CATALOG_SHA256).
SPEC_CATALOG_SHA256 = "b6baecd204444d1e894253fa6c19c61478993b8ae87c71373633989d3a8ee460"
PREFIX = "res/scripts/item_defs/vehicles/ussr/"
PACKAGE = "res/packages/vehicles_russian.pkg"
PACKAGE_PINS = {
    PACKAGE: {"bytes": 1182066680, "sha256": "c2e16aef6fe7a7e44e476e2cb96e009b9f4eb7edab55fda2861601ba783415aa"},
    materials.MISC_REL: copy.deepcopy(materials.PACKAGE_PINS[materials.MISC_REL]),
}
FILE_PINS = {name: copy.deepcopy(materials.FILE_PINS[name]) for name in
             (materials.COMMON_REL, materials.LOADER_REL, materials.KINDS_LOADER_REL, materials.VEHICLE_REL)}
FILE_PINS.update({PREFIX + name: {"bytes": size, "sha256": digest} for name, size, digest in (
    ("t-26.xml", 11010, "ade0230c2511d64ef38d7e3f7bb850ede2004e0f2f39648031d763a884cfe3f8"),
    ("t-34.xml", 11912, "eb83065dace1ca39e93c225c319b3ab857d790f8ea34abcabeb58d6e7138183b"),
    ("t-34-85.xml", 18759, "3b69621a659e3369eddaefd078e7a6d3dbc52f8271c2c3318839956d3021cb92"),
    ("components/guns.xml", 58493, "889fe1564987566478c474ddfef21cbc7742d23bebd19f6a200c59bfafd7d87b"),
    ("components/shells.xml", 20468, "ed301edbe07a72b04dc6c6d799bc563de55d0d1f26bd35798354a9f6769e7a96"),
    ("components/engines.xml", 16153, "196e52561bd04d2d4e5838442f62704456f4b901627248e04b2c9bd37d32f60d"),
    ("components/fueltanks.xml", 457, "1f182b76fceeabf2ff1d828cc5b2aea37b94585f78488bd2dd7c195f8862b013"),
    ("components/radios.xml", 3986, "099292b8b5f5e250b2cd506419d18620f4f2504950776b54983bc303b2ca201a"),
)})
MODULE_KINDS = ("chassis", "engine", "fuelTank", "radio", "turret", "gun")
SPECS = {
    "t26-stock": dict(resource="T-26", folder="R09_T-26", gun_part="Gun_02", type_cd=4609,
        modules=("T-26", "T-26", "Small", "_71-TK-1", "T-26_cylindrical", "_37mm_B-3"),
        module_cds=(9218, 4869, 51462, 263, 7683, 4100), descriptor="011224001300c90001001e00100000",
        crew=(("commander", "radioman"), ("driver",), ("gunner", "loader")),
        capacity=160, max_hp=150, mass_kg=9302, power_hp=90, forward=36, reverse=15,
        chassis_yaw=50, turret_yaw=44, gun_yaw=43.75, reload=2.3, aiming=2.3, dispersion=.46,
        pitch=(-25, 8), shell="_37mm_UBR-160", shell_cd=1034, caliber=37, damage=36,
        device_damage=50, penetration=(40, 33), speed=670),
    "t34-stock": dict(resource="T-34", folder="R04_T-34", gun_part="Gun_01", type_cd=1,
        modules=("T-34_mod_1941", "V-2", "Average", "_9R", "T-34_mod_1940", "_76mm_L-11"),
        module_cds=(2, 5, 51974, 775, 3, 4), descriptor="010000000000cb0003000000000000",
        crew=(("commander", "gunner"), ("radioman",), ("driver",), ("loader",)),
        capacity=77, max_hp=400, mass_kg=27940, power_hp=480, forward=56, reverse=20,
        chassis_yaw=37, turret_yaw=40, gun_yaw=39.375, reload=6, aiming=2.9, dispersion=.51,
        pitch=(-17, 6), shell="_76mm_UBR-354A", shell_cd=7178, caliber=76, damage=110,
        device_damage=105, penetration=(68, 62), speed=612),
    "t3485-stock": dict(resource="T-34-85", folder="R07_T-34-85", gun_part="Gun_01", type_cd=2561,
        modules=("T-34-85", "V-2-34", "Average", "_9R", "T-34-85", "_76mm_S-54"),
        module_cds=(5122, 261, 51974, 775, 4355, 1540), descriptor="010a14000100cb0003001100060000",
        crew=(("commander",), ("gunner",), ("radioman",), ("driver",), ("loader",)),
        capacity=68, max_hp=670, mass_kg=32370, power_hp=500, forward=54, reverse=20,
        chassis_yaw=36, turret_yaw=46, gun_yaw=39.375, reload=4.1, aiming=2.9, dispersion=.41,
        pitch=(-22, 7), shell="_76mm_UBR-354MA", shell_cd=7946, caliber=76, damage=115,
        device_damage=105, penetration=(125, 115), speed=816),
}
_MEMBER_ROWS = {
    "t26-stock": (
        ("Hull.model", 215, "ea01b8ca6149cbd0d93fd49f7c1f5b7820938125d7169e20293d4d6616199d3b"),
        ("Hull.visual", 2490, "58ba907b403f3bbe6c7283f4d4b89e8fede9260219f6024a16fc069603b275de"),
        ("Hull.primitives", 15120, "9801de66b588d46233ca89878a89b2d77cb342638f0acb181eb163361f506072"),
        ("Turret_01.model", 222, "20b01772400490d8533fffeefd4e821ea1764333b9322fdd6601e59520074c6f"),
        ("Turret_01.visual", 2102, "409f3c690027df6c7cb7078ce5aeebd558060c034431289165bd43a9a36e189f"),
        ("Turret_01.primitives", 18464, "301bebeb30a526247a02a9c445a99ca56237043b6576325112ea8c7be5b5d019"),
        ("Gun_02.model", 218, "418892105b37b143c27a559dc705e94fc73f00935cb6c095a063ea5a7390c339"),
        ("Gun_02.visual", 917, "303e45f579a2c2e87e92aa6121caf85059663b3602a6e9d80c2d6e546f7e03a4"),
        ("Gun_02.primitives", 14900, "7757345d1c4b9d4e4536b616e636d4f965de84d98dd8a5dca273c18a9cd3c82a")),
    "t34-stock": (
        ("Hull.model", 214, "da2fd232f6c91d34b287e8569217c9ada8f564e6bea7fab17faf3721be87072c"),
        ("Hull.visual", 2461, "d228c03c0155423da8612220d0c78610b5a7552d20424eb9895a973d8b2c32d5"),
        ("Hull.primitives", 18220, "9749e22f38d55d7df1ecf5df9c9bcb3c540d737841b37a742f006e96b28bf0c3"),
        ("Turret_01.model", 222, "e4f8db9d2c8199fc2b0a34412f702bf7b891672423ab8eb0de56ae0e6b4a03bd"),
        ("Turret_01.visual", 2289, "920ad1eff7c795c13521c77793fcaf10df0e03b8eed938c25151919b9db80eec"),
        ("Turret_01.primitives", 27844, "bb39b0b18d07180912bbc6106d0ced50f7a468ad6587bc3ef63fd432f6bee51b"),
        ("Gun_01.model", 218, "01278d53c2c945aeabfc65ff68a7ece91c82c3e3fc7eb2bbc1897be077490408"),
        ("Gun_01.visual", 917, "274043dfafca7f6fc8c9fe6f4a56b7e95cf637c752ee0aabcc605d6b210ffa26"),
        ("Gun_01.primitives", 18412, "1d43878445526f453a34b8b9685c02095294f15b9751c438faf6014c6abd35af")),
    "t3485-stock": (
        ("Hull.model", 217, "13804c01a715c193039b545b6b86de4385985c2b72aef774347b27fe54f775e4"),
        ("Hull.visual", 3401, "5c6c4bd0593dc283f57e2a3f7acb0a18f68dc111f7cf27c415a1726fb19319df"),
        ("Hull.primitives", 20892, "5a735d6651370c035e63029e9a0e42f17f23c496f0992135f7abc20cda33119f"),
        ("Turret_01.model", 220, "584d7df707a84c039b97939f13945ba24bb9aa54470c6d7b01ece125ea9cba10"),
        ("Turret_01.visual", 3051, "e67d916addd6499d2da5eeea316b2c015a43a9e17cb704c7f0dc7ab9599510fe"),
        ("Turret_01.primitives", 44280, "a5f9f6db6078fa68500179579cdf0aad20f4d718f69728b297e3511515db3206"),
        ("Gun_01.model", 222, "9784d276b970971b13223b70af9157d52f7149eb18f7fc303ab330ba85a529f7"),
        ("Gun_01.visual", 1475, "2d86b30ee9584b15af4f26ee2676d3db52ab95a1314062b654d69dcbe8671203"),
        ("Gun_01.primitives", 16668, "2860d9e3a391ffcdc6d32aae865c16cd036acc36b55834204e1bb1ebc2052b2c")),
}
MEMBER_PINS = {PACKAGE + "!vehicles/russian/" + SPECS[key]["folder"] + "/collision/" + name:
               {"bytes": size, "sha256": digest}
               for key, rows in _MEMBER_ROWS.items() for name, size, digest in rows}
MEMBER_PINS[materials.KINDS_KEY] = copy.deepcopy(materials.MEMBER_PINS[materials.KINDS_KEY])


class ProfileError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ProfileError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def source_spec():
    return copy.deepcopy(dict(schema="p04m-source-spec.v1", catalog_sha256=SPEC_CATALOG_SHA256,
        assemblies=SPECS, files=FILE_PINS, packages=PACKAGE_PINS, members=MEMBER_PINS))


def source_revision():
    return "p04m-717:" + sha(canonical(source_spec()))


def verify_sources(payloads, packages):
    require(type(packages) is dict and packages == PACKAGE_PINS, "package pins differ")
    pins = {**FILE_PINS, **MEMBER_PINS}
    require(type(payloads) is dict and set(payloads) == set(pins), "exact source member set required")
    for name, pin in pins.items():
        raw = payloads[name]
        require(type(raw) is bytes and 0 < len(raw) <= MAX_SOURCE, "source bytes bound: " + name)
        require(dict(bytes=len(raw), sha256=sha(raw)) == pin, "source pin differs: " + name)


def load_sources(original):
    """Audit complete packages in place; read only the27 collision members plus kinds."""
    original = no_links(original).resolve(strict=True)
    require(original.is_dir() and not original.is_relative_to(ROOT / "local"), "original root must be outside local")
    payloads = {}
    for name, pin in FILE_PINS.items():
        path = no_links(original / name)
        raw = geometry.common.source.read_limited(path, MAX_SOURCE)
        require(dict(bytes=len(raw), sha256=sha(raw)) == pin, "source pin differs: " + name)
        payloads[name] = raw
    for package, pin in PACKAGE_PINS.items():
        rows = {key.split("!", 1)[1]: p for key, p in MEMBER_PINS.items() if key.startswith(package + "!")}
        found = geometry.read_members(original, package, rows, pin)
        payloads.update({package + "!" + name: raw for name, raw in found.items()})
    verify_sources(payloads, PACKAGE_PINS)
    return payloads, copy.deepcopy(PACKAGE_PINS), load_catalog(original)


def number(value, label, minimum=0, maximum=1_000_000):
    require(type(value) in (int, float, str), label + " scalar required")
    if isinstance(value, str):
        require(len(value) <= 32 and re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", value), label + " numeric spelling")
    result = float(value)
    require(math.isfinite(result) and minimum <= result <= maximum, label + " finite bounds")
    return result


def vector(value, size, label):
    value = value.split() if isinstance(value, str) else value
    require(type(value) is list and len(value) == size, label + " vector width")
    return [number(v, label, -10_000, 10_000) for v in value]


def _component(part, index, prefix, payloads, effective):
    read = lambda suffix: payloads[PACKAGE + "!" + prefix + part + "." + suffix]
    model = dict(walk(decode(read("model"), max_bytes=MAX_SOURCE, max_depth=32, max_nodes=20000)))
    visual = dict(walk(decode(read("visual"), max_bytes=MAX_SOURCE, max_depth=32, max_nodes=20000)))
    require(model.get("/nodelessVisual[1]") == prefix + part, "collision model/visual binding differs")
    require(visual.get("/node[1]/identifier[1]") == "Scene Root" and
            visual.get("/node[1]/transform[1]") == [1., 0., 0., 0., 1., 0., 0., 0., 1., 0., 0., 0.], "nonidentity visual root")
    require(visual.get("/renderSet[1]/treatAsWorldSpaceObject[1]") is False, "world-space collision mesh unsupported")
    raw = read("primitives")
    mesh = collision_mesh(raw)
    require(mesh["vertex_count"] <= 4096 and mesh["triangle_count"] <= 8192 and
            0 < len(mesh["groups"]) <= 64, "component mesh bound")
    start = mesh["sections"]["vertices"]["offset"] + 68
    vertices = [list(struct.unpack_from("<3f", raw, start + i * 32)) for i in range(mesh["vertex_count"])]
    require(all(abs(v) <= 10 for row in vertices for v in row), "component vertex bounds")
    start = mesh["sections"]["indices"]["offset"]
    fmt = raw[start:start + 64].split(b"\0", 1)[0]
    ids = struct.unpack_from("<" + ("H" if fmt == b"list" else "I") * mesh["index_count"], raw, start + 72)
    groups = {key for key in visual if re.fullmatch(r"/renderSet\[1\]/geometry\[1\]/primitiveGroup\[[0-9]+\]", key)}
    require(len(groups) == len(mesh["groups"]), "visual primitive group count differs")
    require(materials._string(visual.get("/renderSet[1]/geometry[1]/vertices[1]"), "vertex reference") == "vertices" and
            visual.get("/renderSet[1]/geometry[1]/primitive[1]") == "indices", "visual primitive references differ")
    triangles, labels = [None] * mesh["triangle_count"], set()
    for n, group in enumerate(mesh["groups"], 1):
        path = "/renderSet[1]/geometry[1]/primitiveGroup[" + str(n) + "]"
        label = visual.get(path + "/material[1]/identifier[1]")
        require(label in materials.EXPECTED_KINDS, "unmapped material kind")
        require(visual.get(path) == n - 1 and visual.get(path + "/material[1]/materialKind[1]") == materials.EXPECTED_KINDS[label]
                and visual.get(path + "/material[1]/collisionFlags[1]") == 0
                and visual.get(path + "/material[1]/fx[1]") == "shaders/std_effects/lightonly.fx", "primitive material binding differs")
        require(group["start_index"] % 3 == 0 and group["triangle_count"] > 0, "primitive group range")
        labels.add(label)
        for i in range(group["start_index"] // 3, group["start_index"] // 3 + group["triangle_count"]):
            require(i < len(triangles) and triangles[i] is None, "triangle overlap/outside group")
            a, b, c = ids[3 * i:3 * i + 3]
            require(all(group["start_vertex"] <= v < group["start_vertex"] + group["vertex_count"] for v in (a, b, c)), "triangle escapes group vertices")
            triangle = dict(triangle_id=index * 100000 + i, a=a, b=b, c=c, material=label,
                            mesh=part, group="primitiveGroup[" + str(n) + "]")
            require(not geometry.exact_zero_area(vertices, triangle), "unexpected zero-area triangle; no inherited exclusions")
            triangles[i] = triangle
    require(all(t is not None for t in triangles), "triangle coverage gap")
    entries = []
    for label in sorted(set(effective) | labels, key=lambda k: materials.EXPECTED_KINDS[k]):
        record = effective.get(label)
        if record is not None:
            materials._validate_effective(record, materials.EXPECTED_KINDS[label])
        entries.append(dict(name=label, kind=materials.EXPECTED_KINDS[label], effective=record))
    visual_bounds = [vector(visual["/boundingBox[1]/" + edge + "[1]"], 3, "visual bounds") for edge in ("min", "max")]
    return dict(name=part, vertices=vertices, triangles=triangles, materials=entries,
                visual_bounds=visual_bounds, mesh_bounds=mesh["bounds"], excluded_degenerate_triangle_ids=[])


def _effective(node, defaults):
    """Generic bounded local armor overrides, preserving absent != zero."""
    fields = materials._children(node, "active armor")
    require(0 < len(fields) <= materials.MAX_MATERIALS and set(fields) <= set(materials.EXPECTED_KINDS), "active armor kind bound")
    result = {}
    for label, value in fields.items():
        require(label in defaults, "missing common material default")
        record, overrides = copy.deepcopy(defaults[label]), {}
        if isinstance(value, dict):
            overrides = materials._children(value, "active material override")
            value = value["value"]
        record["armor"] = materials._number(value, "active armor", materials.MAX_ARMOR)
        allowed = {"vehicleDamageFactor", *materials.BOOL_FIELDS}
        if not record["extra_is_none"]:
            allowed.update(materials.FRACTION_FIELDS[1:])
        require(set(overrides) <= allowed, "unsupported active material override")
        for field, value in overrides.items():
            record[field] = materials._bool(value, field) if field in materials.BOOL_FIELDS else materials._number(value, field, 1.)
        result[label] = record
    return result


def _build_profile(key, payloads, catalog, defaults):
    require(key in SPECS, "unknown curated stock assembly")
    spec = SPECS[key]
    vehicle_id = "vehicle:ussr:" + spec["resource"]
    vehicle = catalog.vehicles[vehicle_id]
    module_ids = dict(zip(MODULE_KINDS, ("module:ussr:" + kind + ":" + name for kind, name in zip(MODULE_KINDS, spec["modules"]))))
    require(vehicle["defaults"] == module_ids and vehicle["native_compact_id"] == spec["type_cd"], "stock module selection differs")
    require([catalog.modules[module_ids[k]]["native_compact_id"] for k in MODULE_KINDS] == list(spec["module_cds"]), "stock module compact IDs differ")
    require(vehicle["crew_roles"] == [list(row) for row in spec["crew"]], "actual stock crew roles differ")
    cd = descriptor(catalog, dict(vehicle_id=vehicle_id, modules=module_ids)).hex()
    require(cd == spec["descriptor"], "plain stock descriptor differs")
    raw = payloads[PREFIX + spec["resource"].lower() + ".xml"]
    node = decode(raw, max_bytes=MAX_SOURCE, max_depth=32, max_nodes=20000)
    flat = dict(walk(node))
    chassis = "/chassis[1]/" + spec["modules"][0] + "[1]"
    turret = "/turrets0[1]/" + spec["modules"][4] + "[1]"
    gun = turret + "/guns[1]/" + spec["modules"][5] + "[1]"
    shared = dict(walk(decode(payloads[PREFIX + "components/guns.xml"], max_bytes=MAX_SOURCE)))
    shared_gun = "/shared[1]/" + spec["modules"][5] + "[1]"
    require(flat[gun] == "shared" and not any(k.startswith(gun + "/shots[") for k in flat), "unadmitted shot override")
    mounted = lambda field: flat.get(gun + "/" + field + "[1]", shared.get(shared_gun + "/" + field + "[1]"))
    for field, expected in (("maxAmmo", spec["capacity"]), ("reloadTime", spec["reload"]),
                            ("aimingTime", spec["aiming"]), ("shotDispersionRadius", spec["dispersion"])):
        require(number(mounted(field), field) == expected, "mounted gun fact differs: " + field)
    require(mounted("clip") is None and mounted("burst") is None, "stock automatic gun unsupported")
    pitch = vector(mounted("pitchLimits"), 2, "mounted pitch limits")
    require(pitch == list(spec["pitch"]), "stock pitch limits differ")
    shell_flat = dict(walk(decode(payloads[PREFIX + "components/shells.xml"], max_bytes=MAX_SOURCE)))
    shell = "/" + spec["shell"] + "[1]"
    shot = shared_gun + "/shots[1]/" + spec["shell"] + "[1]"
    require(shell_flat[shell + "/kind[1]"] == "ARMOR_PIERCING" and
            number(shell_flat[shell + "/id[1]"], "shell ID") * 256 + 10 == spec["shell_cd"], "stock AP identity differs")
    for path, expected in ((shell + "/caliber[1]", spec["caliber"]),
                           (shell + "/damage[1]/armor[1]", spec["damage"]),
                           (shell + "/damage[1]/devices[1]", spec["device_damage"])):
        require(number(shell_flat[path], "AP source fact") == expected, "stock AP definition differs")
    require(number(shared[shot + "/speed[1]"], "AP speed") == spec["speed"] and
            vector(shared[shot + "/piercingPower[1]"], 2, "AP penetration") == list(spec["penetration"]) and
            number(shared[shot + "/gravity[1]"], "AP gravity") == 9.81 and
            number(shared[shot + "/maxDistance[1]"], "AP distance") == 720, "stock gun AP shot differs")
    common_flat = dict(walk(decode(payloads[materials.COMMON_REL], max_bytes=MAX_SOURCE)))
    factor = number(common_flat["/miscParams[1]/projectileSpeedFactor[1]"], "projectile factor")
    require(factor == .8, "projectile speed factor differs")
    mass = vehicle["hull_mass_grams"] / 1000 + sum(catalog.modules[v]["mass_grams"] / 1000 for v in module_ids.values())
    hp = vehicle["hull_max_hp"] + vehicle["turret_max_hp"][module_ids["turret"]]
    power = catalog.modules[module_ids["engine"]]["power_hp"]
    require((mass, hp, power) == (spec["mass_kg"], spec["max_hp"], spec["power_hp"]), "source mass/HP/power differs")
    movement = dict(mass_kg=mass, engine_power_hp=power, max_forward_kph=number(flat["/speedLimits[1]/forward[1]"], "forward"),
        max_reverse_kph=number(flat["/speedLimits[1]/backward[1]"], "reverse"),
        chassis_yaw_deg_s=number(flat[chassis + "/rotationSpeed[1]"], "chassis yaw"),
        turret_yaw_deg_s=number(flat[turret + "/rotationSpeed[1]"], "turret yaw"),
        gun_yaw_deg_s=number(shared[shared_gun + "/rotationSpeed[1]"], "gun yaw"),
        brake_force_source=number(flat[chassis + "/brakeForce[1]"], "brake force"),
        top_right_carrying_point=vector(flat[chassis + "/topRightCarryingPoint[1]"], 2, "carrying point"),
        terrain_resistance=vector(flat[chassis + "/terrainResistance[1]"], 3, "terrain resistance"),
        rotation_is_around_center=flat[chassis + "/rotationIsAroundCenter[1]"],
        wheel_source={path[len(chassis):]: value for path, value in flat.items() if path.startswith(chassis + "/wheels[1]/")})
    require([movement[k] for k in ("max_forward_kph", "max_reverse_kph", "chassis_yaw_deg_s", "turret_yaw_deg_s", "gun_yaw_deg_s")] ==
            [spec[k] for k in ("forward", "reverse", "chassis_yaw", "turret_yaw", "gun_yaw")], "source movement facts differ")
    require(type(movement["rotation_is_around_center"]) is bool, "rotation flag source type")
    pivots = dict(hull_position=vector(flat[chassis + "/hullPosition[1]"], 3, "hull position"),
        turret_position=vector(flat["/hull[1]/turretPositions[1]/turret[1]"], 3, "turret position"),
        gun_position=vector(flat[turret + "/gunPosition[1]"], 3, "gun position"))
    prefix = "vehicles/russian/" + spec["folder"] + "/collision/"
    parts = ("Hull", "Turret_01", spec["gun_part"])
    paths = (("hull",), ("turrets0", spec["modules"][4]), ("turrets0", spec["modules"][4], "guns", spec["modules"][5]))
    components = []
    for i, (part, path) in enumerate(zip(parts, paths)):
        section = materials._section(node, path)
        fields = materials._children(section, "active component")
        hit = materials._children(fields["hitTester"], "hit tester")
        require(hit["collisionModel"] == prefix + part + ".model", "selected collision model differs")
        components.append(_component(part, i, prefix, payloads, _effective(fields["armor"], defaults)))
    hull = components[0]["mesh_bounds"]
    source_box = dict(half_extents=[(hi - lo) / 2 for lo, hi in zip(hull["min"], hull["max"])],
        center_offset=[(hull["min"][i] + hull["max"][i]) / 2 + pivots["hull_position"][i] for i in range(3)],
        classification="DERIVED_COLLISION_HULL_AABB_NOT_ADMITTED_PHYSICS")
    result = dict(schema=SCHEMA, assembly_id=key, source_revision=source_revision(), source_pins=source_spec(),
        classification="VERIFIED_STATIC_ORIGINAL_717", battle_admission=False,
        identity=dict(vehicle_id=vehicle_id, type_compact_id=spec["type_cd"], descriptor_hex=cd,
                      modules=module_ids, module_compact_ids=dict(zip(MODULE_KINDS, spec["module_cds"])), crew_roles=vehicle["crew_roles"], max_hp=hp),
        gun=dict(capacity=spec["capacity"], reload_seconds=spec["reload"], aiming_seconds=spec["aiming"],
                 shot_dispersion_radius=spec["dispersion"], raw_pitch_limits=pitch, mount_source_path=gun,
                 allowed_shell_kinds=["ARMOR_PIERCING"], shell_resource=spec["shell"], shell_compact_id=spec["shell_cd"],
                 caliber_mm=spec["caliber"], damage_hp=spec["damage"], device_damage=spec["device_damage"],
                 penetration_mm=list(spec["penetration"]), raw_speed_mps=spec["speed"], projectile_speed_factor=factor,
                 speed_mps=spec["speed"] * factor, gravity_mps2=9.81, max_distance_m=720, shot_source_path=shot),
        movement_source=movement, geometry=dict(**pivots, components=components, hull_aabb_candidate=source_box),
        runtime_physics=None, unknowns=["native_hitTester_bbox", "native_effective_material_oracle",
            "physics_support_selection_and_radius", "suspension_friction_torque_policy", "controller_worker_validation",
            "native_aim_render_and_manual_owner_acceptance"])
    require(len(canonical(result)) <= MAX_PROFILE, "export profile size bound")
    return result


def build_profiles(payloads, packages, catalog):
    # All byte pins before any parser, including a late mesh/default loader.
    verify_sources(payloads, packages)
    require(catalog.sha256 == CATALOG_SHA256, "research catalogue differs")
    defaults = materials._loader_defaults(payloads[materials.LOADER_REL])
    for name in (materials.KINDS_LOADER_REL, materials.VEHICLE_REL):
        parse_pyc(payloads[name])
    mapping = materials._kind_mapping(decode(payloads[materials.KINDS_KEY], max_bytes=MAX_SOURCE))
    defaults = materials._common_materials(decode(payloads[materials.COMMON_REL], max_bytes=MAX_SOURCE), mapping, defaults)
    return {key: _build_profile(key, payloads, catalog, defaults) for key in SPECS}


def export(original, out):
    """Fresh no-link output below project local; never replace a prior proof."""
    local = no_links(ROOT / "local").resolve(strict=True)
    out = owned(local, Path(out).absolute())
    require(not out.exists() and out.parent.is_dir(), "fresh output with existing parent required")
    profiles = build_profiles(*load_sources(original))
    out.mkdir()
    rows = []
    for key, profile in profiles.items():
        raw = canonical(profile) + b"\n"
        name = key + ".json"
        with (out / name).open("xb") as stream:
            stream.write(raw)
        rows.append(dict(assembly_id=key, file=name, bytes=len(raw), sha256=sha(raw), battle_admission=False))
    receipt = dict(schema="p04m-source-export.v1", status="PASS_PINNED_SOURCE_EXPORT", source_revision=source_revision(),
                   profiles=rows, runtime_worker="NOT_RUN", native="NOT_RUN", source_packages_copied=False)
    with (out / "manifest.json").open("xb") as stream:
        stream.write(canonical(receipt) + b"\n")
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(export(args.original, args.out)))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps(dict(status="FAIL_P04M_SOURCE_EXPORT", reason=str(error))))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
