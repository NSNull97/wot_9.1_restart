"""CONTENT-0 step 0: the 0.9.1 (#717) content inventory, client <-> server.

Read-only over the original client (never executes client code) and this checkout's
server tables. Client facts are VERIFIED by the hashed source files listed in the
output; the hangar/battle operation statuses are a hand-kept table of what this
server does today (each row names its evidence), not client data.

    python -B -X utf8 tools/content0_inventory.py build --client C:/WoT_0.9.1_RU_0717_original
    python -B -X utf8 tools/content0_inventory.py check --client C:/WoT_0.9.1_RU_0717_original
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.destructible_catalog import no_links  # noqa: E402
from tools.p09e_research_catalog import NATIONS, child, children, load_catalog, scalar  # noqa: E402
from tools.packed_xml import decode  # noqa: E402

SCHEMA = "wot091-content0-inventory.v1"
TARGET = "v.0.9.1 #717 RU"
OUT = ROOT / "docs" / "research" / "content0_inventory.v1.json"
MAX_XML = 8 * 1024 * 1024
CLASSES = ("lightTank", "mediumTank", "heavyTank", "AT-SPG", "SPG")

# What this server does today, per hangar/battle operation (hand-kept, OBSERVED/VERIFIED
# by the named evidence; update with each CONTENT-0 step). status: works | partial | closed | absent | unknown.
OPERATIONS = (
    ("research_vehicle_module", "works", 3, "P09E research service; costs xp/credits today (CONTENT-0: free)"),
    ("buy_vehicle", "works", 3, "P09E store buy_vehicle (stand -14: SU-8 bought 11.11)"),
    ("sell_vehicle", "closed", 14, "ACC-01: unavailable notice"),
    ("buy_slot", "closed", 14, "ACC-01: unavailable notice"),
    ("mount_module", "closed", 3, "client_patch/hangar_capabilities.py NOTICE (module changes)"),
    ("equipment_buy_install_remove", "closed", 5, "client_patch/hangar_capabilities.py NOTICE; model P04B only"),
    ("consumables_buy_install", "closed", 5, "client_patch/hangar_capabilities.py NOTICE"),
    ("consumables_in_battle", "absent", 5, "no server effect of repair kit / medkit / extinguisher"),
    ("shells_load_unload_own_depot", "works", 4, "P09D maintenance window, own depot only"),
    ("shells_buy", "closed", 4, "P09D notice: buying shells unavailable"),
    ("depot_window_shells", "absent", 4, "STATUS tail: Склад shows no shells"),
    ("shared_account_depot", "absent", 1, "server counts per vehicle mount; catalog refuses shared shell IDs"),
    ("repair", "closed", 7, "maintenance window: repair denied; post-battle repair is free and automatic"),
    ("repair_required_before_battle", "absent", 7, "damaged vehicle is repaired for free at return"),
    ("auto_maintenance", "closed", 7, "P09D: automatic maintenance unavailable"),
    ("crew_recruit_barracks", "works", 6, "P04K"),
    ("crew_recruit_into_vehicle_slot", "partial", 6, "P04D/P04H recruitment; hangar slot flow to verify (owner 11.11)"),
    ("crew_transfer_cross_vehicle", "works", 6, "P04F/P04G"),
    ("crew_dismissal", "works", 6, "P04J"),
    ("crew_skill_progression", "works", 6, "P04I"),
    ("crew_retrain_specialization", "absent", 6, "not implemented"),
    ("crew_skill_reset", "partial", 6, "P04L WIP branch codex/p04l-native-skill-reset"),
    ("crew_perks_in_battle", "partial", 6, "only sixth sense (project sound)"),
    ("battle_random_queue", "works", 2, "MM-01 queue, bots"),
    ("battle_leave_before_end", "unknown", 10, "vehicle state after an early leave not described yet"),
    ("battle_results_screen", "partial", 12, "P08C natural results; xp/credits 0"),
    ("battle_rewards", "absent", None, "ECON block after CONTENT-0 and PG-01"),
    ("statistics_dossier", "absent", 11, "hangar statistics stay 0"),
    ("achievements", "absent", 11, "not recorded"),
    ("appearance", "closed", 13, "client_patch/hangar_capabilities.py WINDOW_NOTICES appearance"),
    ("platoons", "absent", 14, "not implemented"),
    ("training_rooms", "works", 14, "P10B"),
)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


class Sources:
    def __init__(self, client):
        self.client = no_links(Path(client)).resolve(strict=True)
        self.pins = {}

    def xml(self, relative):
        path = self.client / relative
        raw = path.read_bytes()
        if len(raw) > MAX_XML:
            raise ValueError("client source bound: " + relative)
        self.pins[relative] = dict(bytes=len(raw), sha256=sha(raw))
        return decode(raw, max_bytes=MAX_XML, max_depth=48, max_nodes=400000)


def text(node, key, default=None):
    value = child(node, key)
    return default if value is None else scalar(value)


def gold(node):
    price = child(node, "price")
    return price is not None and any(name == "gold" for name, _ in children(price))


def items(src, relative, extra=()):
    rows = []
    for name, node in children(src.xml(relative)):
        row = dict(name=name, id=int(text(node, "id")), tags=str(text(node, "tags", "") or "").split(),
                   gold=gold(node))
        for key in extra:
            value = text(node, key)
            if value is not None:
                row[key] = str(value)
        rows.append(row)
    return rows


def vehicles(src, catalog):
    tables = {}
    for variant, directory in (("main", ROOT / "config" / "catalog"), ("test_lab", ROOT / "config" / "test_lab")):
        profiles = json.loads((directory / "battle_profiles.v1.json").read_text(encoding="utf-8"))["vehicles"]
        server = json.loads((directory / "catalog.v1.json").read_text(encoding="utf-8"))["vehicles"]
        qualified = json.loads((directory / "battle_qualification.v1.json").read_text(encoding="utf-8"))["profiles"]
        names = set(qualified) if isinstance(qualified, dict) else {q.get("kind") for q in qualified}
        tables[variant] = (
            {p["vehicle_id"]: p for p in profiles},
            {v["vehicle_id"]: v for v in server},
            names)
    rows = []
    for vehicle_id, v in sorted(catalog.vehicles.items()):
        classes = [t for t in v["tags"] if t in CLASSES]
        compatible = v["compatible"]
        row = dict(vehicle_id=vehicle_id, nation=v["nation"], tier=v["tier"], vehicle_class=classes[0] if classes else None,
                   secret="secret" in v["tags"], not_in_shop=bool(v.get("not_in_shop")),
                   gold_price=v["historical_price"]["currency"] == "gold",
                   modules={kind: len(ids) for kind, ids in sorted(compatible.items())})
        for variant, (profiles, server, _qualified) in tables.items():
            p = profiles.get(vehicle_id)
            s = server.get(vehicle_id)
            row[variant] = dict(profile=None if p is None else p["status"], refusal=None if p is None else p.get("refusal"),
                                in_catalog=s is not None, admission=None if s is None else s["battle_admission"])
        rows.append(row)
    return rows


def shells(src):
    rows = []
    for nation in NATIONS:
        for name, node in children(src.xml("res/scripts/item_defs/vehicles/%s/components/shells.xml" % nation)):
            if name == "icons":
                continue
            rows.append(dict(nation=nation, name=name, id=int(text(node, "id")), kind=str(text(node, "kind")),
                             caliber_mm=float(text(node, "caliber")), gold=gold(node)))
    return rows


def crew(src):
    data = src.xml("res/scripts/item_defs/tankmen/tankmen.xml")
    roles = [name for name, _ in children(child(data, "roles"))]
    skills = [name for name, _ in children(child(data, "skills"))]
    return dict(roles=roles, skills=skills)


def achievements(src):
    data = src.xml("res/scripts/item_defs/achievements.xml")
    rows = []
    for name, node in children(child(data, "achievements")):
        if name != "achievement":
            continue
        rows.append({key: str(scalar(value)) for key, value in children(node) if not list(children(value))})
    return rows


def destructibles(src):
    """res/scripts/destructibles.xml: the client's shoot-through constants and every destructible entry."""
    data = src.xml("res/scripts/destructibles.xml")
    constants, sections = {}, {}
    for name, node in children(data):
        rows = list(children(node))
        if not rows:
            constants[name] = str(scalar(node))
        elif name == "projectilePiercingPowerReduction":
            constants[name] = {material: str(scalar(value)) for material, value in rows}
        else:
            sections[name] = [dict(filename=str(text(entry, "filename")), health=str(text(entry, "health")))
                              for kind, entry in rows if kind == "entry"]
    limit = float(constants["maxHpForShootingThrough"])
    summary = {}
    for name, rows in sections.items():
        healths = [float(r["health"]) for r in rows if r["health"] not in (None, "None", "")]
        summary[name] = dict(entries=len(rows), shoot_through_by_health=sum(h <= limit for h in healths))
    return dict(constants=constants, summary=summary, sections=sections)


