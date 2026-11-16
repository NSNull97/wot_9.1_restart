"""Hash-bound #717 optional-device and consumable source catalogue."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
import sys
from types import MappingProxyType

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.destructible_catalog import read
from tools.p09e_research_catalog import child, children, scalar
from tools.packed_xml import decode

BASE = "res/scripts/item_defs/vehicles/common/"
PINS = {
    "optional_devices.xml": (9, 43, 14807, "f24f01573b3848df1a5051752a2e5f937857e7062b78a4dd1812194486c843c6"),
    "equipments.xml": (11, 18, 4626, "d98e409abe78ed3278d033bfb5340a8897b5dc69e6881901bab70f6746eef461"),
}
SCHEMA = "wot091-content0-artefacts.v1"
SOURCE_BUILD = "v.0.9.1 #717 RU"
MANIFEST = Path(__file__).resolve().parents[1] / "config/catalog/artefacts.v1.json"
MAX_MANIFEST = 32768
MANIFEST_SHA256 = "2c38786202ef015ae0e3a645719b869fe1e01421b7ec9521e2af93332f4b76af"
GASOLINE_MANIFEST = MANIFEST.with_name("gasoline_engine_ids.v1.json")
GASOLINE_MANIFEST_SHA256 = "d67e3353e6a866f274c5f358d1ba9c759ee3d48dd34dd59a1d666804c99a67f2"
GROUSER_MANIFEST = MANIFEST.with_name("grouser_vehicle_ids.v1.json")
SLOT_COUNT = 3

VENTILATION_BONUS = {
    4601: "improvedVentilation_class1",
    4857: "improvedVentilation_class2",
    5113: "improvedVentilation_class3",
}
CREW_FOOD = {
    2555: "chocolate", 3067: "ration", 3579: "hotCoffee", 4091: "ration_china",
    4603: "ration_uk", 4859: "ration_japan", 25851: "cocacola",
}
FUELS = {
    1787: "lendLeaseOil", 2043: "gasoline100", 2299: "gasoline105", 4347: "qualityOil",
}
RPM_LIMITER = 3323
WET_AMMO_RACKS = {6905: "wetCombatPack_class1", 7161: "wetCombatPack_class2"}
CO2_FUEL_TANK = 7417
CYCLONE_FILTER = 7673
SPALL_LINERS = {
    505: "antifragmentationLining_light", 761: "antifragmentationLining_medium",
    1017: "antifragmentationLining_heavy", 11001: "antifragmentationLining_superheavy",
}
ENHANCED_SUSPENSIONS = {
    2041: "enhancedSuspension_Vikkers", 2297: "enhancedSuspension_candle",
    2553: "enhancedSuspension_Christie", 2809: "enhancedTorsions1t",
    3065: "enhancedTorsions3t", 3321: "enhancedTorsions5t", 3577: "enhancedSprings",
    3833: "enhancedLevers", 4089: "enhancedBelwillWashers", 4345: "enhancedLongitudinalTorsions",
    8441: "enhancedVertical_springs", 8697: "enhancedHorizontal_springs",
    8953: "enhancedSprings_class2", 9209: "enhancedSprings_class3",
    9465: "enhancedHorizontal_springs_class2", 9721: "enhancedHorizontal_springs_class3",
    9977: "enhancedVertical_springs_class2", 10233: "enhancedVertical_springs_class3",
    10489: "enhancedVertical_elastic_elements", 10745: "enhancedHorizontal_elastic_elements",
}
SUSPENSION_MAX_LOAD_PERCENT = 110
SUSPENSION_TRACK_HEALTH_PERCENT = 120

# Authoritative runtime effect families backed by the battle command path.
DEVICE_EFFECTS = {
    249: "toolbox", 1273: "stereoscope", 1529: "coatedOptics", 5625: "mediumCaliberTankRammer",
    5881: "largeCaliberTankRammer", 6137: "mediumCaliberHowitzerRammer",
    6393: "largeCaliberHowitzerRammer", 6649: "enhancedAimDrives",
    CO2_FUEL_TANK: "carbonDioxide", CYCLONE_FILTER: "filterCyclone",
    7929: "aimingStabilizer_Mk1", 8185: "aimingStabilizer_Mk2",
    5369: "grousers",
} | VENTILATION_BONUS | WET_AMMO_RACKS | SPALL_LINERS | ENHANCED_SUSPENSIONS
CONSUMABLE_EFFECTS = {
    251: "handExtinguishers", 507: "autoExtinguishers",
    763: "smallMedkit", 1019: "largeMedkit",
    1275: "smallRepairkit", 1531: "largeRepairkit",
    RPM_LIMITER: "removedRpmLimiter",
} | CREW_FOOD | FUELS
SUPPORTED_ITEMS = DEVICE_EFFECTS | CONSUMABLE_EFFECTS
CAMOUFLAGE_NET = 1785
_NET_SCOPE = ContextVar("content0_s5a_net_enabled", default=False)


@contextmanager
def trusted_camouflage_test_scope():
    """Internal preparation seam, not a gateway handshake or an authorization.

    There is intentionally no Domain/config/command entry point to this scope.
    Before production wiring, the caller MUST validate the live Domain and
    gateway capabilities on the authenticated channel for the whole request.
    A request body, client flag, environment variable or config file alone is
    not such proof. ContextVar keeps concurrent threads/tasks independent and
    restores the previous value on every exit, including exceptions.
    """
    token = _NET_SCOPE.set(True)
    try:
        yield
    finally:
        _NET_SCOPE.reset(token)


def active_device_effects():
    return DEVICE_EFFECTS | ({CAMOUFLAGE_NET: "camouflageNet"} if _NET_SCOPE.get() else {})


def canonical(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")


def _criteria(node):
    return {key: _criteria(value) if children(value) else scalar(value) for key, value in children(node)}


def build_fitment_manifests(original_root):
    from tools.p09e_research_catalog import PIN_PATH, _build_catalog

    pins = json.loads(read(PIN_PATH, 256 * 1024))["sources"]
    engine_tags = {}
    catalog = _build_catalog(Path(original_root).resolve(strict=True), pins, engine_tags=engine_tags)
    return {
        GASOLINE_MANIFEST: canonical(sorted(cd for cd, tags in engine_tags.items() if "gasoline" in tags)),
        GROUSER_MANIFEST: canonical(sorted(row["native_compact_id"] for row in catalog.vehicles.values()
                                          if "grousers_user" in row["tags"])),
    }


@lru_cache(maxsize=1)
def gasoline_engine_ids():
    ids = json.loads(read(GASOLINE_MANIFEST, 16384, GASOLINE_MANIFEST_SHA256))
    if (type(ids) is not list or not ids or any(type(cd) is not int or not 0 < cd < 2**24 or cd & 15 != 5 for cd in ids)
            or sorted(set(ids)) != ids):
        raise ValueError("invalid gasoline engine manifest")
    return frozenset(ids)


def build(original_root):
    items, sources = [], {}
    for name, (kind, count, length, digest) in PINS.items():
        relative = BASE + name
        raw = read(Path(original_root) / relative, length, digest)
        rows = children(decode(raw, max_bytes=length, max_depth=12, max_nodes=5000))
        if len(raw) != length or len(rows) != count:
            raise ValueError("artefact source count or size mismatch")
        sources[relative] = {"bytes": length, "sha256": digest}
        for source_name, node in rows:
            item_id = scalar(child(node, "id"))
            price = child(node, "price")
            script = child(node, "script")
            compact_id = (item_id << 8) | 0xf0 | kind
            incompatible = child(node, "incompatibleTags", "")
            if compact_id in FUELS and (_criteria(incompatible) != {"installed": "fuel"}
                                        or scalar(child(node, "tags")) != "fuel"):
                raise ValueError("fuel installed conflict differs from #717 source")
            items.append({
                "compact_id": compact_id, "kind": kind, "source_id": item_id, "source_name": source_name,
                "price": {"currency": "gold" if child(price, "gold") is not None else "credits", "amount": scalar(price)},
                "removable": scalar(child(node, "removable", True)),
                "tags": scalar(child(node, "tags", "")).split(),
                "incompatible_tags": scalar(incompatible).split(),
                "filters": [[mode, _criteria(entry)] for mode, entry in children(child(node, "vehicleFilter"))],
                "script": scalar(script), "effect": _criteria(script),
            })
    items.sort(key=lambda row: row["compact_id"])
    if len(items) != len({row["compact_id"] for row in items}):
        raise ValueError("duplicate artefact compact ID")
    return {"schema": SCHEMA, "source_build": SOURCE_BUILD, "sources": sources, "items": items}


@dataclass(frozen=True)
class VehicleFilter:
    exclude: bool
    nations: frozenset[str]
    tags: frozenset[str]
    min_level: int
    max_level: int
    engine_tags: frozenset[str]

    def matches(self, vehicle, engine_tags):
        return (not self.nations or vehicle["nation"] in self.nations) and (
            not self.tags or not self.tags.isdisjoint(vehicle["tags"])) and (
            not self.engine_tags or not self.engine_tags.isdisjoint(engine_tags)) and self.min_level <= vehicle["tier"] <= self.max_level


def _vehicle_filter(mode, entry):
    if mode not in ("include", "exclude") or set(entry) - {"nations", "vehicle", "engine"}:
        raise ValueError("unsupported restriction on live artefact")
    vehicle = entry.get("vehicle", {})
    if set(vehicle) - {"tags", "minLevel", "maxLevel"}:
        raise ValueError("unsupported vehicle filter on live artefact")
    engine = entry.get("engine")
    if engine is not None and engine != {"tags": "gasoline"}:
        raise ValueError("unsupported engine filter on live artefact")
    return VehicleFilter(mode == "exclude", frozenset(entry.get("nations", "").split()),
                         frozenset(vehicle.get("tags", "").split()), vehicle.get("minLevel", 0),
                         vehicle.get("maxLevel", 255), frozenset(engine["tags"].split() if engine else ()))


@dataclass(frozen=True)
class LiveItem:
    compact_id: int
    kind: int
    removable: bool
    tags: frozenset[str]
    incompatible_tags: frozenset[str]
    weight_grams: int
    weight_percent: int
    filters: tuple[VehicleFilter, ...]

    def compatible(self, vehicle, engine_tags=()):
        if any(row.exclude and row.matches(vehicle, engine_tags) for row in self.filters):
            return False
        inclusions = [row for row in self.filters if not row.exclude]
        return not inclusions or any(row.matches(vehicle, engine_tags) for row in inclusions)


def live_items():
    """Active set; absence of a trusted scope always means legacy closed."""
    return _live_items(_NET_SCOPE.get())


@lru_cache(maxsize=2)
def _live_items(net_enabled):
    supported = DEVICE_EFFECTS | CONSUMABLE_EFFECTS | ({CAMOUFLAGE_NET: "camouflageNet"} if net_enabled else {})
    raw = read(MANIFEST, MAX_MANIFEST, MANIFEST_SHA256)
    document = json.loads(raw)
    if document["schema"] != SCHEMA or document["source_build"] != SOURCE_BUILD:
        raise ValueError("invalid artefact catalogue identity")
    result = {}
    for row in document["items"]:
        cd = row["compact_id"]
        if cd in supported:
            effect = row["effect"]
            weight = effect.get("weight", 0)
            fraction = effect.get("vehicleWeightFraction", "0")
            expected_fraction = "0.01" if cd in WET_AMMO_RACKS else "0"
            suspension = cd in ENHANCED_SUSPENSIONS
            if (row["source_name"] != supported[cd] or type(weight) is not int or not 0 <= weight <= 1500
                    or fraction != expected_fraction or effect.get("chassisMaxLoadFactor") != ("1.1" if suspension else None)
                    or cd == CAMOUFLAGE_NET and (row["kind"] != 9 or row["source_id"] != 6
                        or not row["removable"] or row["filters"] or row["tags"] or row["incompatible_tags"]
                        or row["script"] != "CamouflageNet" or effect != {"weight": 100, "activateWhenStillSec": "3.0"})
                    or suspension and (row["script"] != "EnhancedSuspension" or weight != 0 or row["removable"]
                                       or effect.get("chassisHealthFactor") != "1.2"
                                       or effect.get("vehicleByChassisDamageFactor") != "0.5")):
                raise ValueError("unsupported identity or weight on live artefact")
            # v1 persists the canonical hash in save files. The source builder
            # checks the nested installed tag without changing that receipt.
            conflicts = (*row["incompatible_tags"], "fuel") if cd in FUELS else row["incompatible_tags"]
            result[cd] = LiveItem(cd, row["kind"], row["removable"],
                                  frozenset(row["tags"]), frozenset(conflicts), weight * 1000,
                                  int(fraction == "0.01"),
                                  tuple(_vehicle_filter(mode, entry) for mode, entry in row["filters"]))
    if set(result) != set(supported):
        raise ValueError("incomplete artefact catalogue binding")
    return MappingProxyType(result)


def compatible_suspension(vehicle):
    return next((cd for cd in ENHANCED_SUSPENSIONS if live_items()[cd].compatible(vehicle)), None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("build", "check"))
    parser.add_argument("--client", required=True)
    args = parser.parse_args()
    raw = canonical(build(args.client))
    fitment = build_fitment_manifests(args.client)
    if args.operation == "build":
        MANIFEST.write_bytes(raw)
        for path, content in fitment.items():
            path.write_bytes(content)
    elif raw != read(MANIFEST, MAX_MANIFEST, MANIFEST_SHA256):
        raise SystemExit("artefact catalogue differs from pinned client sources")
    elif any(content != read(path, 16384) for path, content in fitment.items()):
        raise SystemExit("equipment fitment manifests differ from pinned client sources")
    print(sha256(raw).hexdigest())


if __name__ == "__main__":
    main()
