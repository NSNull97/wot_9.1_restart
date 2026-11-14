"""Extract map-authored #717 ground-strength samples for the shared worker."""

import argparse
from collections import Counter
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import struct
import zipfile
import zlib

from map_package import ROOT, file_digest, member, no_links, open_archive, read_file, require, signed16
from packed_xml import decode, walk


MAGIC = b"WOTGND1\0"
CONSTANTS_SHA256 = "1c07c2e6a956dcfef95c4020954b4ca39efd77844d328cded935307a6515eebd"
MAX_OUTPUT = 8 * 1024 * 1024
CONTAINER_SIGNATURE = b"\0piz!\x90\xafB"
HEADER = struct.Struct("<8s44s32sH")


def verify_header(raw):
    require(HEADER.size <= len(raw) <= MAX_OUTPUT, "ground output size")
    magic, asset, terrain_sha, tiles = HEADER.unpack_from(raw)
    name = asset.rstrip(b"\0").decode("ascii")
    require(magic == MAGIC and 1 <= tiles <= 1024 and re.fullmatch(r"[0-9]{2}_[a-z0-9_]{1,40}", name),
            "ground sidecar header")
    return name, terrain_sha.hex()


def ground_codes(raw):
    """Read the packed dominant texture map's high nibble, not the texture's default."""
    require(33 <= len(raw) <= 64 * 1024, "dominant texture size bound")
    magic, version, count, stride, width, height, pad_x, pad_z = struct.unpack_from("<8I", raw)
    require(magic == 0x0074616d and version == 1 and 1 <= count <= 16 and 1 <= stride <= 256 and
            width == height and width in (16, 32, 64, 128) and pad_x == pad_z == 0, "dominant texture header")
    table_end = 32 + count * stride
    require(raw[table_end:table_end + 8] == CONTAINER_SIGNATURE, "dominant texture compression header")
    size = width * height
    require(table_end + 12 < len(raw) and struct.unpack_from("<I", raw, table_end + 8)[0] == size,
            "dominant texture unpacked size")
    inflater = zlib.decompressobj()
    unpacked = inflater.decompress(raw[table_end + 12:], size + 1)
    require(len(unpacked) == size and inflater.eof and not inflater.unconsumed_tail and not inflater.unused_data,
            "dominant texture compressed payload")
    require(all((sample & 15) < count and sample >> 4 <= 5 for sample in unpacked), "dominant texture index or ground code")
    return width, bytes(sample >> 4 for sample in unpacked)


def export(original, terrain, output):
    config = json.loads(read_file(ROOT / "config/project.local.json", 65536).decode("utf-8-sig"))
    original = no_links(Path(original)).resolve(strict=True)
    owned_original = no_links(Path(config["paths"]["original_client_root"])).resolve(strict=True)
    local = no_links(Path(config["paths"]["local_artifacts_root"])).resolve(strict=True)
    terrain = no_links(Path(terrain)).resolve(strict=True)
    output = no_links(Path(output)).resolve()
    require(original == owned_original and terrain.is_relative_to(local) and output.is_relative_to(local),
            "pinned original and owned terrain/output paths required")
    require(not output.exists() and output.parent.is_dir(), "fresh output path required")
    raw_terrain = read_file(terrain, 16384)
    terrain_sha = hashlib.sha256(raw_terrain).hexdigest()
    terrain_doc = json.loads(raw_terrain)
    name = terrain_doc["map"]
    require(re.fullmatch(r"[0-9]{2}_[a-z0-9_]{1,40}", name), "ground map identity")
    registry = json.loads(read_file(ROOT / "server/contracts/map_registry.json", 1024 * 1024))
    require(any(row["asset"] == name and row["terrain"]["manifest_sha256"] == terrain_sha for row in registry["maps"]),
            "registered terrain manifest pin required")
    check_constants = file_digest(original / "res/scripts/common/constants.pyc", 1024 * 1024)
    require(check_constants["sha256"] == CONSTANTS_SHA256, "#717 ground enum source changed")
    package = original / "res/packages" / (name + ".pkg")
    package_pin = file_digest(package)
    identity = terrain_doc["source"]["original_package"]
    require(package_pin == {key: identity[key] for key in package_pin}, "terrain source package pin")

    tiles, counts = {}, Counter()
    prefix = "spaces/" + name + "/"
    with open_archive(package) as archive:
        for entry in sorted(archive.namelist()):
            if not entry.endswith(".chunk"):
                continue
            token = entry.removeprefix(prefix)
            require(re.fullmatch(r"[0-9a-f]{8}o\.chunk", token), "ground tile path")
            x, z = signed16(token[:4]), signed16(token[4:8])
            require(-64 <= x <= 64 and -64 <= z <= 64 and (x, z) not in tiles, "ground tile coordinate")
            terrain_path = dict(walk(decode(member(archive, entry)))).get("/terrain[1]/resource[1]")
            if terrain_path is None:
                continue
            cdata = token[:-6] + ".cdata"
            require(terrain_path == cdata + "/terrain2", "ground source chunk terrain binding")
            with zipfile.ZipFile(BytesIO(member(archive, prefix + cdata))) as inner:
                names = inner.namelist()
                require(len(names) <= 256 and len(set(names)) == len(names), "ground cdata member bound or duplicate")
                size, grid = ground_codes(member(inner, "terrain2/dominantTextures", 64 * 1024))
            tiles[x, z] = struct.pack("<hhH", x, z, size) + grid
            counts.update(grid)
    require(1 <= len(tiles) <= 1024, "ground tile count")
    payload = HEADER.pack(MAGIC, name.encode("ascii"), bytes.fromhex(terrain_sha), len(tiles))
    payload += b"".join(tiles[key] for key in sorted(tiles))
    require(len(payload) <= MAX_OUTPUT, "ground output size")
    with output.open("xb") as stream:
        stream.write(payload)
    return {"status": "PASS_EXPORTED_GROUND_STRENGTH", "map": name, "tiles": len(tiles), "codes": dict(sorted(counts.items())),
            "terrain_sha256": terrain_sha, "source_package": package_pin, "source_ground_enum": check_constants,
            "ground_strength": {"path": str(output), "sha256": hashlib.sha256(payload).hexdigest()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("export",))
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--terrain", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export(args.original, args.terrain, args.out), sort_keys=True))


if __name__ == "__main__":
    main()
