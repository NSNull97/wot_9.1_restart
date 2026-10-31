"""CAT-NATIONS: re-stamped copies of the P04M real-writer fixtures (TEST input only).

Source ``local/evidence/20261016-p04m-writer01/native-fixtures03/<name>`` is
read, never written. Each fixture is copied to
``local/evidence/20261031-cat-nations-restamp/p04m-native-fixtures03/<name>``
with the research catalogue hash ``b6baecd2...`` replaced by ``1f6b20d1...``;
every derived file SHA-256 that another member names is then replaced by the
same old->new map until nothing changes (as in commit 973fb95). Binary
members (state/shop/dossier) contain no catalogue hash and stay byte-identical.
The receipt records every source and output SHA. Existing output is refused.

    python -B -X utf8 tests/helpers/cat_nations_writer_fixture_restamp.py --root D:/WoT_9.1_Server
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from cat_nations_migrate import NEW, OLD  # noqa: E402

SOURCE = "local/evidence/20261016-p04m-writer01/native-fixtures03"
TARGET = "local/evidence/20261031-cat-nations-restamp/p04m-native-fixtures03"
NAMES = ("t26-ap160", "t34-full-crew", "t34-radioman-barracks", "t3485-full-crew")
MAX_FILE = 65536
MAX_FILES = 32


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def plain_dir(path):
    for q in (path, *path.parents):
        if q.exists() and (q.is_symlink() or q.is_junction()):
            raise ValueError("links refused: " + str(q))
    return path


def restamp(files):
    """files: name -> bytes. Returns (new files, old->new hash map)."""
    mapping = {OLD: NEW}
    for _ in range(MAX_FILES + 2):
        # Always rewrite from the source bytes so no intermediate hash survives.
        out = {}
        for name, raw in files.items():
            new = raw
            for old, replacement in mapping.items():
                new = new.replace(old.encode("ascii"), replacement.encode("ascii"))
            if len(new) != len(raw):
                raise ValueError("length changed: " + name)
            out[name] = new
        derived = {OLD: NEW, **{sha(files[n]): sha(out[n]) for n in files if out[n] != files[n]}}
        if derived == mapping:
            return out, mapping
        mapping = derived
    raise ValueError("hash map did not converge")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    root = Path(parser.parse_args().root).resolve(strict=True)
    target_base = plain_dir(root / TARGET)
    if target_base.exists():
        raise ValueError("output exists; refusing to overwrite: " + str(target_base))
    plan = []
    for name in NAMES:
        source = plain_dir(root / SOURCE / name)
        members = sorted(p for p in source.iterdir())
        if not 0 < len(members) <= MAX_FILES or any(not p.is_file() or p.is_symlink() for p in members):
            raise ValueError("plain bounded fixture dir required: " + str(source))
        files = {}
        for p in members:
            raw = p.read_bytes()
            if len(raw) > MAX_FILE:
                raise ValueError("member bound: " + str(p))
            files[p.name] = raw
        if not any(OLD.encode("ascii") in raw for raw in files.values()):
            raise ValueError("fixture does not name the old catalogue: " + name)
        new, mapping = restamp(files)
        if any(OLD.encode("ascii") in raw for raw in new.values()):
            raise ValueError("old catalogue remains: " + name)
        plan.append((name, files, new, mapping))
    target_base.mkdir(parents=True)
    receipt = dict(schema="cat-nations-writer-fixture-restamp.v1", source=SOURCE, target=TARGET,
                   catalog=dict(old=OLD, new=NEW), fixtures=[], source_unchanged=True)
    for name, files, new, mapping in plan:
        directory = target_base / name
        directory.mkdir()
        for member, raw in sorted(new.items()):
            with (directory / member).open("xb") as stream:
                stream.write(raw)
        receipt["fixtures"].append(dict(name=name, hash_map=dict(sorted(mapping.items())),
            files=[dict(file=m, source_sha256=sha(files[m]), sha256=sha(new[m]), restamped=files[m] != new[m])
                   for m in sorted(new)]))
    for name, files, _, _ in plan:
        for member, raw in files.items():
            if (root / SOURCE / name / member).read_bytes() != raw:
                raise ValueError("source changed during restamp")
    with (target_base.parent / "receipt.json").open("x", encoding="ascii") as stream:
        stream.write(json.dumps(receipt, sort_keys=True, indent=1) + "\n")
    print(json.dumps(dict(status="PASS", target=str(target_base),
                          changed={f["name"]: [x["file"] for x in f["files"] if x["restamped"]] for f in receipt["fixtures"]})))


if __name__ == "__main__":
    main()
