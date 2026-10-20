"""Bounded, read-only #717 research/assembly catalogue; never executes client code.

Only source metadata is checked in. Native unlock indices follow the pinned
VehicleType readers, not the web graph's display ordering. Catalogue presence
does not grant ownership, shop availability or battle eligibility.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import hashlib
import json
import marshal
import os
from pathlib import Path
import re
import sys
import tempfile

from tools.destructible_catalog import CatalogError, no_links, read, json_value
from tools.packed_xml import decode

TARGET = "v.0.9.1 #717 RU"
SCHEMA = "p09e-research-catalog.v1"
PIN_PATH = Path(__file__).with_name("p09e_source_pins.json")
NATIONS = ("ussr", "germany", "usa", "france", "uk", "china", "japan")
KINDS = {"chassis": (2, "chassis"), "turret": (3, "turrets"),
         "gun": (4, "guns"), "engine": (5, "engines"),
         "fuelTank": (6, "fuelTanks"), "radio": (7, "radios")}
NAME = re.compile(r"^[A-Za-z0-9_.-]{1,96}$")
MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 16 * 1024 * 1024
CACHE_SCHEMA = "p09e-research-catalog-cache.v1"
# Derived-document cache only; pinned sources are still read and hashed on every load.
CACHE_DIR = Path(__file__).resolve().parents[1] / "local" / "cache" / "p09e-research-catalog"
MAX_CACHE_BYTES = 8 * 1024 * 1024
# Code that turns pinned source bytes into the document; any edit is a new cache key.
DERIVATION_CODE = ("p09e_research_catalog.py", "packed_xml.py", "destructible_catalog.py")
_DEFAULT = object()


class ResearchCatalogError(ValueError):
    """A pinned source or supported assembly contract failed verification."""


def require(condition, message):
    if not condition:
        raise ResearchCatalogError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def children(node):
    if isinstance(node, dict) and "children" in node:
        return [(row["name"], row["data"]) for row in node["children"]]
    return []


def child(node, key, default=None):
    values = [data for name, data in children(node) if name == key]
    require(len(values) <= 1, "duplicate source field: " + key)
    return values[0] if values else default


def scalar(node):
    if isinstance(node, dict) and "children" in node:
        return scalar(node["value"])
    if isinstance(node, dict) and set(node) == {"base64"}:
        # Packed XML kind5 is its asString base64 spelling, not decoded text.
        return node["base64"]
    return node


def number(node, label, multiplier=1):
    value = scalar(node)
    require(type(value) in (int, float, str), "missing/non-numeric source " + label)
    try:
        parsed = Decimal(str(value)) * multiplier
    except InvalidOperation as error:
        raise ResearchCatalogError("invalid source number: " + label) from error
    require(parsed.is_finite() and 0 <= parsed <= 2**31 - 1 and parsed == int(parsed),
            "non-integral/out-of-range source " + label)
    return int(parsed)


def price(node):
    require(node is not None, "missing historical price")
    return {"amount": number(node, "price"),
            "currency": "gold" if child(node, "gold") is not None else "credits"}


def identifier(kind, nation, name):
    require(nation in NATIONS and type(name) is str and NAME.fullmatch(name), "invalid resource ID")
    return ("vehicle:" + nation + ":" + name if kind == "vehicle"
            else "module:" + nation + ":" + kind + ":" + name)


@dataclass(frozen=True)
class Catalog:
    document: dict
    # [exact marshal snapshot of document, its canonical SHA-256]; see sha256.
    _digest: list = field(default_factory=list, init=False, repr=False, compare=False)

    @property
    def vehicles(self): return self.document["vehicles"]
    @property
    def modules(self): return self.document["modules"]
    @property
    def unlocks(self): return self.document["unlocks"]
    @property
    def initial_unlocked(self): return self.document["initial_unlocked"]
    @property
    def sha256(self):
        """Canonical document digest, recomputed whenever the document may differ.

        The memo is reused only while ``marshal`` bytes of the live document equal
        the snapshot taken with the digest. Equal bytes mean the same values, types
        and order, hence the same canonical JSON; any mutation recomputes.
        """
        try: snapshot = marshal.dumps(self.document)
        except ValueError: snapshot = None
        if snapshot is not None and self._digest and self._digest[0] == snapshot:
            return self._digest[1]
        digest = hashlib.sha256(canonical(self.document)).hexdigest()
        self._digest[:] = [] if snapshot is None else [snapshot, digest]
        return digest
    @property
    def audit(self):
        return {"schema": "p09e-catalog-audit.v1", "target": TARGET,
                "catalog_sha256": self.sha256, "vehicles": len(self.vehicles),
                "modules": len(self.modules), "unlock_records": len(self.unlocks),
                "acquisition_allowed": sum(v["acquisition_allowed"] for v in self.vehicles.values()),
                "unsupported_assemblies": {k: v["unsupported_reason"] for k, v in self.vehicles.items()
                                            if v["unsupported_reason"]},
                "sources": self.document["sources"],
                "classification": "VERIFIED_STATIC_PINNED_SOURCE",
                "native_ui": "NOT_RUN", "native_index_readback": "NOT_RUN",
                "battle_eligibility": "NOT_GRANTED_BY_CATALOGUE"}


def load_catalog(original_root, manifest_path=PIN_PATH, cache_dir=_DEFAULT):
    """Load exact local sources; caller must use the owner-authorized original root.

    ``manifest_path`` is a developer-controlled pin manifest, never request input.
    All reads are bounded, reject links, and rechecked after extraction.
    ``cache_dir`` (default: ``local/cache/...`` when ``local/`` exists; ``None``
    disables) may hold the derived document. A cached document is used only after
    every pinned source it was derived from passes the same size/SHA-256/link checks.
    """
    if cache_dir is _DEFAULT:
        cache_dir = CACHE_DIR if CACHE_DIR.parent.parent.is_dir() else None
    try:
        return _load_catalog(original_root, manifest_path, cache_dir)
    except ResearchCatalogError:
        raise
    except (OSError, ValueError, KeyError, TypeError, OverflowError) as error:
        raise ResearchCatalogError("catalogue source verification failed: " + str(error)) from error


def _load_catalog(original_root, manifest_path, cache_dir):
    root = no_links(original_root).resolve(strict=True)
    require(root.is_dir(), "original root must be a directory")
    # read() applies no_links to its path first.
    manifest = read(manifest_path, 256 * 1024)
    pins = json_value(manifest, limit=256 * 1024, nodes=6000, depth=8)
    require(pins.get("schema") == "p09e-source-pins.v1" and pins.get("target") == TARGET,
            "wrong source pin manifest")
    source_pins = pins["sources"]
    require(type(source_pins) is dict and 1 <= len(source_pins) <= 512, "source count")
    path = _cache_path(cache_dir, root, manifest)
    cached = _cached_catalog(path, root, source_pins)
    if cached is not None:
        return cached
    result = _build_catalog(root, source_pins)
    _store_cache(path, result)
    return result


def _build_catalog(root, source_pins):
    cache, sources, total = {}, {}, 0

    def source(relative):
        nonlocal total
        require(relative in source_pins and ".." not in relative.split("/"), "unlisted source")
        if relative not in cache:
            pin = source_pins[relative]
            require(type(pin["bytes"]) is int and 0 < pin["bytes"] <= MAX_SOURCE_BYTES, "source size")
            raw = read(root / relative, pin["bytes"], pin["sha256"])
            require(len(raw) == pin["bytes"], "source length changed")
            total += len(raw)
            require(total <= MAX_TOTAL_BYTES, "total source bound")
            cache[relative] = decode(raw, max_bytes=MAX_SOURCE_BYTES, max_depth=48, max_nodes=50000) if relative.endswith(".xml") else raw
            sources[relative] = dict(pin)
        return cache[relative]

    # Pin the algorithms and category/nation ordering used by this independent adapter.
    for relative in ("res/scripts/common/items/vehicles.pyc", "res/scripts/common/items/__init__.pyc", "res/scripts/common/nations.pyc"):
        source(relative)
    vehicles, modules, unlocks = {}, {}, []
    for nation_id, nation in enumerate(NATIONS):
        prefix = "res/scripts/item_defs/vehicles/" + nation + "/"
        listing = source(prefix + "list.xml")
        catalogues = {kind: source(prefix + "components/" + filename + ".xml")
                      for kind, (_, filename) in KINDS.items()}
        ids = {kind: {name: number(value, "component ID") for name, value in children(child(data, "ids"))}
               for kind, data in catalogues.items()}
        for kind, values in ids.items():
            require(len(values) == len(set(values.values())), "duplicate native component ID")
            require(len(values) <= 4096 and all(value <= 65535 for value in values.values()), "native component ID bound")
        vehicle_ids = {name: number(child(row, "id"), "vehicle ID") for name, row in children(listing)}
        require(len(vehicle_ids) == len(set(vehicle_ids.values())), "duplicate native vehicle ID")

        for name, info in children(listing):
            vehicle_id = identifier("vehicle", nation, name)
            require(vehicle_ids[name] <= 255, "vehicle native byte ID")
            path = prefix + name.lower() + ".xml"
            raw = source(path)
            defaults, compatible, masses, loads, powers = {}, {}, {}, {}, {}
            gun_turrets, gun_parameters, turret_guns, turret_hp = {}, {}, {}, {}
            raw_unlocks, default_unlocks = [], []
            position_choices = []

            def collect_unlocks(section, prerequisites=()):
                for target_kind, target in children(child(section, "unlocks")):
                    require(target_kind in {*KINDS, "vehicle"}, "unknown unlock kind")
                    key = scalar(target)
                    target_id = identifier(target_kind, nation, key)
                    require((key in vehicle_ids if target_kind == "vehicle" else key in ids[target_kind]), "unknown unlock target")
                    raw_unlocks.append({"vehicle_id": vehicle_id, "item_id": target_id,
                                        "native_index": len(raw_unlocks),
                                        "historical_xp": number(child(target, "cost"), "unlock XP"),
                                        "prerequisite_ids": list(prerequisites)})

            def installable(kind, key, local, turret_id=None):
                require(key in ids[kind], "module absent from source ID table")
                module_id = identifier(kind, nation, key)
                shared = scalar(local) == "shared"
                base = child(child(catalogues[kind], "shared"), key) if shared else local
                require(base is not None, "shared module missing")
                # Native local readers do not override mass, price, engine power or load.
                base_mass = number(child(base, "weight"), "module weight", 1000)
                row = {"module_id": module_id, "kind": kind, "resource_name": key,
                       "native_compact_id": (ids[kind][key] << 8) + (nation_id << 4) + KINDS[kind][0],
                       "historical_price": price(child(base, "price")), "mass_grams": base_mass,
                       "max_load_grams": number(child(base, "maxLoad"), "max load", 1000) if kind == "chassis" else None,
                       "power_hp": number(child(base, "power"), "engine power") if kind == "engine" else None}
                if module_id in modules:
                    require(modules[module_id] == row, "conflicting global module facts: " + module_id)
                else:
                    modules[module_id] = row
                if module_id not in compatible.setdefault(kind, []): compatible[kind].append(module_id)
                masses[module_id] = base_mass
                if row["max_load_grams"] is not None: loads[module_id] = row["max_load_grams"]
                if row["power_hp"] is not None: powers[module_id] = row["power_hp"]
                if kind == "gun":
                    gun_turrets.setdefault(module_id, []).append(turret_id)
                    turret_guns.setdefault(turret_id, []).append(module_id)
                    # Parameters are turret-specific; never collapse a shared gun's reload overrides.
                    fields = {}
                    for field in ("reloadTime", "aimingTime", "shotDispersionRadius", "maxAmmo", "clip", "burst"):
                        value = child(local, field, child(base, field))
                        if value is not None:
                            fields[field] = _fact(value)
                    gun_parameters[turret_id + "/" + module_id] = fields
                if kind == "turret":
                    turret_hp[module_id] = number(child(base, "maxHealth"), "turret max HP")
                    gun_section = child(local, "guns", child(base, "guns"))
                    require(gun_section is not None, "turret guns missing")
                    for gun_key, gun in children(gun_section): installable("gun", gun_key, gun, module_id)
                # Shared descriptors are cached with no unlock list. Only local override appends.
                req = (module_id, turret_id) if kind == "gun" and shared else (module_id,)
                collect_unlocks(local, tuple(x for x in req if x))
                return module_id

            collect_unlocks(raw)
            for kind, branch in (("chassis", "chassis"), ("engine", "engines"),
                                 ("fuelTank", "fuelTanks"), ("radio", "radios")):
                entries = children(child(raw, branch))
                require(entries and len(entries) <= 64, "missing/excessive installable source branch")
                for key, local in entries: installable(kind, key, local)
                defaults[kind] = compatible[kind][0]
                default_unlocks.append(defaults[kind])
            turret_positions = children(child(child(raw, "hull"), "turretPositions"))
            require(1 <= len(turret_positions) <= 8, "turret positions outside bound")
            for pos in range(len(turret_positions)):
                entries = children(child(raw, "turrets" + str(pos)))
                require(entries, "missing turret position definition")
                choice = [installable("turret", key, local) for key, local in entries]
                position_choices.append(choice)
                default_unlocks += [choice[0], turret_guns[choice[0]][0]]
            defaults["turret"] = position_choices[0][0]
            defaults["gun"] = turret_guns[defaults["turret"]][0]
            fake = scalar(child(child(child(raw, "hull"), "fakeTurrets"), "lobby", ""))
            if fake is not None and fake != "":
                require(type(fake) in (str, int), "unsupported fake turret list")
                for token in str(fake).split():
                    index = number(token, "fake turret index")
                    require(index < len(position_choices), "fake turret index out of range")
                    default_unlocks += position_choices[index][1:]
            require(len(raw_unlocks) <= 512, "unlock count bound")
            requirements = {}
            for row in raw_unlocks:
                if row["item_id"].startswith("module:"):
                    require(row["item_id"] in masses, "unlock targets incompatible component")
                requirements.setdefault(row["item_id"], set()).update(row["prerequisite_ids"])

            def ancestors(item, visiting=()):
                require(item not in visiting and len(visiting) <= 64, "research cycle/depth")
                result = set(requirements.get(item, ()))
                for required in tuple(result): result.update(ancestors(required, visiting + (item,)))
                return result

            for row in raw_unlocks:
                row["prerequisite_ids"] = sorted(ancestors(row["item_id"]))
                unlocks.append(row)
            tags = scalar(child(info, "tags")).split()
            crew_roles = []
            valid_roles = {"commander", "gunner", "driver", "radioman", "loader"}
            for role, section in children(child(raw, "crew")):
                extras = scalar(section)
                require(role in valid_roles and type(extras) is str, "crew role source shape")
                roles = [role] + extras.split()
                require(all(extra in valid_roles - {role, "commander"} for extra in roles[1:]), "crew secondary role")
                crew_roles.append(roles)
            require(1 <= len(crew_roles) <= 8 and sum(row[0] == "commander" for row in crew_roles) == 1,
                    "crew slot/commander count")
            historical_price = price(child(info, "price"))
            not_in_shop = scalar(child(info, "notInShop", False))
            require(type(not_in_shop) is bool, "non-boolean notInShop")
            unsupported = "multiple turret positions require dedicated installation adapter" if len(position_choices) != 1 else None
            acquisition = not (not_in_shop or set(tags) & {"secret", "observer", "event_battles", "special"} or historical_price["currency"] != "credits" or unsupported)
            vehicles[vehicle_id] = {"vehicle_id": vehicle_id, "resource_name": name,
                "native_compact_id": (vehicle_ids[name] << 8) + (nation_id << 4) + 1,
                "nation_id": nation_id, "nation": nation, "tier": number(child(info, "level"), "tier"),
                "tags": tags, "not_in_shop": not_in_shop, "historical_price": historical_price,
                "acquisition_allowed": acquisition, "unsupported_reason": unsupported,
                "defaults": defaults, "default_unlocks": sorted(set(default_unlocks)), "compatible": compatible,
                "gun_turrets": {key: sorted(set(value)) for key, value in gun_turrets.items()},
                "turret_guns": turret_guns, "turret_positions": position_choices,
                "hull_mass_grams": number(child(child(raw, "hull"), "weight"), "hull weight", 1000),
                "hull_max_hp": number(child(child(raw, "hull"), "maxHealth"), "hull max HP"),
                "turret_max_hp": turret_hp, "crew_roles": crew_roles,
                "module_mass_grams": masses, "module_max_load_grams": loads, "module_power_hp": powers,
                "gun_parameters": gun_parameters, "source": path,
                "battle_eligibility": "UNSUPPORTED_UNTIL_EXACT_RUNTIME_PROFILE"}
    require(len(vehicles) == 374, "pinned source vehicle coverage differs")
    for row in unlocks:
        require(row["item_id"] in vehicles or row["item_id"] in modules, "unknown target")
    initial = []
    for key, row in vehicles.items():
        if row["tier"] == 1 and row["acquisition_allowed"]:
            initial += [key] + row["default_unlocks"]
    # Recheck every source; immutable output may be used beyond this read operation.
    _verify_sources(root, sources)
    return Catalog({"schema": SCHEMA, "target": TARGET, "vehicles": vehicles, "modules": modules,
                    "unlocks": unlocks, "initial_unlocked": sorted(set(initial)),
                    "initial_unlock_policy": "test_lab-visible-credit-tier1-and-native-defaults.v1",
                    "sources": sources})


def _verify_sources(root, sources):
    """Bounded, link-free, exact-size and SHA-256 read of every listed source."""
    total = 0
    for relative, pin in sources.items():
        require(".." not in relative.split("/"), "unlisted source")
        require(type(pin["bytes"]) is int and 0 < pin["bytes"] <= MAX_SOURCE_BYTES, "source size")
        total += pin["bytes"]
        require(total <= MAX_TOTAL_BYTES, "total source bound")
        require(len(read(root / relative, pin["bytes"], pin["sha256"])) == pin["bytes"], "source changed")


def _cache_path(cache_dir, root, manifest):
    """Cache file named by everything the derived document depends on, or None."""
    if cache_dir is None:
        return None
    code = {name: hashlib.sha256(read(Path(__file__).with_name(name), 1024 * 1024)).hexdigest()
            for name in DERIVATION_CODE}
    key = hashlib.sha256(canonical({"cache": CACHE_SCHEMA, "schema": SCHEMA, "target": TARGET,
        "manifest_sha256": hashlib.sha256(manifest).hexdigest(), "code": code,
        "original_root": str(root), "python": sys.implementation.name + " " + sys.version})).hexdigest()
    try:
        return no_links(Path(cache_dir) / (key + ".json"))
    except CatalogError:
        return None  # a linked cache location is never read or written


def _cached_catalog(path, root, source_pins):
    """Return the verified cached catalogue, or None to rebuild from sources.

    Unreadable, malformed or mismatching cache files are a miss, never a result.
    Changed pinned sources raise exactly as the full build's final recheck does.
    """
    if path is None or not path.is_file():
        return None
    try:
        raw = read(path, MAX_CACHE_BYTES)
        header, separator, body = raw.partition(b"\n")
        meta = json_value(header, limit=4096, nodes=16, depth=2)
        if (not separator or type(meta) is not dict or meta.get("cache") != CACHE_SCHEMA
                or meta.get("key") != path.stem
                or meta.get("document_sha256") != hashlib.sha256(body).hexdigest()):
            return None
        document = json_value(body, limit=MAX_CACHE_BYTES, nodes=200000, depth=16)
        if type(document) is not dict or document.get("schema") != SCHEMA or document.get("target") != TARGET:
            return None
        catalog = Catalog(document)
        sources = document["sources"]
        if (catalog.sha256 != meta.get("catalog_sha256") or type(sources) is not dict or not sources
                or any(relative not in source_pins or source_pins[relative] != pin
                       for relative, pin in sources.items())):
            return None
    except (CatalogError, OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
    _verify_sources(root, sources)
    return catalog


def _store_cache(path, catalog):
    """Best effort: a failed write only means the next load rebuilds from sources."""
    if path is None:
        return
    # Insertion order is kept (no sort_keys): consumers iterate these mappings.
    body = json.dumps(catalog.document, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii")
    header = canonical({"cache": CACHE_SCHEMA, "key": path.stem, "catalog_sha256": catalog.sha256,
                        "document_sha256": hashlib.sha256(body).hexdigest()})
    if len(header) + 1 + len(body) > MAX_CACHE_BYTES:
        return
    temp = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        no_links(path.parent)
        handle, temp = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=path.parent)
        with os.fdopen(handle, "wb") as stream:
            stream.write(header + b"\n" + body)
        os.replace(temp, path)
        temp = None
    except (OSError, CatalogError):
        pass  # concurrent writer or read-only local/: the returned result is already verified
    finally:
        if temp is not None:
            try: os.unlink(temp)
            except OSError: pass


def _fact(node):
    """Copy only a small numeric parameter subtree as inert primitive facts."""
    pairs = children(node)
    if pairs:
        require(len(pairs) <= 16 and len({k for k, _ in pairs}) == len(pairs), "parameter shape")
        return {key: _fact(value) for key, value in pairs}
    value = scalar(node)
    require(type(value) in (int, float, str), "parameter scalar type")
    require(len(str(value)) <= 128, "parameter scalar length")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", required=True)
    parser.add_argument("--out", required=True, help="new private evidence directory")
    args = parser.parse_args()
    result = load_catalog(args.original)
    out = Path(args.out).resolve()
    allowed = Path(__file__).resolve().parents[1] / "local" / "evidence"
    require(out.is_relative_to(allowed.resolve()), "output must remain in worktree local/evidence")
    out.mkdir(parents=True, exist_ok=False)
    (out / "catalog.json").write_bytes(canonical(result.document) + b"\n")
    (out / "audit.json").write_bytes(canonical(result.audit) + b"\n")
    print(json.dumps({key: value for key, value in result.audit.items() if key != "sources"}))


if __name__ == "__main__": main()
