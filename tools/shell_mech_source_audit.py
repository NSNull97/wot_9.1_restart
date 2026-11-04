"""Read-only Packed XML field provenance for SHELL-MECH research.

Reuses packed_xml's bounded decoder; records zero-based, half-open RAW file
offsets, never executes bytecode or changes client resources. Output is confined
to a new file in this checkout's local/evidence/shell-mech-* directory.
This measures source data, not the historical server's combat algorithm.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import struct

try:
    from . import packed_xml
except ImportError:  # Direct CLI invocation.
    import packed_xml

MAX_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_FILES = 32
MAX_OUTPUT_BYTES = 32 * 1024 * 1024
MAX_FIELD_PATH = 4096
MAX_FIELD_PATH_TOTAL = 2 * 1024 * 1024
ROOT = Path(__file__).resolve().parents[1]


class AuditError(ValueError):
    """Invalid source, path, size or output boundary."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def no_links(path: Path) -> None:
    """Reject symlinks and Windows junctions, including ancestors."""
    for candidate in (path, *path.parents):
        if candidate.is_symlink() or candidate.is_junction():
            raise AuditError(f"linked path is forbidden: {candidate}")


def bounded_read(path: Path) -> bytes:
    no_links(path)
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_BYTES:
        raise AuditError("source must be a nonempty regular file <= 16 MiB")
    with path.open("rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    if not 0 < len(data) <= MAX_BYTES:
        raise AuditError("source grew beyond byte limit")
    return data


def field_offsets(data: bytes) -> list[dict]:
    """Return scalar values and their raw descriptors after decoder validation.

    Container own values use the same path as packed_xml.walk. Scalar leaves
    include empty/zero-byte fields. Repeated sibling tags are numbered from 1.
    A nested container in an own-value slot is explicitly unsupported here.
    """
    decoded = packed_xml.decode(data, max_bytes=MAX_BYTES)
    values, path_bytes = {}, 0
    for path, value in packed_xml.walk(decoded):
        if len(path) > MAX_FIELD_PATH:
            raise AuditError("logical field path length limit")
        path_bytes += len(path.encode("utf-8"))
        if path_bytes > MAX_FIELD_PATH_TOTAL:
            raise AuditError("aggregate logical field path limit")
        if path in values:
            raise AuditError("ambiguous logical field paths")
        values[path] = value
    names, position = [], 5
    while data[position] != 0:
        end = data.index(b"\0", position)
        names.append(data[position:end].decode("utf-8"))
        position = end + 1
    rows = []

    def add(path, descriptor, start, end, kind):
        key = path or "/"
        if key not in values:
            raise AuditError("offset traversal disagrees with bounded decoder")
        rows.append({"path": key, "kind": kind,
                     "descriptor_offset": descriptor, "value_start": start,
                     "value_end": end, "value_sha256": sha256(data[start:end]),
                     "value": values[key]})

    def element(start, end, path):
        count, own = struct.unpack_from("<HI", data, start)
        base = start + 6 + count * 6
        stop = own & 0x0fffffff
        if own >> 28 == 0:
            raise AuditError("nested container own value is unsupported")
        add(path, start + 2, base, base + stop, own >> 28)
        seen = {}
        for ordinal in range(count):
            entry = start + 6 + ordinal * 6
            index, descriptor = struct.unpack_from("<HI", data, entry)
            name = names[index]
            seen[name] = seen.get(name, 0) + 1
            child_path = path + "/" + name + f"[{seen[name]}]"
            next_stop = descriptor & 0x0fffffff
            a, b = base + stop, base + next_stop
            if descriptor >> 28 == 0:
                element(a, b, child_path)
            else:
                add(child_path, entry + 2, a, b, descriptor >> 28)
            stop = next_stop

    element(position + 1, len(data), "")
    if len(rows) != len(values) or set(values) != {row["path"] for row in rows}:
        raise AuditError("incomplete offset traversal")
    return rows


def source_path(client_root: Path, resource: str) -> Path:
    relative = PurePosixPath(resource)
    if (not resource or "\\" in resource or ":" in resource
            or relative.is_absolute() or ".." in relative.parts
            or not relative.parts or relative.parts[0] != "res"
            or relative.suffix.lower() not in (".xml", ".def")):
        raise AuditError("resource must be relative res/... Packed XML/DEF path")
    path = client_root.joinpath(*relative.parts)
    no_links(path)
    if not path.resolve().is_relative_to(client_root.resolve()):
        raise AuditError("resource escapes client root")
    return path


def audit(client_root: Path, resources: list[str], selects: list[str]) -> dict:
    client_root = client_root.absolute()
    no_links(client_root)
    if not client_root.is_dir():
        raise AuditError("client root directory missing")
    if not 1 <= len(resources) <= MAX_FILES or len(set(resources)) != len(resources):
        raise AuditError("require 1..32 distinct source paths")
    if len(selects) > 32 or any(not item or len(item) > 256 for item in selects):
        raise AuditError("require <= 32 nonempty bounded literal selectors")
    sources, total = [], 0
    for resource in resources:
        path = source_path(client_root, resource)
        # Check the aggregate budget before allocation; recheck actual length.
        if path.stat().st_size + total > MAX_TOTAL_BYTES:
            raise AuditError("aggregate source byte limit")
        data = bounded_read(path)
        total += len(data)
        if total > MAX_TOTAL_BYTES:
            raise AuditError("aggregate source byte limit")
        fields = field_offsets(data)
        selected = [row for row in fields if not selects or
                    any(token in row["path"] for token in selects)]
        sources.append({"resource": resource, "bytes": len(data),
                        "sha256": sha256(data), "fields_total": len(fields),
                        "fields_selected": len(selected), "fields": selected})
    return {"schema": "shell-mech-source-audit.v1", "client_root": str(client_root),
            "scope": "static Packed XML fields only; no build or server-law attestation",
            "offsets": "zero-based raw file bytes; [value_start, value_end)",
            "selectors": selects, "source_bytes": total, "sources": sources}


def write_receipt(receipt: dict, output: Path, root: Path = ROOT) -> None:
    root = root.absolute()
    output = output.absolute()
    no_links(root)
    no_links(output)
    try:
        relative = output.resolve().relative_to((root / "local/evidence").resolve())
    except ValueError as error:
        raise AuditError("output must stay in this checkout's local/evidence") from error
    if (len(relative.parts) < 2 or not relative.parts[0].startswith("shell-mech-")
            or relative.suffix != ".json" or output.exists()):
        raise AuditError("new JSON file under local/evidence/shell-mech-* required")
    encoded = (json.dumps(receipt, ensure_ascii=False, indent=2,
                          allow_nan=False) + "\n").encode("utf-8")
    if len(encoded) > MAX_OUTPUT_BYTES:
        raise AuditError("output byte limit")
    output.parent.mkdir(parents=True, exist_ok=True)
    no_links(output)
    with output.open("xb") as stream:
        stream.write(encoded)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-root", required=True, type=Path)
    parser.add_argument("--resource", action="append", required=True)
    parser.add_argument("--select", action="append", default=[])
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = audit(args.client_root, args.resource, args.select)
        write_receipt(result, args.out)
    except (AuditError, packed_xml.FormatError, OSError, UnicodeError,
            struct.error, ValueError) as error:
        parser.exit(2, f"SHELL-MECH source audit failed: {error}\n")
    print(json.dumps({"status": "PASS_STATIC_READ", "sources": len(result["sources"]),
                      "output": str(args.out), "source_bytes": result["source_bytes"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
