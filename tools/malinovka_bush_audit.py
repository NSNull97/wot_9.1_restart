"""Inventory explicitly named bush/shrub instances in pinned #717 Malinovka.

The output is a local research receipt, not a concealment geometry exporter.
SpeedTree canopy bounds and concealment effects have not been decoded. The
three selected resource names are candidates, not proof of in-game semantics.
Client resources are read only; raw SPT/BSP data are never emitted.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import re

if __package__:
    from .map_package import (decode, file_digest, member, no_links, open_archive,
                              sha, signed16, transformed, walk)
else:
    from map_package import (decode, file_digest, member, no_links, open_archive,
                             sha, signed16, transformed, walk)


MAP_PIN = {"bytes": 86993684, "sha256": "bcefe13bd0a82916292075c976210770fea2d7e2cef81ec2fdaea9b427b197a0"}
SHARED_PIN = {"bytes": 1295549695, "sha256": "11b3dd86eef85eb2128c78ec993d259b3f5c1fb187b0ce061f79088b68350025"}
PREFIX = "speedtree/02_Malinovka/"
RESOURCE_PINS = {
    PREFIX + "Bush.spt": (13477, "a88d6635fd6ce65c7b4ae01fbd98ccb5695df3cde4d03fe1140879595a6f4118"),
    PREFIX + "Shrub_1.spt": (13410, "02c12d819d3b4409f1056563e190b235cf7ff71308f67dd75dfb55c44316d60a"),
    PREFIX + "Shrub_2.spt": (13420, "c304486045179ace4810918dc4352a9a96c9ebb6114ac7da29352dae65c0c92e"),
}
CHUNK = re.compile(r"spaces/02_malinovka/([0-9a-f]{4})([0-9a-f]{4})o\.chunk\Z")


def selected_row(chunk, index, fields):
    resource = fields.get("/spt[1]")
    if resource not in RESOURCE_PINS:
        return None
    transform = fields.get("/transform[1]")
    if (type(index) is not int or index < 1 or type(transform) is not list or len(transform) != 12
            or any(type(x) not in (float, int) or not math.isfinite(x) or abs(x) > 10000 for x in transform)):
        raise ValueError("invalid selected SpeedTree transform")
    seed = fields.get("/seed[1]")
    if type(seed) is not int or not 0 <= seed <= 0xffffffff:
        raise ValueError("invalid selected SpeedTree seed")
    return {"chunk": list(chunk), "speedtree_index": index, "resource": resource,
            "seed": seed, "transform": transform,
            "world_origin": list(transformed((0, 0, 0), transform, chunk))}


def audit(original):
    root = no_links(Path(original)).resolve(strict=True)
    packages = root / "res" / "packages"
    map_path, shared_path = (no_links(packages / name) for name in ("02_malinovka.pkg", "shared_content.pkg"))
    if file_digest(map_path) != MAP_PIN or file_digest(shared_path) != SHARED_PIN:
        raise ValueError("#717 package pin differs")
    with open_archive(shared_path) as archive:
        for name, (size, digest) in RESOURCE_PINS.items():
            data = member(archive, name)
            if len(data) != size or sha(data) != digest or b"__IdvSpt_02_" not in data[:32]:
                raise ValueError("selected SPT source differs: " + name)
    rows, counts, chunk_pins = [], Counter(), []
    with open_archive(map_path) as archive:
        chunks = sorted(i.filename for i in archive.infolist() if i.filename.endswith(".chunk"))
        if len(chunks) != 144 or len(set(chunks)) != 144:
            raise ValueError("unexpected Malinovka chunks")
        for path in chunks:
            match = CHUNK.fullmatch(path)
            if match is None:
                raise ValueError("unexpected chunk path")
            chunk = tuple(signed16(value) for value in match.groups())
            data = member(archive, path)
            chunk_pins.append({"chunk": list(chunk), "sha256": sha(data)})
            index = 0
            for item in decode(data)["children"]:
                if item["name"] != "speedtree":
                    continue
                index += 1
                if index > 5000:
                    raise ValueError("per chunk SpeedTree bound")
                fields = dict(walk(item["data"]))
                name = fields.get("/spt[1]")
                if type(name) is not str or len(name) > 512:
                    raise ValueError("invalid SpeedTree resource")
                counts[name] += 1
                row = selected_row(chunk, index, fields)
                if row is not None:
                    rows.append(row)
    if len(rows) > 5000:
        raise ValueError("selected instance bound")
    return {"schema": "content0-s5a-malinovka-bush-inventory.v1",
            "map_package_pin": MAP_PIN, "shared_package_pin": SHARED_PIN,
            "selected_resource_pins": {k: {"bytes": v[0], "sha256": v[1]} for k, v in RESOURCE_PINS.items()},
            "chunk_pins": chunk_pins, "all_speedtree_counts": dict(sorted(counts.items())), "instances": rows,
            "limitations": ["Name-based candidates only; visual appearance and concealment behavior need native verification.",
                            "SPT canopy geometry and bounds are not decoded; no collision BSP is treated as vegetation.",
                            "No detection coefficient or ray attenuation is inferred from these source records."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.original), ensure_ascii=False, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
