"""SHELL-CFG: build the immutable shell rules snapshot from the profile layers.

Layers (config/shell_rules/, order of Shell Mechanics 2.0 section 2):
server_defaults -> historical_0_9_1 -> classic_plus -> shell_type ->
shell_definition -> gun_vehicle -> game_mode. A later layer replaces a leaf of an
earlier one. Every leaf is {"value", "status", "source"}; the schema is closed
(unknown key, wrong type or a bound outside SCHEMA is refused). Layers whose
override scope has no schema yet (shell type, shell definition, gun/vehicle,
game mode) must be empty.

The snapshot (config/shell_rules/snapshot.json) is canonical JSON + LF; its
SHA-256 is rulesHash. The gateway embeds the bytes and their pin
(server/gateway/src/shared/shell_rules_pins.rs).

    python tools/shell_rules.py build   # write snapshot + pins
    python tools/shell_rules.py check   # rebuild and compare bytes
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "config" / "shell_rules"
SNAPSHOT = DIR / "snapshot.json"
PINS = ROOT / "server" / "gateway" / "src" / "shared" / "shell_rules_pins.rs"
PROFILE_SCHEMA = "wot091-shell-rules-profile.v1"
SNAPSHOT_SCHEMA = "wot091-shell-rules.v1"
LAYERS = ("server_defaults", "historical_0_9_1", "classic_plus", "shell_type", "shell_definition", "gun_vehicle", "game_mode")
EMPTY_ONLY = ("shell_type", "shell_definition", "gun_vehicle", "game_mode")
STATUSES = ("verified_091", "test_lab", "requires_verification", "experimental")
MAX_FILE = 64 * 1024
MAX_SOURCE = 512


def angle(nullable=False):
    return ("number", 0.0, 90.0, nullable)


FAMILY = {"normalization_deg": angle(), "ricochet_deg": angle(True), "caliber_rules": ("bool",),
          "distance_falloff": ("bool",)}
SCHEMA = {
    "laws": {"direct": ("law",), "track": ("law",), "unarmored_device": ("law",)},
    "families": {name: FAMILY for name in ("armor_piercing", "armor_piercing_cr", "hollow_charge", "high_explosive")},
    "caliber": {"normalization_ratio": ("number", 1.0, 20.0, False), "normalization_multiplier": ("number", 0.0, 10.0, False),
                "no_ricochet_ratio": ("number", 1.0, 20.0, False)},
    "falloff": {"full_power_until_m": ("number", 0.0, 1000.0, False), "linear_span_m": ("number", 1.0, 2000.0, False)},
    "high_explosive": {"damage_factor": ("number", 0.0, 1.0, False), "armor_factor": ("number", 0.0, 10.0, False)},
}


class RulesError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise RulesError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii") + b"\n"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_json(path):
    raw = Path(path).read_bytes()
    require(0 < len(raw) <= MAX_FILE, "file bound: " + Path(path).name)
    return json.loads(raw), raw.replace(b"\r\n", b"\n")


def is_leaf(value):
    return isinstance(value, dict) and "value" in value


def check_leaf(path, spec, leaf):
    require(isinstance(leaf, dict) and set(leaf) == {"value", "status", "source"}, path + ": leaf needs value/status/source")
    require(leaf["status"] in STATUSES, path + ": unknown status")
    require(type(leaf["source"]) is str and 0 < len(leaf["source"]) <= MAX_SOURCE, path + ": source")
    value, kind = leaf["value"], spec[0]
    if kind == "bool":
        require(type(value) is bool, path + ": bool required")
    elif kind == "law":
        require(type(value) is str and value.startswith(("test_lab.", "project.", "wot091.")) and len(value) <= 128,
                path + ": law id")
    else:
        _, low, high, nullable = spec
        if value is None:
            require(nullable, path + ": null not allowed")
        else:
            require(type(value) in (int, float) and not isinstance(value, bool) and math.isfinite(value)
                    and low <= value <= high, path + ": number bound")


def check_partial(path, schema, value):
    """A layer: any subset of the schema tree, leaves fully specified."""
    require(isinstance(value, dict), path + ": object required")
    for key, item in value.items():
        require(key in schema, path + ": unknown key " + key)
        if isinstance(schema[key], tuple):
            check_leaf(path + "." + key, schema[key], item)
        else:
            require(not is_leaf(item), path + "." + key + ": section expected")
            check_partial(path + "." + key, schema[key], item)


def check_complete(path, schema, value):
    require(isinstance(value, dict) and set(value) == set(schema), path + ": incomplete or extra keys")
    for key, spec in schema.items():
        if isinstance(spec, tuple):
            check_leaf(path + "." + key, spec, value[key])
        else:
            check_complete(path + "." + key, spec, value[key])


def merge(base, layer):
    out = copy.deepcopy(base)
    for key, item in layer.items():
        if is_leaf(item) or key not in out:
            out[key] = copy.deepcopy(item)
        else:
            out[key] = merge(out[key], item)
    return out


def build_snapshot(directory=DIR):
    directory = Path(directory)
    profile, _ = read_json(directory / "profile.json")
    require(isinstance(profile, dict) and set(profile) == {"schema", "config_version", "profile", "historical_baseline", "note", "layers"},
            "profile keys")
    require(profile["schema"] == PROFILE_SCHEMA and type(profile["config_version"]) is int and 1 <= profile["config_version"] <= 2**31 - 1,
            "profile schema/config_version")
    require(profile["profile"] == "classic_plus" and profile["historical_baseline"] == "wot_0_9_1", "profile identity")
    require(tuple(profile["layers"]) == LAYERS, "layer order must be the Shell Mechanics 2.0 order")
    rules, layers = {}, []
    for name in LAYERS:
        layer, raw = read_json(directory / (name + ".json"))
        require(isinstance(layer, dict) and set(layer) == {"layer", "rules"} and layer["layer"] == name, name + ": layer header")
        check_partial(name, SCHEMA, layer["rules"])
        require(name not in EMPTY_ONLY or layer["rules"] == {}, name + ": override scope has no schema yet; keep it empty")
        rules = merge(rules, layer["rules"])
        layers.append({"name": name, "sha256": sha(raw)})
    check_complete("rules", SCHEMA, rules)
    snapshot = {"schema": SNAPSHOT_SCHEMA, "config_version": profile["config_version"], "profile": profile["profile"],
                "historical_baseline": profile["historical_baseline"], "layers": layers, "rules": rules}
    return canonical(snapshot)


def rust_pins(raw):
    snapshot = json.loads(raw)
    lines = ("// GENERATED by tools/shell_rules.py; do not edit. Exact-byte pin of the embedded",
             "// config/shell_rules/snapshot.json (rulesHash) and its configVersion.",
             'pub const RULES_SHA256:&str="%s";' % sha(raw),
             "pub const CONFIG_VERSION:u32=%d;" % snapshot["config_version"])
    return ("\n".join(lines) + "\n").encode("ascii")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("build", "check"))
    args = parser.parse_args(argv)
    try:
        raw = build_snapshot()
        if args.command == "build":
            SNAPSHOT.write_bytes(raw)
            PINS.write_bytes(rust_pins(raw))
        else:
            require(SNAPSHOT.read_bytes() == raw, "snapshot.json differs from the layers (run build)")
            require(PINS.read_bytes() == rust_pins(raw), "shell_rules_pins.rs differs (run build)")
        print(json.dumps({"status": "PASS", "command": args.command, "rules_sha256": sha(raw),
                          "config_version": json.loads(raw)["config_version"]}))
        return 0
    except (OSError, ValueError, KeyError) as error:
        print(json.dumps({"status": "FAIL_SHELL_RULES", "reason": str(error)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
