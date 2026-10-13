"""Source-bound #717 ammunition catalogue for the isolated P09C domain service.

Native IDs stay here, in a compatibility adapter; commands use domain IDs.
The audit reads nine exact local original resources, never executes bytecode,
and never claims native IS-7 ammunition delivery or historical purchase prices.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

if __package__:
    from .destructible_catalog import CatalogError, no_links, read
    from .packed_xml import FormatError, decode, walk
    from .py27_static import MarshalError, parse_pyc, records
else:
    from destructible_catalog import CatalogError, no_links, read
    from packed_xml import FormatError, decode, walk
    from py27_static import MarshalError, parse_pyc, records


SCHEMA = "p09c-ammo-catalog.v1"
AUDIT_SCHEMA = "p09c-ammo-source-audit.v1"
TARGET = "v.0.9.1 #717 RU"
ROOT = Path(__file__).resolve().parents[1]
MAX_SOURCE_BYTES = 1024 * 1024
XML_PREFIX = "res/scripts/item_defs/vehicles/ussr/"
ITEMS_PATH = "res/scripts/common/items/__init__.pyc"
VEHICLES_PATH = "res/scripts/common/items/vehicles.pyc"
NATIONS_PATH = "res/scripts/common/nations.pyc"


class AmmoCatalogError(ValueError):
    """Source files or the explicit audit destination violate the contract."""


@dataclass(frozen=True)
class Shell:
    shell_id: str
    resource_name: str
    kind: str
    item_id: int
    native_compact_id: int


@dataclass(frozen=True)
class Mount:
    mount_id: str
    vehicle_definition_id: str
    vehicle_resource_name: str
    vehicle_native_compact_id: int
    turret_resource_name: str
    turret_native_compact_id: int
    gun_resource_name: str
    gun_native_compact_id: int
    capacity: int
    shell_ids: tuple[str, ...]


@dataclass(frozen=True)
class SourcePin:
    size: int
    sha256: str


SHELLS: Mapping[str, Shell] = MappingProxyType({s.shell_id: s for s in (
    Shell("shell:ms1-stock-ap", "_37mm_UBRT1", "ARMOR_PIERCING", 10, 2570),
    Shell("shell:ms1-stock-heat", "_37mm_BPT1", "HOLLOW_CHARGE", 11, 2826),
    Shell("shell:ms1-stock-he", "_37mm_UOT1", "HIGH_EXPLOSIVE", 12, 3082),
    Shell("shell:is7-stock-ap", "_130mm_UBR-482", "ARMOR_PIERCING", 57, 14602),
    Shell("shell:is7-stock-apcr", "_130mm_UBR-482P", "ARMOR_PIERCING_CR", 58, 14858),
    Shell("shell:is7-stock-he", "_130mm_UOF-482", "HIGH_EXPLOSIVE", 59, 15114),
)})

MOUNTS: Mapping[str, Mount] = MappingProxyType({m.mount_id: m for m in (
    Mount("ms1-stock", "vehicle:ms1", "MS-1", 3329,
          "T-18_Standart", 5891, "_37mm_Gochkins", 5892, 96,
          ("shell:ms1-stock-ap", "shell:ms1-stock-heat", "shell:ms1-stock-he")),
    Mount("is7-stock", "vehicle:is7", "IS-7", 7169,
          "IS-7", 12035, "_130mm_S-70", 14852, 30,
          ("shell:is7-stock-ap", "shell:is7-stock-apcr", "shell:is7-stock-he")),
)})

SOURCE_PINS: Mapping[str, SourcePin] = MappingProxyType({
    XML_PREFIX + "list.xml": SourcePin(18228, "167a637d725a233d42e52bd7d5bac00b9af45c0ef225163ab578e202454f5138"),
    XML_PREFIX + "ms-1.xml": SourcePin(11839, "a494bf04d29da7d066fd6923dbb75a79b947559a52405298c494a943c4b0c535"),
    XML_PREFIX + "is-7.xml": SourcePin(5809, "8d55fa4657a88f1436cd164afe11bade875a906fa7b97256f1fb2f803b09c10d"),
    XML_PREFIX + "components/turrets.xml": SourcePin(2501, "2a5927fc6bd030056c25fdca4cf70543b001560d03274b0661389ed2e80c5537"),
    XML_PREFIX + "components/guns.xml": SourcePin(58493, "889fe1564987566478c474ddfef21cbc7742d23bebd19f6a200c59bfafd7d87b"),
    XML_PREFIX + "components/shells.xml": SourcePin(20468, "ed301edbe07a72b04dc6c6d799bc563de55d0d1f26bd35798354a9f6769e7a96"),
    ITEMS_PATH: SourcePin(4303, "587ba137fee1b7de77ce81d5e963185ba20267c54d157ce8699a76f2f0d11176"),
    VEHICLES_PATH: SourcePin(125668, "805240e4b59d8a75950dbb97b41c17867606e7e96d7ff0c8d7b05312b83ae8b6"),
    NATIONS_PATH: SourcePin(565, "34392915b0d2a70a3df0b8151e0fdbb9cb58aad6a708ffc85843c45c596a4562"),
})


def catalog_document() -> dict:
    """Detached JSON-compatible catalogue; callers cannot mutate the constants."""
    return {"schema": SCHEMA, "target": TARGET,
            "mounts": {key: asdict(value) for key, value in MOUNTS.items()},
            "shells": {key: asdict(value) for key, value in SHELLS.items()},
            "sources": {key: asdict(value) for key, value in SOURCE_PINS.items()},
            "prices": "UNSUPPORTED", "native_is7_ammo": "NOT_RUN"}


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


CATALOG_SHA256 = hashlib.sha256(_canonical(catalog_document())).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AmmoCatalogError(message)


def _field(values: Mapping, path: str, expected: object) -> None:
    actual = values.get(path)
    _require(type(actual) is type(expected) and actual == expected,
             "original source field differs: " + path)


def _validate_fields(xml: Mapping[str, Mapping]) -> list[dict]:
    """Validate exact mount overrides and ordered shared shot membership."""
    result = []
    vehicle_list = xml["list.xml"]
    guns, turrets, shells = (xml["components/" + name + ".xml"]
                             for name in ("guns", "turrets", "shells"))
    for mount in MOUNTS.values():
        vehicle = xml[mount.vehicle_resource_name.lower() + ".xml"]
        turret = mount.turret_resource_name
        gun = mount.gun_resource_name
        mount_path = f"/turrets0[1]/{turret}[1]/guns[1]/{gun}[1]"
        shots_path = f"/shared[1]/{gun}[1]/shots[1]"
        _field(vehicle_list, f"/{mount.vehicle_resource_name}[1]/id[1]",
               mount.vehicle_native_compact_id >> 8)
        _field(turrets, f"/ids[1]/{turret}[1]", mount.turret_native_compact_id >> 8)
        _field(guns, f"/ids[1]/{gun}[1]", mount.gun_native_compact_id >> 8)
        for compact_id, item_type in ((mount.vehicle_native_compact_id, 1),
                                      (mount.turret_native_compact_id, 3),
                                      (mount.gun_native_compact_id, 4)):
            _require(compact_id & 255 == item_type,
                     "mount compact ID differs from pinned nation/item type")
        _field(vehicle, mount_path, "shared")
        _field(vehicle, mount_path + "/maxAmmo[1]", mount.capacity)
        # An override to shots would invalidate this shared-source catalogue.
        _require(not any(path.startswith(mount_path + "/shots[") for path in vehicle),
                 "vehicle overrides shared shot compatibility")
        ordered_shots = [path[len(shots_path) + 1:-3] for path in guns
                         if path.startswith(shots_path + "/")
                         and "/" not in path[len(shots_path) + 1:]]
        expected_shots = [SHELLS[key].resource_name for key in mount.shell_ids]
        _require(ordered_shots == expected_shots, "ordered original shots differ")
        for shell_id in mount.shell_ids:
            shell = SHELLS[shell_id]
            _field(shells, f"/{shell.resource_name}[1]/id[1]", shell.item_id)
            _field(shells, f"/{shell.resource_name}[1]/kind[1]", shell.kind)
            _require(shell.native_compact_id == (shell.item_id << 8) + 10,
                     "shell compact ID differs from pinned encoder")
        result.append({"mount_id": mount.mount_id, "capacity": mount.capacity,
                       "capacity_node": mount_path + "/maxAmmo[1]",
                       "shots_node": shots_path, "shell_ids": list(mount.shell_ids),
                       "classification": "VERIFIED_STATIC_ORIGINAL_717"})
    return result


def _validate_encoding(sources: Mapping[str, bytes]) -> dict:
    # Bounded parser returns inert records, never Python code objects.
    items = parse_pyc(sources[ITEMS_PATH])
    type_names = [b"reserved", b"vehicle", b"vehicleChassis", b"vehicleTurret",
                  b"vehicleGun", b"vehicleEngine", b"vehicleFuelTank", b"vehicleRadio",
                  b"tankman", b"optionalDevice", b"shell", b"equipment"]
    _require(type_names in items["consts"] and b"ITEM_TYPE_NAMES" in items["names"],
             "original item type list differs")
    nations = parse_pyc(sources[NATIONS_PATH])
    nation_names = [b"ussr", b"germany", b"usa", b"china", b"france", b"uk", b"japan"]
    _require(nation_names in nations["consts"] and b"NAMES" in nations["names"],
             "original nation order differs")
    matching = [record for name, record in records(parse_pyc(sources[VEHICLES_PATH]))
                if name == "<module>.makeIntCompactDescrByID"]
    _require(len(matching) == 1, "original compact encoder missing/duplicated")
    record = matching[0]
    # LOAD_GLOBAL items / LOAD_ATTR ITEM_TYPES / index itemTypeName;
    # add nationID << 4, then itemID << 8. Hash the record without embedding
    # original client bytecode in this repository.
    _require(record["firstlineno"] == 2708 and record["argcount"] == 3
             and record["varnames"] == [b"itemTypeName", b"nationID", b"itemID", b"header"]
             and record["consts"] == [None, 4, 8]
             and record["names"] == [b"items", b"ITEM_TYPES"]
             and hashlib.sha256(record["code"]).hexdigest()
             == "00d04a6b4859de88a86d352887866a0947dfe6d6b35a105c2d6f17e71a484ee8",
             "original compact encoder differs")
    return {"classification": "VERIFIED_STATIC_ORIGINAL_717", "nation_id": 0,
            "item_type_ids": {"vehicle": 1, "vehicleTurret": 3, "vehicleGun": 4, "shell": 10},
            "encoder": "makeIntCompactDescrByID", "source_line": 2708,
            "formula": "(itemID << 8) + (nationID << 4) + itemTypeID",
            "client_bytecode_executed": False}


def audit_sources(original_root: Path | str) -> dict:
    """Activate only this exact catalogue against an explicitly supplied root."""
    root = Path(original_root)
    _require(root.is_absolute(), "explicit absolute original root required")
    try:
        root = no_links(root).resolve(strict=True)
        _require(root.is_dir(), "original root must be a directory")
        sources = {}
        for relative, pin in SOURCE_PINS.items():
            raw = read(root / relative, min(MAX_SOURCE_BYTES, pin.size), pin.sha256)
            _require(len(raw) == pin.size, "original source size differs: " + relative)
            sources[relative] = raw
        xml = {relative[len(XML_PREFIX):]: dict(walk(decode(raw, max_bytes=MAX_SOURCE_BYTES,
                                                       max_depth=32, max_nodes=50000)))
               for relative, raw in sources.items() if relative.endswith(".xml")}
        mounts = _validate_fields(xml)
        encoding = _validate_encoding(sources)
    except (CatalogError, FormatError, MarshalError, OSError, KeyError, UnicodeError) as error:
        raise AmmoCatalogError("original source audit failed: " + str(error)) from error
    return {"schema": AUDIT_SCHEMA, "status": "PASS_P09C_AMMO_SOURCE_AUDIT",
            "catalog_sha256": CATALOG_SHA256, "target": TARGET,
            "original_root": str(root),
            "sources": {key: asdict(pin) for key, pin in SOURCE_PINS.items()},
            "mounts": mounts, "compact_encoding": encoding,
            "native_is7_ammunition": "NOT_RUN", "runtime_wiring": "NOT_RUN",
            "historical_purchase_prices": "UNKNOWN_UNSUPPORTED"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path,
                        help="Fresh directory inside this worktree's local/evidence")
    args = parser.parse_args(argv)
    try:
        out = no_links(args.out)
        allowed = no_links(ROOT / "local/evidence")
        _require(out.is_relative_to(allowed) and out != allowed,
                 "audit output must be inside this worktree local/evidence")
        _require(not out.exists(), "audit output already exists")
        receipt = audit_sources(args.original_root)
        out.mkdir(parents=True, exist_ok=False)
        with (out / "receipt.json").open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(receipt, indent=2, ensure_ascii=True) + "\n")
        print(json.dumps({"status": receipt["status"], "catalog_sha256": CATALOG_SHA256,
                          "receipt": str(out / "receipt.json")}))
        return 0
    except (AmmoCatalogError, CatalogError, OSError) as error:
        parser.exit(1, "P09C source audit rejected: " + str(error) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
