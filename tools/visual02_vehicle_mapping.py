"""Read-only #717 USSR vehicle -> model -> visual -> texture bindings.

Resource resolution here deliberately covers declared packages only. Loose resources,
overrides, runtime model selection and shader channel semantics need separate proof.
"""
from __future__ import annotations

import hashlib
import re
import zipfile
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree

from tools.p09e_research_catalog import load_catalog, scalar
from tools.packed_xml import decode, walk

MAX_XML = 8 * 1024 * 1024
MAX_ARCHIVES = 128
MAX_ENTRIES = 1000000
MAX_READ_TOTAL = 512 * 1024 * 1024
MAX_MODELS = 20000
MAX_PARENT_DEPTH = 16
PROPERTY_TEXTURE = re.compile(r"^(.*?/property\[\d+\])/Texture\[\d+\]$")
UNDAMAGED = re.compile(r"/models\[\d+\]/undamaged\[\d+\]$")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _safe_resource(name):
    if not isinstance(name, str) or not name or len(name) > 512 or "\\" in name or "\x00" in name or ":" in name:
        raise ValueError("invalid resource path")
    p = PurePosixPath(name)
    if p.is_absolute() or any(part in ("", ".", "..") for part in name.split("/")):
        raise ValueError("unsafe resource path: " + name)
    return name


class _Packages:
    def __init__(self, root):
        self.root = root
        self.index = {}
        self.packages = []
        self.cache = {}
        self.total_read = 0
        paths = root / "paths.xml"
        with paths.open("rb") as stream:
            raw = stream.read(MAX_XML + 1)
        if len(raw) > MAX_XML or b"<!" in raw:
            raise ValueError("paths.xml bound or forbidden declaration")
        self.paths_sha256 = _sha(raw)
        doc = ElementTree.fromstring(raw)
        refs = []
        for node in doc.findall("./Paths/Path"):
            text = (node.text or "").strip()
            if not text.lower().endswith(".pkg"):
                continue
            if not text.startswith("./res/packages/"):
                raise ValueError("unexpected package path in paths.xml: " + text)
            rel = _safe_resource(text[2:])
            if rel in refs:
                raise ValueError("duplicate package path: " + rel)
            refs.append(rel)
        if not refs or len(refs) > MAX_ARCHIVES:
            raise ValueError("archive count bound")
        total = 0
        try:
            for rel in refs:
                path = root / rel
                if path.is_symlink() or not path.is_file():
                    raise ValueError("missing or linked package: " + rel)
                archive = zipfile.ZipFile(path)
                self.packages.append((rel, archive))
                infos = archive.infolist()
                total += len(infos)
                if total > MAX_ENTRIES:
                    raise ValueError("package entry count bound")
                local = set()
                for info in infos:
                    if info.is_dir() or not info.filename.lower().endswith((".model", ".visual", ".dds", ".mfm", ".png", ".tga")):
                        continue
                    name = _safe_resource(info.filename)
                    key = name.casefold()
                    if key in local:
                        raise ValueError("duplicate/case-colliding ZIP entry: " + rel + "!" + name)
                    local.add(key)
                    self.index.setdefault(key, []).append((rel, archive, info))
        except BaseException:
            self.close()
            raise

    def close(self):
        for _, archive in self.packages:
            archive.close()

    def locate(self, name):
        name = _safe_resource(name)
        matches = self.index.get(name.casefold(), [])
        if not matches:
            return None
        rel, _, info = matches[0]
        return {"resource": name, "archive": rel, "member": info.filename,
                "bytes": info.file_size, "crc32": "%08x" % info.CRC,
                "shadowed_archives": [row[0] for row in matches[1:]]}

    def read(self, name):
        name = _safe_resource(name)
        key = name.casefold()
        if key in self.cache:
            return self.cache[key]
        matches = self.index.get(key, [])
        if not matches:
            return None
        rel, archive, info = matches[0]
        if not 0 <= info.file_size <= MAX_XML:
            raise ValueError("XML member size bound: " + rel + "!" + info.filename)
        if info.file_size > max(1024, info.compress_size * 2000):
            raise ValueError("XML compression ratio bound: " + rel + "!" + info.filename)
        raw = archive.read(info)
        if len(raw) != info.file_size:
            raise ValueError("short XML member: " + info.filename)
        self.total_read += len(raw)
        if self.total_read > MAX_READ_TOTAL:
            raise ValueError("total XML data bound")
        result = (raw, self.locate(name))
        self.cache[key] = result
        return result


def _xml(raw):
    return dict(walk(decode(raw, max_bytes=MAX_XML, max_depth=48, max_nodes=400000)))


def _extension(name, ext):
    name = _safe_resource(name)
    return name if name.lower().endswith(ext) else name + ext


