"""Build per-vehicle internal module volumes from penetration-zone skins (owner decisions 2026-11-09).

The #717 client carries no internal device volumes for any battle vehicle. Community
penetration-zone skins of the 0.9.x era mark the ammo rack, engine, fuel tanks and crew on the
vehicle's own texture, so a mark maps through the UV of the lod0 visual to the component frame.
Positions are therefore the skin authors' estimate (`project_policy`), never server data.

Rules:
* a texel is a mark when its colour is saturated in the legend hue and differs from the client texture;
* connected marks (0.30 m link) of one kind form a cluster; the engine keeps its largest cluster;
* a face of a cluster on a side runs through the whole component width, on the roof or floor through
  its whole height; on the front or rear it runs `FRONT_REAR_DEPTH_M` inward (owner 2026-11-09).

Commands (the archive and the output stay under `local/`):
  python -B -X utf8 tools/module_volumes.py build --archive ZIP --client DIR --out DIR [--only RESOURCE ...]
  python -B -X utf8 tools/module_volumes.py manifest --manifest M --dir DIR --out NEW
"""
from __future__ import annotations

import argparse
import colorsys
import hashlib
import json
import re
import struct
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import packed_xml  # noqa: E402
from battle_any_profiles import primitive_sections  # noqa: E402

SCHEMA = "wot091-module-volumes.v1"
POLICY = "project.module-volumes-from-skins.v1"
CATALOG = ROOT / "config" / "catalog" / "battle_profiles.v1.json"
FOLDERS = {"ussr": "russian", "germany": "german", "usa": "american", "france": "french", "uk": "british",
           "china": "chinese", "japan": "japan"}
# Curated gateway kind labels -> `<nation>-<resource>`, as tools/chassis_manifest.py.
CURATED = {"ms1": "ussr-MS-1", "is7": "ussr-IS-7", "t26": "ussr-T-26", "t34": "ussr-T-34", "t3485": "ussr-T-34-85",
           "wt-e100-128": "germany-Waffentrager_E100", "fv215b-183": "uk-GB48_FV215b_183"}
PARTS = ("Hull", "Turret_01")
KINDS = ("ammo", "engine", "fuel", "crew")
LINK_M = 0.30
MIN_POINTS = 8
FRONT_REAR_DEPTH_M = 0.5
MAX_MEMBER = 64 * 1024 * 1024
MAX_TEXTURE_SIDE = 4096
MAX_VERTICES = 262144
MAX_INDICES = 3 * 262144
MAX_SAMPLES = 400
TEXEL_STEP = 6.0


class VolumeError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise VolumeError(message)


