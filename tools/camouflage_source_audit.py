"""Read-only, bounded inventory of selected #717 camouflage source fields.

This is an evidence inventory, not a reconstructed detection law. In particular,
absence of a named field in the vehicle XMLs does not establish that no other
client resource or server data contains it. Output is JSON on stdout; no client
data are modified and no bytecode is executed.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

if __package__:
    from .battle_any_profiles import CATALOG_SHA256, Sources, load_catalog
else:
    from battle_any_profiles import CATALOG_SHA256, Sources, load_catalog


DEVICE_SOURCE = "res/scripts/item_defs/vehicles/common/optional_devices.xml"
DEVICE_PIN = {"bytes": 14807, "sha256": "f24f01573b3848df1a5051752a2e5f937857e7062b78a4dd1812194486c843c6"}
# These names are queried literally; do not conflate visual camouflage texture
# sections with combat coefficients or treat the query as a complete search.
FIELD_NAMES = frozenset(("invisibility", "invisibilityFactor", "camouflageNetBonus"))
SEGMENT = re.compile(r"^([^/\[\]]+)\[\d+\]$")


def matching_fields(flat):
    result = []
    for path, value in sorted(flat.items()):
        last = path.rsplit("/", 1)[-1]
        match = SEGMENT.fullmatch(last)
        if match and match.group(1) in FIELD_NAMES:
            result.append({"path": path, "value": value})
    return result


def net_facts(flat):
    root = "/camouflageNet[1]"
    paths = {"source_id": "/id[1]", "script": "/script[1]",
             "weight_kg": "/script[1]/weight[1]",
             "activation_seconds": "/script[1]/activateWhenStillSec[1]"}
    facts = {key: flat[root + path] for key, path in paths.items()}
    if facts != {"source_id": 6, "script": "CamouflageNet", "weight_kg": 100,
                 "activation_seconds": "3.0"}:
        raise ValueError("#717 camouflage net facts differ from pinned source")
    facts["compact_id"] = 6 * 256 + 249
    return facts


def audit(original):
    source = Sources(original)
    catalog = load_catalog(source.root)
    if catalog.sha256 != CATALOG_SHA256:
        raise ValueError("research catalogue differs from pinned build")
    vehicle_rows = []
    for vehicle_id, vehicle in sorted(catalog.document["vehicles"].items()):
        path = vehicle["source"]
        flat = source.xml(path)
        vehicle_rows.append({"vehicle_id": vehicle_id, "source": path,
                             "source_pin": source.files[path][1],
                             "matching_fields": matching_fields(flat)})
    device = source.xml(DEVICE_SOURCE)
    if source.files[DEVICE_SOURCE][1] != DEVICE_PIN:
        raise ValueError("optional devices source hash differs")
    return {"schema": "content0-s5a-camouflage-source-inventory.v1",
            "source_build": "v.0.9.1 #717", "catalog_sha256": catalog.sha256,
            "query_exact_leaf_names": sorted(FIELD_NAMES),
            "vehicles": vehicle_rows, "device_source": DEVICE_SOURCE,
            "device_pin": DEVICE_PIN, "net": net_facts(device),
            "limitations": [
                "Matching XML fields are static declarations; their gameplay interpretation is not established here.",
                "No conclusion about unsearched files, server data, default values, movement, firing or vegetation follows from absence in these XMLs.",
                "Vehicle camouflage texture fields are outside this combat-field query.",
            ]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.original), ensure_ascii=False, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
