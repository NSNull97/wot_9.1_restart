"""Table of the battle guns' dispersion data from the original #717 client (read only).

`shotDispersionRadius` (metres at 100 m) and `shotDispersionFactors/afterShot` of the gun each
battle vehicle fires, as the mounted override or the shared gun. The client's own marker uses
these with `Avatar.getOwnVehicleShotDispersionAngle`; the server computes the same circle.

Command: python -B -X utf8 tools/gun_dispersion.py build|check --client DIR
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import packed_xml  # noqa: E402

OUT = ROOT / "config" / "catalog" / "gun_dispersion.v1.json"
PINS = ROOT / "server" / "gateway" / "src" / "shared" / "gun_dispersion_pins.rs"
CATALOGS = (ROOT / "config" / "catalog" / "battle_profiles.v1.json", ROOT / "config" / "test_lab" / "battle_profiles.v1.json")
SCHEMA = "wot091-gun-dispersion.v1"
# Curated gateway kinds fire one exact stock gun (`p06t_shell_data::GunProfile::gun_compact_descr`).
CURATED = {"ussr:MS-1": 5892, "ussr:IS-7": 14852, "ussr:T-26": 4100, "ussr:T-34": 4, "ussr:T-34-85": 1540,
           "germany:Waffentrager_E100": 23060, "uk:GB48_FV215b_183": 13908}


class DispersionError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise DispersionError(message)


def tree(path):
    return dict(packed_xml.walk(packed_xml.decode(Path(path).read_bytes())))


def number(value, path):
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise DispersionError("number: " + path)
    require(0 < result < 100, "bound: " + path)
    return result


class Client:
    def __init__(self, root):
        self.root = Path(root) / "res/scripts/item_defs/vehicles"
        self.vehicles = {}
        self.guns = {}

    def vehicle(self, nation, resource):
        key = (nation, resource)
        if key not in self.vehicles:
            self.vehicles[key] = tree(self.root / nation / (resource + ".xml"))
        return self.vehicles[key]

    def shared(self, nation):
        if nation not in self.guns:
            self.guns[nation] = tree(self.root / nation / "components" / "guns.xml")
        return self.guns[nation]

    def mounted(self, nation, resource, mount, gun):
        """Radius and afterShot: the mount's own value, else the shared gun's."""
        vehicle, shared = self.vehicle(nation, resource), self.shared(nation)
        base = "/shared[1]/%s[1]/" % gun
        radius = vehicle.get(mount + "/shotDispersionRadius[1]", shared.get(base + "shotDispersionRadius[1]"))
        after = vehicle.get(mount + "/shotDispersionFactors[1]/afterShot[1]", shared.get(base + "shotDispersionFactors[1]/afterShot[1]"))
        return number(radius, mount + " radius"), number(after, mount + " afterShot")

    def mount_of_compact(self, nation, resource, compact):
        """The first turret mount of the gun with this compact descriptor."""
        shared = self.shared(nation)
        wanted = compact >> 8
        names = [m.group(1) for path, value in shared.items()
                 for m in [re.fullmatch(r"/ids\[1\]/([^/]+)\[1\]", path)] if m and int(value) == wanted]
        require(len(names) == 1, "gun id %d" % wanted)
        for path in self.vehicle(nation, resource):
            m = re.fullmatch(r"(/turrets0\[1\]/[^/]+/guns\[1\]/%s\[1\])" % re.escape(names[0]), path)
            if m:
                return m.group(1), names[0]
        raise DispersionError("no mount of " + names[0])


def rows_from(client, catalog, table):
    for row in catalog["vehicles"]:
        if row["status"] != "generated":
            continue
        name = row["nation"] + ":" + row["resource"]
        if name in CURATED or name in table:
            continue
        gun = row["gun"]
        m = re.fullmatch(r"res/scripts/item_defs/vehicles/([a-z]+)/([^:]+)\.xml:(/.+)", gun["mount_source_path"])
        require(m is not None, "mount path of " + name)
        radius, after = client.mounted(m.group(1), Path(m.group(2)).name, m.group(3), gun["resource"])
        require(abs(radius - float(gun["shot_dispersion_radius"])) < 1e-9, "catalog radius of " + name)
        table[name] = dict(after_shot=after, gun=gun["resource"], radius_m=radius, spg=row["vehicle_class"] == "SPG")


def build(client_root):
    client = Client(client_root)
    table = {}
    for name, compact in CURATED.items():
        nation, resource = name.split(":")
        mount, gun = client.mount_of_compact(nation, resource, compact)
        radius, after = client.mounted(nation, resource, mount, gun)
        table[name] = dict(after_shot=after, compact=compact, gun=gun, radius_m=radius, spg=False)
    for path in CATALOGS:
        rows_from(client, json.loads(path.read_text("utf-8")), table)
    document = dict(schema=SCHEMA, source="#717 res/scripts/item_defs/vehicles (mounted gun, else components/guns.xml)", guns=table)
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii") + b"\n"


def pins(raw):
    return ("// GENERATED by tools/gun_dispersion.py; do not edit.\npub const TABLE_SHA256:&str=\"%s\";\n" % hashlib.sha256(raw).hexdigest()).encode("ascii")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("build", "check"))
    parser.add_argument("--client", required=True)
    args = parser.parse_args(argv)
    try:
        raw = build(args.client)
        if args.command == "build":
            OUT.write_bytes(raw)
            PINS.write_bytes(pins(raw))
        else:
            require(OUT.read_bytes() == raw and PINS.read_bytes() == pins(raw), "table differs from the client (run build)")
        guns = json.loads(raw)["guns"]
        print(json.dumps(dict(status="PASS", command=args.command, guns=len(guns), spg=sum(1 for g in guns.values() if g["spg"]))))
        return 0
    except (DispersionError, OSError, KeyError, ValueError) as error:
        print(json.dumps(dict(status="FAIL_GUN_DISPERSION", reason="%s: %s" % (type(error).__name__, error))))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