def build_mapping(client_root):
    """Return JSON-safe static evidence; explicit unresolved entries are never hidden."""
    root = Path(client_root).resolve(strict=True)
    catalog = load_catalog(root, cache_dir=None)
    ussr = {k: v for k, v in catalog.vehicles.items() if v["nation"] == "ussr"}
    vehicle_unlocks = [u for u in catalog.unlocks if u["item_id"].startswith("vehicle:ussr:")]
    reachable = {"vehicle:ussr:MS-1"}
    if not reachable.issubset(ussr):
        raise ValueError("MS-1 root missing")
    while True:
        next_reachable = reachable | {u["item_id"] for u in vehicle_unlocks if u["vehicle_id"] in reachable}
        if next_reachable == reachable:
            break
        reachable = next_reachable
    packages = _Packages(root)
    model_cache, visual_cache = {}, {}
    try:
        def visual(name):
            if name in visual_cache:
                return visual_cache[name]
            obj = {"resource": name, "provenance": packages.locate(name), "properties": [], "unresolved": []}
            found = packages.read(name)
            if found is None:
                obj["unresolved"].append({"reason": "visual_not_found_in_packages", "resource": name})
            else:
                raw, prov = found
                obj["provenance"] = dict(prov, sha256=_sha(raw))
                flat = _xml(raw)
                for path, value in sorted(flat.items()):
                    match = PROPERTY_TEXTURE.match(path)
                    if not match:
                        continue
                    prop = flat.get(match.group(1))
                    entry = {"property_path": match.group(1), "property_value": prop, "property_as_string": scalar(prop),
                             "texture_path": path, "texture": value, "provenance": None}
                    if not isinstance(value, str) or not value:
                        entry["unresolved"] = "empty_or_nonstring_texture"
                    else:
                        try:
                            entry["provenance"] = packages.locate(value)
                        except ValueError:
                            entry["unresolved"] = "unsafe_texture_path"
                        else:
                            if entry["provenance"] is None:
                                entry["unresolved"] = "texture_not_found_in_packages"
                    obj["properties"].append(entry)
                for path, value in sorted(flat.items()):
                    if path.endswith(("/mfm[1]", "/materialFile[1]")) and value:
                        obj["unresolved"].append({"reason": "external_material_not_resolved", "path": path, "value": value})
            visual_cache[name] = obj
            return obj

        def model(name, stack=()):
            if name in stack:
                return {"resource": name, "unresolved": [{"reason": "model_parent_cycle"}]}
            if len(stack) >= MAX_PARENT_DEPTH:
                return {"resource": name, "unresolved": [{"reason": "model_parent_depth_bound"}]}
            if name in model_cache:
                return model_cache[name]
            if len(model_cache) >= MAX_MODELS:
                raise ValueError("model count bound")
            obj = {"resource": name, "provenance": packages.locate(name), "visuals": [],
                   "parent": None, "unresolved": []}
            found = packages.read(name)
            if found is None:
                obj["unresolved"].append({"reason": "model_not_found_in_packages", "resource": name})
            else:
                raw, prov = found
                obj["provenance"] = dict(prov, sha256=_sha(raw))
                flat = _xml(raw)
                for path, value in sorted(flat.items()):
                    if re.fullmatch(r"/(?:nodefullVisual|nodelessVisual)\[\d+\]", path):
                        if isinstance(value, str) and value:
                            obj["visuals"].append({"field": path, "visual": visual(_extension(value, ".visual"))})
                        else:
                            obj["unresolved"].append({"reason": "invalid_visual_reference", "field": path, "value": value})
                parent = flat.get("/parent[1]")
                if isinstance(parent, str) and parent:
                    obj["parent"] = model(_extension(parent, ".model"), stack + (name,))
                if not obj["visuals"] and not obj["parent"]:
                    obj["unresolved"].append({"reason": "no_visual_or_parent"})
            model_cache[name] = obj
            return obj

        rows = []
        for vehicle_id, v in sorted(ussr.items()):
            source = v["source"]
            with (root / _safe_resource(source)).open("rb") as stream:
                raw = stream.read(MAX_XML + 1)
            if len(raw) > MAX_XML:
                raise ValueError("vehicle XML bound: " + source)
            expected = catalog.document["sources"].get(source)
            if not expected or _sha(raw) != expected["sha256"]:
                raise ValueError("vehicle source changed after catalogue read: " + source)
            flat = _xml(raw)
            row = {"vehicle_id": vehicle_id, "resource_name": v["resource_name"], "tier": v["tier"],
                   "tags": v["tags"], "secret": "secret" in v["tags"], "not_in_shop": v["not_in_shop"],
                   "historical_price": v["historical_price"],
                   "research_graph_incoming": [u for u in vehicle_unlocks if u["item_id"] == vehicle_id],
                   "research_graph_outgoing": [u for u in vehicle_unlocks if u["vehicle_id"] == vehicle_id],
                   "reachable_from_ms1_in_client_research_graph": vehicle_id in reachable,
                   "tree_ui_visibility": "UNKNOWN", "source": {"path": source, "sha256": _sha(raw)},
                   "models": [], "unresolved": []}
            for path, value in sorted(flat.items()):
                if not UNDAMAGED.search(path):
                    continue
                if not isinstance(value, str) or not value:
                    row["unresolved"].append({"reason": "invalid_undamaged_model", "path": path, "value": value})
                else:
                    try:
                        name = _extension(value, ".model")
                    except ValueError:
                        row["unresolved"].append({"reason": "unsafe_model_reference", "path": path, "value": value})
                    else:
                        row["models"].append({"source_path": path, "model": model(name)})
            if not row["models"]:
                row["unresolved"].append({"reason": "no_undamaged_model_in_vehicle_xml"})
            rows.append(row)
        return {"schema": "wot091-visual02-vehicle-mapping.v1", "target": "v.0.9.1 #717 RU",
                "scope": "USSR catalogue; vehicle XML undamaged model links; declared package paths; graph reachability ignores prerequisites; not loose overrides or runtime/UI proof",
                "paths_xml_sha256": packages.paths_sha256, "catalog_sha256": catalog.sha256,
                "packages": [p for p, _ in packages.packages], "vehicles": rows}
    finally:
        packages.close()