def maps(src):
    registry = json.loads((ROOT / "server" / "contracts" / "map_registry.json").read_text(encoding="utf-8"))["maps"]
    served = {m["asset"] for m in (registry if isinstance(registry, list) else registry.values())}
    rows = []
    for name, node in children(src.xml("res/scripts/arena_defs/_list_.xml")):
        if name != "map":
            continue
        asset = str(text(node, "name"))
        arena = src.xml("res/scripts/arena_defs/%s.xml" % asset)
        modes = sorted(n for n, _ in children(child(arena, "gameplayTypes"))) if child(arena, "gameplayTypes") is not None else []
        rows.append(dict(id=int(text(node, "id")), asset=asset, gameplay_types=modes,
                         package=(src.client / "res" / "packages" / (asset + ".pkg")).is_file(),
                         server_battle=asset in served))
    return rows


def build(client):
    src = Sources(client)
    catalog = load_catalog(src.client)
    vehicle_rows = vehicles(src, catalog)
    modules = collections.Counter(m["kind"] for m in catalog.document["modules"].values())
    shell_rows = shells(src)
    equipment = items(src, "res/scripts/item_defs/vehicles/common/optional_devices.xml")
    consumables = items(src, "res/scripts/item_defs/vehicles/common/equipments.xml")
    map_rows = maps(src)
    achievement_rows = achievements(src)
    destructible = destructibles(src)
    summary = dict(
        vehicles=len(vehicle_rows),
        vehicles_by_class=dict(sorted(collections.Counter(v["vehicle_class"] for v in vehicle_rows).items())),
        vehicles_secret=sum(v["secret"] for v in vehicle_rows),
        modules=dict(sorted(modules.items())),
        unlocks=len(catalog.document["unlocks"]),
        shells=len(shell_rows), shells_gold=sum(s["gold"] for s in shell_rows),
        equipment=len(equipment), equipment_gold=sum(e["gold"] for e in equipment),
        consumables=len(consumables), consumables_gold=sum(c["gold"] for c in consumables),
        maps=len(map_rows), maps_server_battle=sum(m["server_battle"] for m in map_rows),
        gameplay_types=dict(sorted(collections.Counter(t for m in map_rows for t in m["gameplay_types"]).items())),
        achievements=len(achievement_rows), destructibles=destructible["summary"],
        shoot_through=dict(max_hp=destructible["constants"]["maxHpForShootingThrough"],
                           piercing_power_reduction=destructible["constants"]["projectilePiercingPowerReduction"]))
    for variant in ("main", "test_lab"):
        summary[variant] = dict(
            in_catalog=sum(v[variant]["in_catalog"] for v in vehicle_rows),
            profile=dict(sorted(collections.Counter(str(v[variant]["profile"]) for v in vehicle_rows).items())),
            refusals=dict(sorted(collections.Counter(v[variant]["refusal"] for v in vehicle_rows if v[variant]["refusal"]).items())))
    crew_data = crew(src)
    summary["crew_skills"] = len(crew_data["skills"])
    return dict(schema=SCHEMA, target=TARGET, research_catalog_sha256=catalog.sha256,
                sources=dict(sorted(src.pins.items())), summary=summary,
                operations=[dict(operation=o, status=s, content0_step=step, evidence=e) for o, s, step, e in OPERATIONS],
                vehicles=vehicle_rows, shells=shell_rows, equipment=equipment, consumables=consumables,
                crew=crew_data, achievements=achievement_rows, maps=map_rows, destructibles=destructible)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("mode", choices=("build", "check"))
    p.add_argument("--client", type=Path, required=True)
    a = p.parse_args(argv)
    raw = canonical(build(a.client))
    if a.mode == "build":
        OUT.write_bytes(raw)
    elif OUT.read_bytes().replace(b"\r\n", b"\n") != raw:  # a checkout may turn LF into CRLF
        raise SystemExit("content0 inventory differs from the client and server tables")
    document = json.loads(raw)
    print(json.dumps(dict(status="PASS", sha256=sha(raw), summary=document["summary"]), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