def c565(v):
    return ((v >> 11 & 31) * 255 // 31, (v >> 5 & 63) * 255 // 63, (v & 31) * 255 // 31)


def decode_dds(data):
    """Colour plane of a DXT1/3/5 texture's top mip as rows of RGB bytes."""
    require(len(data) >= 128 and data[:4] == b"DDS ", "DDS header")
    height, width = struct.unpack("<2I", data[12:20])
    four_cc = data[84:88]
    require(four_cc in (b"DXT1", b"DXT3", b"DXT5"), "DDS format")
    require(4 <= width <= MAX_TEXTURE_SIDE and 4 <= height <= MAX_TEXTURE_SIDE, "DDS size")
    block, offset = (8, 0) if four_cc == b"DXT1" else (16, 8)
    blocks_w, blocks_h = (width + 3) // 4, (height + 3) // 4
    require(128 + blocks_w * blocks_h * block <= len(data), "DDS truncated")
    rows = [bytearray(3 * width) for _ in range(height)]
    position = 128
    for by in range(blocks_h):
        for bx in range(blocks_w):
            c0, c1, bits = struct.unpack_from("<HHI", data, position + offset)
            position += block
            a, b = c565(c0), c565(c1)
            if c0 > c1 or four_cc != b"DXT1":
                palette = (a, b, tuple((2 * x + y) // 3 for x, y in zip(a, b)), tuple((x + 2 * y) // 3 for x, y in zip(a, b)))
            else:
                palette = (a, b, tuple((x + y) // 2 for x, y in zip(a, b)), (0, 0, 0))
            for j in range(4):
                y = by * 4 + j
                if y >= height:
                    continue
                row = rows[y]
                for i in range(4):
                    x = bx * 4 + i
                    if x < width:
                        row[3 * x:3 * x + 3] = bytes(palette[bits >> (2 * (4 * j + i)) & 3])
    return width, height, rows


def classify(skin, client):
    """Legend kind of one texel, or None."""
    if max(abs(a - b) for a, b in zip(skin, client)) < 50:
        return None
    hue, saturation, value = colorsys.rgb_to_hsv(skin[0] / 255, skin[1] / 255, skin[2] / 255)
    hue *= 360
    if saturation < 0.55 or value < 0.35:
        return None
    if 285 <= hue <= 330:
        return "ammo"
    if 90 <= hue <= 150:
        return "engine"
    if 195 <= hue <= 230:
        return "fuel"
    if 50 <= hue <= 72:
        return "crew"
    return None


def mesh(raw):
    """Positions, UVs, triangle indices and primitive groups of a static BigWorld mesh."""
    sections = primitive_sections(raw)
    vertex_keys = [k for k in sections if k.endswith("vertices")]
    index_keys = [k for k in sections if k.endswith("indices")]
    require(len(vertex_keys) == 1 and len(index_keys) == 1, "mesh sections")
    v = raw[sections[vertex_keys[0]]["offset"]:sections[vertex_keys[0]]["offset"] + sections[vertex_keys[0]]["bytes"]]
    i = raw[sections[index_keys[0]]["offset"]:sections[index_keys[0]]["offset"] + sections[index_keys[0]]["bytes"]]
    require(len(v) >= 68 and len(i) >= 72, "mesh truncated")
    require(v[:64].split(b"\0", 1)[0] in (b"xyznuv", b"xyznuvtb"), "vertex format")
    count = struct.unpack_from("<I", v, 64)[0]
    require(0 < count <= MAX_VERTICES and len(v) == 68 + 32 * count, "vertex count")
    points = [struct.unpack_from("<3f", v, 68 + 32 * n) for n in range(count)]
    uvs = [struct.unpack_from("<2f", v, 68 + 32 * n + 16) for n in range(count)]
    width = {b"list": 2, b"list32": 4}.get(i[:64].split(b"\0", 1)[0])
    total, groups = struct.unpack_from("<II", i, 64)
    require(width is not None and 0 < total <= MAX_INDICES and total % 3 == 0 and 0 < groups <= 256
            and len(i) == 72 + width * total + 16 * groups, "index layout")
    ids = struct.unpack_from("<" + ("H" if width == 2 else "I") * total, i, 72)
    require(all(n < count for n in ids), "index bound")
    rows = [struct.unpack_from("<4I", i, 72 + width * total + 16 * g) for g in range(groups)]
    return points, uvs, ids, rows


def bounds(points):
    return [[min(p[i] for p in points) for i in range(3)], [max(p[i] for p in points) for i in range(3)]]


def diffuse_textures(visual):
    """Primitive group index -> diffuse texture path of a lod0 visual."""
    names, textures = {}, {}
    for path, value in packed_xml.walk(packed_xml.decode(visual)):
        m = re.match(r"/renderSet\[1\]/geometry\[1\]/primitiveGroup\[(\d+)\]/material\[1\]/property\[(\d+)\](/Texture\[1\])?$", path)
        if m:
            (textures if m.group(3) else names)[(int(m.group(1)) - 1, m.group(2))] = value
    return {k[0]: textures[k] for k, v in names.items() if v == "diffuseMap" and k in textures}


def samples(area_texels):
    """Barycentric sample points of a triangle, about one per TEXEL_STEP texels."""
    steps = max(1, min(27, int((2 * max(area_texels, 0.)) ** 0.5 / TEXEL_STEP)))
    out = []
    for a in range(steps + 1):
        for b in range(steps + 1 - a):
            c = steps - a - b
            out.append(((a + 1 / 3) / (steps + 1), (b + 1 / 3) / (steps + 1), (c + 1 / 3) / (steps + 1)))
    return out[:MAX_SAMPLES]


def face_axis(a, b, c):
    u = [b[k] - a[k] for k in range(3)]
    w = [c[k] - a[k] for k in range(3)]
    cross = (u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0])
    magnitudes = [abs(x) for x in cross]
    return magnitudes.index(max(magnitudes))


def clusters(points, link=LINK_M):
    """Connected components of (point, axis) rows by a uniform-grid link distance."""
    cell = {}
    for index, (p, _) in enumerate(points):
        cell.setdefault(tuple(int(x // link) for x in p), []).append(index)
    seen, out = set(), []
    limit = link * link
    for start in range(len(points)):
        if start in seen:
            continue
        seen.add(start)
        stack, group = [start], []
        while stack:
            n = stack.pop()
            group.append(n)
            p = points[n][0]
            base = tuple(int(x // link) for x in p)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        for m in cell.get((base[0] + dx, base[1] + dy, base[2] + dz), ()):
                            if m not in seen and sum((p[k] - points[m][0][k]) ** 2 for k in range(3)) <= limit:
                                seen.add(m)
                                stack.append(m)
        out.append([points[n] for n in group])
    return sorted(out, key=len, reverse=True)


def face_boxes(cluster, box):
    """Boxes of one cluster by the owner's depth rule, one per face direction with enough points."""
    out = []
    center = [(box[0][k] + box[1][k]) / 2 for k in range(3)]
    for axis in range(3):
        rows = [p for p, a in cluster if a == axis]
        if len(rows) < MIN_POINTS:
            continue
        low, high = bounds(rows)
        if axis in (0, 1):
            low[axis], high[axis] = box[0][axis], box[1][axis]
        elif sum(p[2] for p in rows) / len(rows) >= center[2]:
            low[2] -= FRONT_REAR_DEPTH_M
        else:
            high[2] += FRONT_REAR_DEPTH_M
        low = [max(low[k], box[0][k]) for k in range(3)]
        high = [min(high[k], box[1][k]) for k in range(3)]
        if all(high[k] > low[k] for k in range(3)):
            out.append([[round(x, 4) for x in low], [round(x, 4) for x in high]])
    return out


def overlap(a, b):
    """Share of the smaller box that the two boxes have in common, along height and length."""
    share = 1.0
    for axis in (1, 2):
        common = min(a[1][axis], b[1][axis]) - max(a[0][axis], b[0][axis])
        share *= max(common, 0.) / max(min(a[1][axis] - a[0][axis], b[1][axis] - b[0][axis]), 1e-6)
    return share


def merge_seats(seats):
    """One entry per crew member: clusters overlapping by half or more along height and length."""
    merged = []
    for boxes in seats:
        target = next((m for m in merged if any(overlap(a, b) >= 0.5 for a in m for b in boxes)), None)
        if target is None:
            merged.append(list(boxes))
        else:
            target.extend(boxes)
    return merged


class Sources:
    def __init__(self, archive, client):
        self.archive = zipfile.ZipFile(archive)
        self.skins = {i.filename.lower(): i for i in self.archive.infolist()
                      if i.filename.lower().endswith(".dds") and not i.is_dir() and 0 < i.file_size <= MAX_MEMBER}
        self.client = Path(client)
        self.packages = {}
        self.textures = {}

    def package(self, folder):
        if folder not in self.packages:
            archive = zipfile.ZipFile(self.client / "res" / "packages" / ("vehicles_" + folder + ".pkg"))
            self.packages[folder] = (archive, {n.lower(): n for n in archive.namelist()})
        return self.packages[folder]

    def skin_member(self, key):
        if key in self.skins:
            return self.skins[key], False
        if key.endswith("_am.dds") and key[:-7] + ".dds" in self.skins:
            return self.skins[key[:-7] + ".dds"], True
        return None, False

    def pair(self, folder, path):
        """Skin and client planes of a diffuse texture; None when the skin has no such file."""
        key = re.sub(r"\.tga$", ".dds", path, flags=re.I).lower()
        if key in self.textures:
            return self.textures[key]
        member, alias = self.skin_member(key)
        archive, names = self.package(folder)
        result = None
        if member is not None and key in names and archive.getinfo(names[key]).file_size <= MAX_MEMBER:
            result = dict(skin=decode_dds(self.archive.read(member)), client=decode_dds(archive.read(names[key])),
                          member=member.filename, alias=alias, date="%04d-%02d" % member.date_time[:2])
        self.textures[key] = result
        return result


def project(sources, folder, resource, part):
    """Marks of one lod0 component: kind -> [(point, face axis)], and the texture records used."""
    archive, _ = sources.package(folder)
    stem = "vehicles/%s/%s/normal/lod0/%s" % (folder, resource, part)
    points, uvs, ids, rows = mesh(archive.read(stem + ".primitives"))
    textures = diffuse_textures(archive.read(stem + ".visual"))
    marks, used = {}, {}
    for group, (start, triangles, _, _) in enumerate(rows):
        pair = textures.get(group) and sources.pair(folder, textures[group])
        if not pair:
            continue
        used[pair["member"]] = dict(alias=pair["alias"], date=pair["date"])
        sw, sh, sr = pair["skin"]
        cw, ch, cr = pair["client"]
        for k in range(triangles):
            a, b, c = ids[start + 3 * k:start + 3 * k + 3]
            ua, ub, uc = uvs[a], uvs[b], uvs[c]
            area = abs((ub[0] - ua[0]) * (uc[1] - ua[1]) - (uc[0] - ua[0]) * (ub[1] - ua[1])) / 2 * sw * sh
            axis = None
            for l1, l2, l3 in samples(area):
                u = (l1 * ua[0] + l2 * ub[0] + l3 * uc[0]) % 1
                v = (l1 * ua[1] + l2 * ub[1] + l3 * uc[1]) % 1
                sx, sy, cx, cy = int(u * sw), int(v * sh), int(u * cw), int(v * ch)
                kind = classify(tuple(sr[sy][3 * sx:3 * sx + 3]), tuple(cr[cy][3 * cx:3 * cx + 3]))
                if kind:
                    if axis is None:
                        axis = face_axis(points[a], points[b], points[c])
                    p = tuple(l1 * points[a][i] + l2 * points[b][i] + l3 * points[c][i] for i in range(3))
                    marks.setdefault(kind, []).append((p, axis))
    return marks, used


def collision_box(sources, folder, resource, part):
    archive, _ = sources.package(folder)
    points, _, _, _ = mesh(archive.read("vehicles/%s/%s/collision/%s.primitives" % (folder, resource, part)))
    return bounds(points)


def build_component(sources, folder, resource, part):
    marks, used = project(sources, folder, resource, part)
    box = collision_box(sources, folder, resource, part)
    component = {}
    for kind in KINDS:
        groups = [g for g in clusters(marks.get(kind, [])) if len(g) >= MIN_POINTS]
        if kind == "engine":
            groups = groups[:1]
        built = [face_boxes(g, box) for g in groups]
        built = [b for b in built if b]
        if kind == "crew":
            # One entry per crew member; icons of one seat on both sides are one member.
            built = merge_seats(sorted(built, key=lambda boxes: min(b[0][2] for b in boxes)))
            if built:
                component["crew"] = built
        else:
            flat = [b for boxes in built for b in boxes]
            if flat:
                component[kind] = flat
    return component, used, box


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii") + b"\n"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def resource_folder(client, nation, resource):
    raw = (Path(client) / "res/scripts/item_defs/vehicles" / nation / (resource + ".xml")).read_bytes()
    for path, value in packed_xml.walk(packed_xml.decode(raw)):
        if path == "/hull[1]/models[1]/undamaged[1]":
            m = re.fullmatch(r"vehicles/([a-z]+)/([A-Za-z0-9_.-]+)/normal/lod0/Hull\.model", value)
            require(m is not None, "hull model path")
            return m.group(1), m.group(2)
    raise VolumeError("hull model absent")


def build(args):
    catalog = json.loads(CATALOG.read_text("utf-8"))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    sources = Sources(args.archive, args.client)
    archive_sha = sha(Path(args.archive).read_bytes())
    summary = {}
    for row in catalog["vehicles"]:
        if row["status"] != "generated" or (args.only and row["resource"] not in args.only):
            continue
        name = row["nation"] + "-" + row["resource"]
        sources.textures.clear()
        try:
            folder, resource = resource_folder(args.client, row["nation"], row["resource"])
            components, textures = {}, {}
            for part in PARTS:
                try:
                    component, used, box = build_component(sources, folder, resource, part)
                except KeyError:
                    continue
                textures.update(used)
                if component:
                    components[part] = dict(box=[[round(x, 4) for x in c] for c in box], volumes=component)
            kinds = sorted({k for c in components.values() for k in c["volumes"]})
            summary[name] = dict(kinds=kinds, parts=sorted(components), alias=any(t["alias"] for t in textures.values()))
            if components:
                document = dict(schema=SCHEMA, policy=POLICY, vehicle=row["vehicle_id"], components=components,
                                source=dict(archive_sha256=archive_sha, authors=["Dendyt", "Kodoku", "Shotter", "Lemon96", "Vadila_Carl"],
                                            textures=textures), depth=dict(front_rear_m=FRONT_REAR_DEPTH_M))
                (out / (name + ".json")).write_bytes(canonical(document))
        except (VolumeError, OSError, ValueError, KeyError, struct.error) as error:
            summary[name] = dict(error="%s: %s" % (type(error).__name__, error))
        sources.textures.clear()
    (out / "summary.json").write_bytes(canonical(summary))
    print(json.dumps(dict(status="PASS", vehicles=len(summary), with_volumes=sum(1 for s in summary.values() if s.get("kinds")),
                          errors=sum(1 for s in summary.values() if "error" in s))))
    return 0


def manifest(args):
    """Copy a profile13 manifest, binding each profile that has a volumes file by path and hash."""
    source = Path(args.manifest)
    require(source.is_absolute() and source.is_file(), "absolute manifest required")
    document = json.loads(source.read_text("utf-8"))
    directory = Path(args.dir)
    require(directory.is_absolute() and directory.is_dir(), "absolute volumes directory required")
    bound = []
    for profile in document["profiles"]:
        path = directory / (CURATED.get(profile["kind"], profile["kind"]) + ".json")
        if path.is_file():
            profile["module_volumes"] = dict(path=str(path), sha256=sha(path.read_bytes()))
            bound.append(profile["kind"])
    Path(args.out).write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", "utf-8")
    print(json.dumps(dict(status="PASS", profiles=len(document["profiles"]), bound=sorted(bound))))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    b = commands.add_parser("build")
    b.add_argument("--archive", required=True)
    b.add_argument("--client", required=True)
    b.add_argument("--out", required=True)
    b.add_argument("--only", nargs="*")
    m = commands.add_parser("manifest")
    m.add_argument("--manifest", required=True)
    m.add_argument("--dir", required=True)
    m.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        return build(args) if args.command == "build" else manifest(args)
    except (VolumeError, OSError, KeyError, ValueError) as error:
        print(json.dumps(dict(status="FAIL_MODULE_VOLUMES", reason=str(error))))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
