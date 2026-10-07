"""Audit a bounded static research-tree ownership/visibility fixture.

This is a read-only Phase A receipt.  It reads the test-lab ``state.bin`` and
``shop.bin`` with the literal decoder used by the existing independent native
verifiers.  It never uses pickle/unpickle, imports client code, starts a
service, or treats a fixture as proof of native tree visibility.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

try:  # Running from the repository root (the normal test path).
    from tools.research_tree_audit import ResearchTreeAuditError, audit as audit_graph
except ImportError:  # Running the file directly from tools/.
    from research_tree_audit import ResearchTreeAuditError, audit as audit_graph

# verify_hangar intentionally uses sibling imports (client_audit, etc.)
# because the existing verifiers are also runnable as standalone tools.  Add
# only that local tools directory; no client or untrusted data is imported.
_TOOL_DIR = str(Path(__file__).resolve().parent)
if _TOOL_DIR not in sys.path:
    sys.path.insert(0, _TOOL_DIR)
from verify_hangar import literal


MAX_JSON_BYTES = 256 * 1024
MAX_LITERAL_BYTES = 16 * 1024
MAX_ITEMS = 4096
MAX_DEPTH = 24
MAX_INT = 2_147_483_647
TARGETS = {
    3329: ("ussr-ms-1", "MS-1"),
    7169: ("ussr-is-7", "IS-7"),
}


class VisibilityMatrixError(ValueError):
    """The static fixture is malformed or outside the bounded contract."""


def _reject_constant(value: str) -> Any:
    raise VisibilityMatrixError(f"non-finite JSON constant: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise VisibilityMatrixError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _walk_depth(value: Any, level: int = 0) -> None:
    if level > MAX_DEPTH:
        raise VisibilityMatrixError("JSON nesting exceeds bounds")
    if isinstance(value, dict):
        if len(value) > MAX_ITEMS:
            raise VisibilityMatrixError("JSON object exceeds item bound")
        for key, child in value.items():
            if not isinstance(key, str):
                raise VisibilityMatrixError("JSON object key must be text")
            _walk_depth(child, level + 1)
    elif isinstance(value, list):
        if len(value) > MAX_ITEMS:
            raise VisibilityMatrixError("JSON list exceeds item bound")
        for child in value:
            _walk_depth(child, level + 1)


def _json_file(path: Path) -> tuple[dict[str, Any], str]:
    raw = _read_file(path, MAX_JSON_BYTES)
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                           parse_constant=_reject_constant)
    except VisibilityMatrixError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise VisibilityMatrixError(f"bounded UTF-8 JSON required: {path}") from error
    if not isinstance(value, dict):
        raise VisibilityMatrixError(f"JSON root must be an object: {path}")
    _walk_depth(value)
    return value, hashlib.sha256(raw).hexdigest()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _bounded_path(path: str | Path, root: Path, *, must_exist: bool = True) -> Path:
    """Resolve a path and require it to stay in root; reject links."""
    root = root.resolve(strict=True)
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    # Check every existing component before resolve(); checking only the
    # resolved result would erase the evidence that a symlink/junction was
    # supplied and would make the path-boundary negative control ineffective.
    probe = candidate
    while probe != probe.parent:
        if probe.exists() and (probe.is_symlink() or getattr(probe, "is_junction", lambda: False)()):
            raise VisibilityMatrixError(f"source links are forbidden: {probe}")
        probe = probe.parent
    candidate = candidate.resolve(strict=must_exist)
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise VisibilityMatrixError(f"path escapes repository root: {candidate}") from error
    if must_exist and not candidate.is_file() and not candidate.is_dir():
        raise VisibilityMatrixError(f"missing source: {candidate}")
    return candidate


def _read_file(path: Path, maximum: int) -> bytes:
    if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
        raise VisibilityMatrixError(f"source links are forbidden: {path}")
    try:
        info = path.stat()
        if not path.is_file() or info.st_size <= 0 or info.st_size > maximum:
            raise VisibilityMatrixError(f"source size/type is outside bounds: {path}")
        raw = path.read_bytes()
    except OSError as error:
        raise VisibilityMatrixError(f"source is not readable: {path}") from error
    if len(raw) != info.st_size:
        raise VisibilityMatrixError(f"source changed while reading: {path}")
    return raw


def _integer(value: Any, label: str, lower: int = 1, upper: int = MAX_INT) -> int:
    if type(value) is not int or not lower <= value <= upper:
        raise VisibilityMatrixError(f"{label}: bounded integer required")
    return value


def _descriptor_ids(path: Path) -> set[int]:
    value, _ = _json_file(path)
    vehicle = value.get("vehicle")
    if not isinstance(vehicle, dict):
        raise VisibilityMatrixError(f"descriptor vehicle object missing: {path}")
    result = {_integer(vehicle.get("type_compact_descr"), "vehicle type compact descriptor")}
    components = vehicle.get("components")
    if not isinstance(components, dict) or not 1 <= len(components) <= 32:
        raise VisibilityMatrixError(f"descriptor components outside bounds: {path}")
    for component, row in components.items():
        if not isinstance(component, str) or not isinstance(row, dict):
            raise VisibilityMatrixError(f"descriptor component malformed: {path}")
        result.add(_integer(row.get("compact_descr"), f"{component} compact descriptor"))
    return result


def _validate_manifest_files(fixture: Path, manifest: dict[str, Any]) -> dict[str, str]:
    rows = manifest.get("files")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 32:
        raise VisibilityMatrixError("fixture manifest files outside bounds")
    hashes: dict[str, str] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) - {"file", "bytes", "sha256", "opcodes"}:
            raise VisibilityMatrixError(f"manifest files[{index}] shape")
        name = row.get("file")
        if not isinstance(name, str) or not name or Path(name).name != name:
            raise VisibilityMatrixError("manifest file path must be a single filename")
        if name in hashes:
            raise VisibilityMatrixError(f"duplicate manifest file: {name}")
        expected_bytes = _integer(row.get("bytes"), f"manifest {name} bytes", 1, MAX_LITERAL_BYTES)
        expected_sha = row.get("sha256")
        if not isinstance(expected_sha, str) or len(expected_sha) != 64:
            raise VisibilityMatrixError(f"manifest {name} SHA shape")
        path = _bounded_path(fixture / name, fixture)
        raw = _read_file(path, MAX_LITERAL_BYTES)
        if len(raw) != expected_bytes or hashlib.sha256(raw).hexdigest() != expected_sha:
            raise VisibilityMatrixError(f"manifest hash mismatch: {name}")
        hashes[name] = expected_sha
    required = {"state.bin", "shop.bin", "dossier.bin"}
    if set(hashes) != required:
        raise VisibilityMatrixError("fixture manifest file set differs")
    return hashes


def _literal_file(fixture: Path, name: str) -> tuple[Any, str]:
    path = _bounded_path(fixture / name, fixture)
    raw = _read_file(path, MAX_LITERAL_BYTES)
    try:
        value = literal(raw)
    except (ValueError, TypeError, OverflowError) as error:
        raise VisibilityMatrixError(f"malformed literal: {name}") from error
    return value, hashlib.sha256(raw).hexdigest()


def _fixture_matrix(fixture: Path, repository_root: Path) -> dict[str, Any]:
    manifest, manifest_sha256 = _json_file(_bounded_path(fixture / "manifest.json", fixture))
    if manifest.get("fixture_version") not in (2, 3) or manifest.get("ruleset") != "test_lab":
        raise VisibilityMatrixError("fixture version/ruleset outside P09A static contract")
    _validate_manifest_files(fixture, manifest)
    state, state_sha256 = _literal_file(fixture, "state.bin")
    shop, shop_sha256 = _literal_file(fixture, "shop.bin")
    if not isinstance(state, dict) or not isinstance(shop, dict):
        raise VisibilityMatrixError("state/shop literal root must be a mapping")
    inventory = state.get(b"inventory")
    if not isinstance(inventory, dict) or not 1 <= len(inventory) <= 32:
        raise VisibilityMatrixError("state inventory outside bounds")
    shop_items = shop.get(b"items")
    if not isinstance(shop_items, dict):
        raise VisibilityMatrixError("shop items mapping missing")
    item_prices = shop_items.get(b"itemPrices")
    hidden = shop_items.get(b"notInShopItems")
    if not isinstance(item_prices, dict) or not 1 <= len(item_prices) <= MAX_ITEMS:
        raise VisibilityMatrixError("itemPrices outside bounds")
    if not isinstance(hidden, list) or len(hidden) > MAX_ITEMS:
        raise VisibilityMatrixError("notInShopItems outside bounds")
    hidden_ids: list[int] = []
    for index, compact_descr in enumerate(hidden):
        compact_descr = _integer(compact_descr, f"notInShopItems[{index}]")
        if compact_descr in hidden_ids:
            raise VisibilityMatrixError(f"duplicate notInShopItems ID: {compact_descr}")
        hidden_ids.append(compact_descr)
    for compact_descr, price in item_prices.items():
        _integer(compact_descr, "itemPrices compact descriptor")
        if not isinstance(price, tuple) or len(price) != 2 or any(
                type(value) is not int or not 0 <= value <= MAX_INT for value in price):
            raise VisibilityMatrixError("itemPrices value outside bounds")

    compatibility, compatibility_sha256 = _json_file(
        _bounded_path(fixture / "compatibility.json", fixture))
    mapping = compatibility.get("vehicle_mapping")
    if not isinstance(mapping, list) or not 1 <= len(mapping) <= 32:
        raise VisibilityMatrixError("compatibility vehicle mapping outside bounds")
    by_cd: dict[int, dict[str, Any]] = {}
    for row in mapping:
        if not isinstance(row, dict):
            raise VisibilityMatrixError("compatibility vehicle mapping row malformed")
        cd = _integer(row.get("type_compact_descr"), "compatibility type descriptor")
        if cd in by_cd:
            raise VisibilityMatrixError(f"duplicate compatibility descriptor: {cd}")
        native_id = _integer(row.get("native_inventory_id"), "compatibility native inventory ID")
        by_cd[cd] = {"native_inventory_id": native_id, "inventory_id": row.get("inventory_id")}

    descriptor_sources = manifest.get("native_descriptors")
    if not isinstance(descriptor_sources, dict):
        raise VisibilityMatrixError("native descriptor manifest missing")
    allowed_ids: set[int] = set()
    descriptor_hashes: dict[str, str] = {}
    for name in ("ms1", "is7"):
        source = descriptor_sources.get(name)
        if not isinstance(source, dict) or not isinstance(source.get("file"), str):
            raise VisibilityMatrixError(f"descriptor manifest entry missing: {name}")
        descriptor_path = _bounded_path(source["file"], repository_root)
        raw = _read_file(descriptor_path, MAX_JSON_BYTES)
        expected_sha = source.get("sha256")
        if not isinstance(expected_sha, str) or hashlib.sha256(raw).hexdigest() != expected_sha:
            raise VisibilityMatrixError(f"descriptor hash mismatch: {name}")
        descriptor_hashes[name] = expected_sha
        allowed_ids.update(_descriptor_ids(descriptor_path))
    unknown = (set(item_prices) | set(hidden_ids)) - allowed_ids
    if unknown:
        raise VisibilityMatrixError(f"unknown compact descriptor IDs: {sorted(unknown)}")

    rows = []
    for compact_descr, (vehicle_id, display_name) in TARGETS.items():
        mapping_row = by_cd.get(compact_descr)
        if mapping_row is None:
            raise VisibilityMatrixError(f"target descriptor absent from compatibility: {compact_descr}")
        native_inventory_id = mapping_row["native_inventory_id"]
        # The fixture's vehicle collection is the documented state inventory
        # row 1; row 8 is tankmen and can reuse slots 1/2 with a different
        # descriptor format.  Keep this explicit so those two namespaces are
        # never conflated.
        state_inventory_id = 1
        state_row = inventory.get(state_inventory_id)
        if not isinstance(state_row, dict):
            raise VisibilityMatrixError("state vehicle inventory row missing")
        descriptors = state_row.get(b"compDescr")
        if not isinstance(descriptors, dict) or native_inventory_id not in descriptors:
            raise VisibilityMatrixError(f"state compDescr slot missing: {native_inventory_id}")
        # Presence is deliberately derived from state.compDescr, not from the
        # higher-level JSON profile or the requested matrix row.
        inventory_presence = True
        rows.append({
            "vehicle_id": vehicle_id,
            "display_name": display_name,
            "compact_descr": compact_descr,
            "native_inventory_id": native_inventory_id,
            "state_inventory_id": state_inventory_id,
            "inventory_presence": inventory_presence,
            "inventory_comp_descr_slots": sorted(
                _integer(slot, "state compDescr slot") for slot in descriptors
            ),
            "itemPrices_presence": compact_descr in item_prices,
            "notInShop_membership": compact_descr in hidden_ids,
            "expected_native_visibility": "UNKNOWN",
            "runtime_eligibility": "NOT_RUN",
        })

    return {
        "fixture_manifest_sha256": manifest_sha256,
        "state_sha256": state_sha256,
        "shop_sha256": shop_sha256,
        "compatibility_sha256": compatibility_sha256,
        "descriptor_sha256": descriptor_hashes,
        "account_id": manifest.get("account_id"),
        "snapshot_revision": manifest.get("snapshot_revision"),
        "rows": rows,
        "unowned_reference": {
            "available": False,
            "status": "NOT_AVAILABLE_IN_FIXTURE",
            "source": "fixture inventory and compatibility vehicle_mapping",
            "reason": "fixture contains owned MS-1 and explicit IS-7 grant only",
        },
    }


def audit(catalog_path: str | Path, research_path: str | Path, fixture_path: str | Path,
          *, repository_root: str | Path | None = None) -> dict[str, Any]:
    root = Path(repository_root).resolve() if repository_root else _repo_root()
    root = _bounded_path(root, root)
    catalog = _bounded_path(catalog_path, root)
    research = _bounded_path(research_path, root)
    fixture = _bounded_path(fixture_path, root)
    if not fixture.is_dir():
        raise VisibilityMatrixError("fixture path must be a directory")
    try:
        graph = audit_graph(catalog, research)
    except (ResearchTreeAuditError, OSError, ValueError) as error:
        raise VisibilityMatrixError(f"static graph/catalog audit rejected: {error}") from error
    matrix = _fixture_matrix(fixture, root)
    if matrix["account_id"] is not None and not isinstance(matrix["account_id"], str):
        raise VisibilityMatrixError("fixture account_id shape")
    return {
        "status": "PASS_STATIC_FIXTURE_VISIBILITY_MATRIX",
        "schema": "research-tree-visibility-matrix.v1",
        "scope": "P09A Phase A static fixture only",
        "catalog": {
            "status": graph["status"],
            "catalog_sha256": graph["catalog_sha256"],
            "research_sha256": graph["research_sha256"],
            "tree_count": graph["tree_count"],
            "node_count": graph["node_count"],
            "edge_count": graph["edge_count"],
            "ussr_tiers": graph["ussr_tiers"],
            "is8_to_is7": graph["is8_to_is7"],
            "is7_vehicle_edges": graph["is7_vehicle_edges"],
        },
        "fixture": matrix,
        "native_visibility": "UNKNOWN",
        "runtime_eligibility": "NOT_RUN",
        "native_payload": "NOT_RUN",
        "visual_handoff": "NOT_RUN",
    }


def _write_receipt(path: Path, report: dict[str, Any], root: Path) -> None:
    output = _bounded_path(path, root, must_exist=False)
    if output.exists() and (output.is_symlink() or getattr(output, "is_junction", lambda: False)()):
        raise VisibilityMatrixError("output links are forbidden")
    output.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(raw) > 64 * 1024:
        raise VisibilityMatrixError("receipt exceeds output bound")
    output.write_bytes(raw + b"\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", default="web/data/catalog.v1.json")
    parser.add_argument("--research", default="web/data/catalog-research.v1.json")
    parser.add_argument("--fixture", default="local/server/fixtures/c5326cc1-8524-479c-8bba-72e973489c22/r3-catalog3")
    parser.add_argument("--repository-root", help="repository root for path bounds (defaults to this checkout)")
    parser.add_argument("--out")
    args = parser.parse_args()
    root = Path(args.repository_root).resolve() if args.repository_root else _repo_root()
    try:
        report = audit(args.catalog, args.research, args.fixture, repository_root=root)
        if args.out:
            _write_receipt(Path(args.out), report, root)
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    except (VisibilityMatrixError, OSError) as error:
        raise SystemExit(f"research tree visibility matrix rejected: {error}")


if __name__ == "__main__":
    main()
