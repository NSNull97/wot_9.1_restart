"""BATTLE-ANY stage 3d: tankman passport sources of every #717 nation.

Reads `res/scripts/item_defs/tankmen/<nation>.xml` of the original client as
packed XML data only (no client code runs), pins each file by bytes and SHA-256
and writes `config/catalog/tankman_passports.v1.json`: per nation its native ID
(`nations.pyc` order, as BATTLE-ANY), the descriptor header `8 + (nation << 4)`
(VERIFIED in P04H), the exact ID sets of the single normal passport group
(`normalGroups/men1`) as inclusive ranges, and the role rank indices at 50/100%.

Commands: `build --original C` (writes the table; refuses to change it without
`--update`), `check` (no client; canonical bytes and self-consistency).
The project's deterministic passport allocation over these sets is a test_lab
rule (P04H), not the original random generator.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
from packed_xml import decode, walk

TABLE = ROOT / "config/catalog/tankman_passports.v1.json"
SCHEMA = "wot091-tankman-passports.v1"
# Original nations.pyc order (verified in BATTLE-ANY stage 1, as P06T).
NATIONS = ("ussr", "germany", "usa", "china", "france", "uk", "japan")
ROLES = ("commander", "gunner", "driver", "radioman", "loader")
FIELDS = ("firstNames", "lastNames", "icons")
MAX_SOURCE = 256 * 1024
MAX_TABLE = 64 * 1024
GROUP = "/normalGroups[1]/men1[1]"
# P04H VERIFIED for USSR; build requires the same initial indices for every nation.
INITIAL_RANKS = {"commander": [2, 3], "gunner": [1, 2], "driver": [1, 2], "radioman": [0, 1], "loader": [0, 1]}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def ranges(values):
    out = []
    for v in values:
        if out and v == out[-1][1] + 1:
            out[-1][1] = v
        else:
            out.append([v, v])
    return out


def nation_row(nation_id, nation, raw):
    x = dict(walk(decode(raw, max_bytes=MAX_SOURCE, max_depth=24, max_nodes=60000)))
    groups = [p for p in x if re.fullmatch(r"/normalGroups\[1\]/[^/]+\[1\]", p)]
    require(groups == [GROUP], nation + ": exactly one normal passport group men1")
    sex = x[GROUP + "/sex[1]"]
    require((sex.get("base64") if isinstance(sex, dict) else sex) == "male" and x[GROUP + "/weight[1]"] == "1.0",
            nation + ": men1 sex/weight")
    ids = {}
    for key in FIELDS:
        prefix = GROUP + "/" + key + "[1]/_"
        values = sorted(int(p[len(prefix):-3]) for p in x
                        if p.startswith(prefix) and re.fullmatch(r"[0-9]+\[1\]", p[len(prefix):]))
        require(values and values[0] >= 1 and values[-1] <= 65535 and len(set(values)) == len(values), nation + ": " + key)
        ids[key] = dict(count=len(values), ranges=ranges(values))
    ranks = [re.fullmatch(r"/ranks\[1\]/([^/]+)\[1\]", p).group(1) for p in x if re.fullmatch(r"/ranks\[1\]/([^/]+)\[1\]", p)]
    require(len(ranks) == 11, nation + ": rank count")
    role_ranks = {r: [ranks.index(v) for v in x["/roleRanks[1]/" + r + "[1]"].split()[:2]] for r in ROLES}
    require(role_ranks == INITIAL_RANKS, nation + ": initial role rank indices differ from P04H")
    return dict(nation=nation, nation_id=nation_id, header=8 + (nation_id << 4),
                source=dict(path="res/scripts/item_defs/tankmen/" + nation + ".xml", bytes=len(raw), sha256=sha(raw)),
                group="normalGroups/men1", first_names=ids["firstNames"], last_names=ids["lastNames"], icons=ids["icons"],
                role_rank_ids_level50={r: v[0] for r, v in role_ranks.items()},
                role_rank_ids_level100={r: v[1] for r, v in role_ranks.items()})


def build(original):
    base = Path(original) / "res/scripts/item_defs/tankmen"
    rows = []
    for nation_id, nation in enumerate(NATIONS):
        path = base / (nation + ".xml")
        require(path.is_file() and not path.is_symlink() and 0 < path.stat().st_size <= MAX_SOURCE, nation + ": source file")
        rows.append(nation_row(nation_id, nation, path.read_bytes()))
    return dict(schema=SCHEMA, target="v.0.9.1 #717 RU", classification="VERIFIED_STATIC_PINNED_SOURCE",
                allocation="test_lab deterministic: n-th identity takes ID index (n-1) mod count per set (P04H rule)",
                nations=rows)


def check(path=TABLE):
    raw = path.read_bytes()
    require(0 < len(raw) <= MAX_TABLE, "table size")
    table = json.loads(raw)
    require(canonical(table) + b"\n" == raw and table["schema"] == SCHEMA, "canonical table")
    require([r["nation"] for r in table["nations"]] == list(NATIONS), "nation order")
    for row in table["nations"]:
        require(row["header"] == 8 + (row["nation_id"] << 4) and row["nation_id"] == NATIONS.index(row["nation"]), "header")
        for key in ("first_names", "last_names", "icons"):
            r = row[key]["ranges"]
            require(sum(b - a + 1 for a, b in r) == row[key]["count"] and all(a <= b for a, b in r)
                    and all(r[i][1] + 1 < r[i + 1][0] for i in range(len(r) - 1)), "ranges " + key)
    return dict(status="PASS", sha256=sha(raw), nations=len(table["nations"]))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build")
    b.add_argument("--original", type=Path, required=True)
    b.add_argument("--update", action="store_true")
    sub.add_parser("check")
    args = parser.parse_args(argv)
    if args.command == "build":
        raw = canonical(build(args.original)) + b"\n"
        require(len(raw) <= MAX_TABLE, "table bound")
        if TABLE.exists() and TABLE.read_bytes() != raw:
            require(args.update, "committed table differs; pass --update to replace it")
        TABLE.write_bytes(raw)
    print(json.dumps(check()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
