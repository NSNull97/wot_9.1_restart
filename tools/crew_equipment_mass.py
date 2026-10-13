"""P04C bounded mass authority for two exact #717 mounted assemblies.

The source auditor reuses the established inert XML/bytecode readers. It does
not import a second content catalogue, execute client code, infer a loadout
from vehicle name alone, or activate this configuration on a live account.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sys
from types import MappingProxyType

ROOT = Path(__file__).resolve().parents[1]
if not __package__:
    sys.path.insert(0, str(ROOT))

from server.domain.crew_equipment import MassBudget, canonical
from tools.crew_equipment_source_audit import SOURCE_BUILD, SOURCE_MANIFEST
from tools.destructible_catalog import CatalogError, json_value, no_links, read
from tools.packed_xml import FormatError, decode, walk
from tools.py27_static import MarshalError, parse_pyc, records


FORMAT = "mounted-assembly.717.v1"
AUDIT_FORMAT = "mounted-assembly-mass-audit.717.v1"
XML_PREFIX = "res/scripts/item_defs/vehicles/ussr/"
VEHICLES_PATH = "res/scripts/common/items/vehicles.pyc"
ITEMS_PATH = "res/scripts/common/items/__init__.pyc"
SOURCE_PINS = MappingProxyType({
    XML_PREFIX + "list.xml": (18228, "167a637d725a233d42e52bd7d5bac00b9af45c0ef225163ab578e202454f5138"),
    XML_PREFIX + "ms-1.xml": (11839, "a494bf04d29da7d066fd6923dbb75a79b947559a52405298c494a943c4b0c535"),
    XML_PREFIX + "is-7.xml": (5809, "8d55fa4657a88f1436cd164afe11bade875a906fa7b97256f1fb2f803b09c10d"),
    XML_PREFIX + "components/chassis.xml": (2850, "37f8abc432f36e789dcacbeb12e15c8d56f6c21c3a8d717d87c5e23d070c8618"),
    XML_PREFIX + "components/engines.xml": (16153, "196e52561bd04d2d4e5838442f62704456f4b901627248e04b2c9bd37d32f60d"),
    XML_PREFIX + "components/fuelTanks.xml": (457, "1f182b76fceeabf2ff1d828cc5b2aea37b94585f78488bd2dd7c195f8862b013"),
    XML_PREFIX + "components/radios.xml": (3986, "099292b8b5f5e250b2cd506419d18620f4f2504950776b54983bc303b2ca201a"),
    XML_PREFIX + "components/turrets.xml": (2501, "2a5927fc6bd030056c25fdca4cf70543b001560d03274b0661389ed2e80c5537"),
    XML_PREFIX + "components/guns.xml": (58493, "889fe1564987566478c474ddfef21cbc7742d23bebd19f6a200c59bfafd7d87b"),
    VEHICLES_PATH: (125668, "805240e4b59d8a75950dbb97b41c17867606e7e96d7ff0c8d7b05312b83ae8b6"),
    ITEMS_PATH: (4303, "587ba137fee1b7de77ce81d5e963185ba20267c54d157ce8699a76f2f0d11176"),
})
NATIVE_PINS = MappingProxyType({
    "ms1-stock": ("server/native-descriptors.json", 1390, "18e6c2babfc205ce80fa24c2c9f23385a1731233c4d504be369638485652d6f2"),
    "is7-stock": ("server/native-is7-descriptors.json", 1290, "4b24a59c5344808018caf438c044d31d86cf1da20c8b2cbd58f93b8ab2f859b1"),
})


class MassSourceError(ValueError):
    """Unverified source or unsupported full mounted assembly."""


def _require(value, message):
    if not value:
        raise MassSourceError(message)


def _same(actual, expected, label):
    _require(type(actual) is type(expected) and actual == expected, label + ": source differs")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class AssemblySpec:
    mount_id: str
    vehicle_definition_id: str
    vehicle_name: str
    vehicle_source_id: int
    compact_descr_hex: str
    hull_kg: int
    max_load_kg: int
    # role, resource name, item type, source ID, mass kg, shared source filename
    components: tuple[tuple[str, str, int, int, int, str], ...]


ASSEMBLIES = (
    AssemblySpec("ms1-stock", "vehicle:ms1", "MS-1", 13,
                 "010d1a000e00c90000001700170000", 2750, 4890, (
                     ("chassis", "T-18", 2, 26, 1200, "chassis.xml"),
                     ("engine", "MS-1", 5, 14, 266, "engines.xml"),
                     ("fuelTank", "Small", 6, 201, 200, "fuelTanks.xml"),
                     ("radio", "Alarm_flags", 7, 0, 1, "radios.xml"),
                     ("turret", "T-18_Standart", 3, 23, 170, "turrets.xml"),
                     ("gun", "_37mm_Gochkins", 4, 23, 104, "guns.xml"))),
    AssemblySpec("is7-stock", "vehicle:is7", "IS-7", 28,
                 "011c3a002400cd000b002f003a0000", 38850, 70950, (
                     ("chassis", "IS-7", 2, 58, 11000, "chassis.xml"),
                     ("engine", "M-50T", 5, 36, 700, "engines.xml"),
                     ("fuelTank", "Large", 6, 205, 300, "fuelTanks.xml"),
                     ("radio", "_10RK-26", 7, 11, 160, "radios.xml"),
                     ("turret", "IS-7", 3, 47, 14200, "turrets.xml"),
                     ("gun", "_130mm_S-70", 4, 58, 2980, "guns.xml"))),
)


@dataclass(frozen=True)
class VerifiedAssembly:
    """Produced by load_verified_assemblies inside the trusted server boundary.

    This object is not a network credential. Do not accept constructed objects,
    evidence JSON or a MassBudget from a client as source authority.
    """
    canonical_bytes: bytes
    evidence_bytes: bytes

    def __post_init__(self):
        _require(type(self.canonical_bytes) is bytes and type(self.evidence_bytes) is bytes,
                 "immutable canonical bytes required")

    @property
    def component_configuration_sha256(self):
        return _sha(self.canonical_bytes)

    @property
    def sha256(self):
        return self.component_configuration_sha256

    @property
    def evidence_sha256(self):
        return _sha(self.evidence_bytes)

    @property
    def mount_id(self):
        return self.as_dict()["mount_id"]

    @property
    def vehicle_definition_id(self):
        return self.as_dict()["vehicle_definition_id"]

    @property
    def mass_budget(self):
        value = self.as_dict()
        return MassBudget(self.sha256, self.evidence_sha256,
                          value["base_mass_grams"], value["max_load_grams"])

    def as_dict(self):
        return json.loads(self.canonical_bytes)

    def evidence_dict(self):
        return json.loads(self.evidence_bytes)


def _pinned_read(path, pin):
    size, digest = pin
    raw = read(path, size, digest)
    _same(len(raw), size, "source size")
    return raw


def _configured_paths(config_path):
    config = json_value(read(no_links(config_path), 65536).removeprefix(b"\xef\xbb\xbf"),
                        limit=65536, nodes=1024, depth=12)
    _same(config["target"]["exact_build"], SOURCE_BUILD, "client build")
    _same(config["target"]["client_manifest_sha256"], SOURCE_MANIFEST, "client manifest")
    _same(config["target"]["region"], "RU", "client region")
    result = []
    for key in ("original_client_root", "local_artifacts_root"):
        value = config["paths"][key]
        _require(type(value) is str and Path(value).is_absolute(), "configured absolute root required")
        path = no_links(value).resolve(strict=True)
        _require(path.is_dir(), "configured root must be a directory")
        result.append(path)
    return tuple(result)


def _verify_algorithm(sources):
    items = parse_pyc(sources[ITEMS_PATH])
    expected_types = [b"reserved", b"vehicle", b"vehicleChassis", b"vehicleTurret",
                      b"vehicleGun", b"vehicleEngine", b"vehicleFuelTank", b"vehicleRadio",
                      b"tankman", b"optionalDevice", b"shell", b"equipment"]
    _require(expected_types in items["consts"], "native component categories differ")
    methods = dict(records(parse_pyc(sources[VEHICLES_PATH])))
    weight = methods["<module>.VehicleDescr.__computeWeight"]
    _same(weight["firstlineno"], 1432, "native mass method line")
    _same(weight["argcount"], 1, "native mass method arguments")
    _same(_sha(weight["code"]), "4c7e5989b24debcc7a2b421426d706965e6a5c47035323747a1202704f46caf0",
          "native mass algorithm")
    _same(weight["names"], [b"chassis", b"hull", b"engine", b"fuelTank", b"radio",
                            b"turrets", b"optionalDevices", b"None", b"weightOnVehicle"],
          "native mass field references")
    encoder = methods["<module>.makeIntCompactDescrByID"]
    _same(_sha(encoder["code"]), "00d04a6b4859de88a86d352887866a0947dfe6d6b35a105c2d6f17e71a484ee8",
          "native compact encoder")
    return {"method": "VehicleDescr.__computeWeight", "source_line": 1432,
            "method_code_sha256": _sha(weight["code"]),
            "base_formula": "hull+chassis+engine+fuelTank+radio+sum(turret+gun)",
            "base_offsets": [13, 117], "max_load_offsets": [0, 10],
            "optional_devices_excluded": True, "client_bytecode_executed": False}


def _assembly_document(xml, native, spec):
    """Require each mounted source, reference and native ID; no fallback lookup."""
    vehicle_file = spec.vehicle_name.lower() + ".xml"
    vehicle = xml[vehicle_file]
    _same(xml["list.xml"].get(f"/{spec.vehicle_name}[1]/id[1]"),
          spec.vehicle_source_id, "vehicle source ID")
    _same(native["type_name"], "ussr:" + spec.vehicle_name, "native vehicle name")
    _same(native["type_id"], [0, spec.vehicle_source_id], "native vehicle ID")
    _same(native["type_compact_descr"], (spec.vehicle_source_id << 8) + 1, "native vehicle compact ID")
    _same(native["compact_descr_hex"], spec.compact_descr_hex, "native mounted descriptor")
    _same(set(native["components"]), {row[0] for row in spec.components}, "native component coverage")
    _same(vehicle.get("/hull[1]/weight[1]"), spec.hull_kg, "hull mass")
    components = [{"role": "hull", "resource_name": "hull", "mass_grams": spec.hull_kg * 1000,
                   "source_id": XML_PREFIX + vehicle_file, "source_node": "/hull[1]/weight[1]"}]
    turret_name = next(row[1] for row in spec.components if row[0] == "turret")
    chassis_name = next(row[1] for row in spec.components if row[0] == "chassis")
    for role, name, item_type, item_id, kg, component_file in spec.components:
        catalogue = xml["components/" + component_file]
        _same(catalogue.get(f"/ids[1]/{name}[1]"), item_id, "component source ID: " + role)
        _same(native["components"][role], {"id": [0, item_id], "compact_descr": (item_id << 8) + item_type},
              "native component: " + role)
        if role in ("chassis", "turret"):
            branch = "chassis" if role == "chassis" else "turrets0"
            mount_node = f"/{branch}[1]/{name}[1]"
            _same(vehicle.get(mount_node), "", "local component definition")
            mass_file, mass_node = vehicle_file, mount_node + "/weight[1]"
        else:
            branch = {"engine": "engines", "fuelTank": "fuelTanks", "radio": "radios"}.get(role)
            mount_node = (f"/{branch}[1]/{name}[1]" if role != "gun"
                          else f"/turrets0[1]/{turret_name}[1]/guns[1]/{name}[1]")
            _same(vehicle.get(mount_node), "shared", "mounted shared component")
            _require(not any(path.startswith(mount_node + "/weight[") for path in vehicle),
                     "unsupported mounted mass override: " + role)
            mass_file, mass_node = "components/" + component_file, f"/shared[1]/{name}[1]/weight[1]"
        _same(xml[mass_file].get(mass_node), kg, "component mass: " + role)
        if role == "chassis":
            _same(vehicle.get(mount_node + "/maxLoad[1]"), spec.max_load_kg, "chassis max load")
        components.append({"role": role, "resource_name": name, "source_item_id": item_id,
                           "native_compact_id": (item_id << 8) + item_type,
                           "mass_grams": kg * 1000, "source_id": XML_PREFIX + mass_file,
                           "source_node": mass_node, "vehicle_mount_node": mount_node})
    return {"format": FORMAT, "target": SOURCE_BUILD + " RU", "mount_id": spec.mount_id,
            "vehicle_definition_id": spec.vehicle_definition_id,
            "vehicle_native_compact_id": (spec.vehicle_source_id << 8) + 1,
            "native_empty_optional_device_descriptor_hex": spec.compact_descr_hex,
            "components": components, "base_mass_grams": sum(row["mass_grams"] for row in components),
            "max_load_grams": spec.max_load_kg * 1000,
            "max_load_source": {"id": XML_PREFIX + vehicle_file,
                                "node": f"/chassis[1]/{chassis_name}[1]/maxLoad[1]"},
            "arithmetic": "exact-integer-source-kg-to-grams",
            "sources": [{"id": key, "bytes": pin[0], "sha256": pin[1]}
                        for key, pin in sorted(SOURCE_PINS.items())]}


def load_verified_assemblies(config_path: Path | str) -> tuple[VerifiedAssembly, ...]:
    """Read explicit configuration and exact original/native evidence; no writes.

    No caller-supplied module IDs, masses or claimed receipt are accepted. The
    caller must bind this exact assembly SHA to authenticated reserved state.
    """
    try:
        original, local = _configured_paths(config_path)
        sources = {name: _pinned_read(original / name, pin) for name, pin in SOURCE_PINS.items()}
        xml = {name[len(XML_PREFIX):]: dict(walk(decode(raw, max_bytes=1024 * 1024,
                                                       max_depth=32, max_nodes=50000)))
               for name, raw in sources.items() if name.endswith(".xml")}
        algorithm = _verify_algorithm(sources)
        result = []
        for spec in ASSEMBLIES:
            relative, size, digest = NATIVE_PINS[spec.mount_id]
            native = json_value(_pinned_read(local / relative, (size, digest)),
                                limit=65536, nodes=1024, depth=12)
            document = _assembly_document(xml, native["vehicle"], spec)
            raw = canonical(document)
            evidence = {"format": AUDIT_FORMAT, "classification": "VERIFIED_STATIC_SOURCE_717",
                        "assembly": document, "component_configuration_sha256": _sha(raw),
                        "algorithm": algorithm,
                        "native_selection_evidence": {"id": "local/" + relative, "bytes": size,
                                                      "sha256": digest, "classification": "OBSERVED_PINNED_EXPORT"},
                        "native_mass_readback": "NOT_RUN", "runtime_wiring": "NOT_RUN",
                        "live_inventory_grant": "NOT_RUN"}
            result.append(VerifiedAssembly(raw, canonical(evidence)))
        return tuple(result)
    except (CatalogError, FormatError, MarshalError, OSError, KeyError, TypeError, UnicodeError) as error:
        raise MassSourceError("mounted assembly source verification failed: " + str(error)) from error


def select_assembly(assemblies: tuple[VerifiedAssembly, ...], mount_id: str) -> VerifiedAssembly:
    _require(type(mount_id) is str and mount_id in {spec.mount_id for spec in ASSEMBLIES},
             "unsupported mounted assembly")
    matches = [assembly for assembly in assemblies if assembly.mount_id == mount_id]
    _require(len(matches) == 1, "verified assembly missing or duplicated")
    return matches[0]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True,
                        help="Fresh evidence directory inside this worktree local/evidence")
    args = parser.parse_args(argv)
    try:
        out = no_links(args.out)
        allowed = no_links(ROOT / "local/evidence")
        _require(out.is_relative_to(allowed) and out != allowed, "output outside worktree evidence")
        _require(not out.exists(), "fresh evidence directory required")
        assemblies = load_verified_assemblies(args.config)
        report = {"format": AUDIT_FORMAT, "status": "PASS_P04C_MOUNTED_MASS_SOURCE_AUDIT",
                  "assemblies": [{"component_configuration_sha256": item.sha256,
                                  "mass_evidence_sha256": item.evidence_sha256,
                                  "evidence": item.evidence_dict()} for item in assemblies]}
        raw = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("ascii")
        out.mkdir(parents=True, exist_ok=False)
        with (out / "receipt.json").open("xb") as stream:
            stream.write(raw)
        print(json.dumps({"status": report["status"], "receipt": str(out / "receipt.json"), "sha256": _sha(raw)}))
    except (MassSourceError, CatalogError, OSError) as error:
        parser.exit(1, f"FAIL_P04C_MOUNTED_MASS_SOURCE_AUDIT: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
