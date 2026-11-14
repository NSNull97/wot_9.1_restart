"""Hash-bound #717 optional-device and consumable source catalogue."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
import sys

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
SLOT_COUNT = 3

# Authoritative runtime effect families backed by the battle command path.
DEVICE_EFFECTS = {1529: "coatedOptics"}
CONSUMABLE_EFFECTS = {
    251: "handExtinguishers", 507: "autoExtinguishers",
    763: "smallMedkit", 1019: "largeMedkit",
    1275: "smallRepairkit", 1531: "largeRepairkit",
}
SUPPORTED_ITEMS = DEVICE_EFFECTS | CONSUMABLE_EFFECTS


def canonical(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")


def _criteria(node):
    return {key: _criteria(value) if children(value) else scalar(value) for key, value in children(node)}


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
            items.append({
                "compact_id": compact_id, "kind": kind, "source_id": item_id, "source_name": source_name,
                "price": {"currency": "gold" if child(price, "gold") is not None else "credits", "amount": scalar(price)},
                "removable": scalar(child(node, "removable", True)),
                "tags": scalar(child(node, "tags", "")).split(),
                "incompatible_tags": scalar(child(node, "incompatibleTags", "")).split(),
                "filters": [[mode, _criteria(entry)] for mode, entry in children(child(node, "vehicleFilter"))],
                "script": scalar(script), "effect": _criteria(script),
            })
    items.sort(key=lambda row: row["compact_id"])
    if len(items) != len({row["compact_id"] for row in items}):
        raise ValueError("duplicate artefact compact ID")
    return {"schema": SCHEMA, "source_build": SOURCE_BUILD, "sources": sources, "items": items}


@dataclass(frozen=True)
class LiveItem:
    compact_id: int
    kind: int
    removable: bool
    tags: frozenset[str]
    incompatible_tags: frozenset[str]


@lru_cache(maxsize=1)
def live_items():
    raw = read(MANIFEST, MAX_MANIFEST, MANIFEST_SHA256)
    document = json.loads(raw)
    if document["schema"] != SCHEMA or document["source_build"] != SOURCE_BUILD:
        raise ValueError("invalid artefact catalogue identity")
    result = {}
    for row in document["items"]:
        cd = row["compact_id"]
        if cd in SUPPORTED_ITEMS:
            if row["source_name"] != SUPPORTED_ITEMS[cd] or row["filters"] or row["effect"].get("weight", 0):
                raise ValueError("unsupported restrictions on live artefact")
            result[cd] = LiveItem(cd, row["kind"], row["removable"],
                                  frozenset(row["tags"]), frozenset(row["incompatible_tags"]))
    if set(result) != set(SUPPORTED_ITEMS):
        raise ValueError("incomplete artefact catalogue binding")
    from types import MappingProxyType
    return MappingProxyType(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("build", "check"))
    parser.add_argument("--client", required=True)
    args = parser.parse_args()
    raw = canonical(build(args.client))
    if args.operation == "build":
        MANIFEST.write_bytes(raw)
    elif raw != read(MANIFEST, MAX_MANIFEST, MANIFEST_SHA256):
        raise SystemExit("artefact catalogue differs from pinned client sources")
    print(sha256(raw).hexdigest())


if __name__ == "__main__":
    main()
