# Explicit pinned map source for extended profile authoring

Scope: `tools/p06t_extended_profiles.py` and its existing test module only.
Branch `codex/p06t-profile-map-source` from
`200dcd221fb48c019b0939046ac38c18a85061dd`; actual tested runtime54f1c7f in
`C:/wot091-map-source74/w`. Documentation commits may descend from that runtime;
the925 runtime byte map is checked unchanged separately. The prepared primary
`C:/wot091-night-20261017-01/w` stays HEAD200/raw925; no merge was performed.

## VERIFIED problem and change

The extended source generator historically reads raw configs from fixed
`local/evidence/20261014-p05b-handling-fixes-01/pools-ms1-c17`. Its two raw pins
are unchanged:

* Karelia `73729757af1209b5093d1d3b271657b1c6e498322ad172d05e93d9bf9aec880c`;
* Prohorovka `0e4fe8ad2c1367254cf73bb91d055a0f980f00fac6a6014e110af13ec5b7dd64`.

The operational short-C closure intentionally relocates only `terrain.path`
and `obstacles.path` in those configs. All other parsed fields equal the D
originals. Its rawSHA necessarily differs, so the source-authoring test's
default directory conflicts with those valid operational documents. No source
geometry/RNG/native compatibility regression is established by that error.

`generate(original,out,poison=None,*,map_source=None)` now permits an explicit
read-only source directory; CLI adds `--map-source`. Absence still uses exactly
`MAP_BASE`. The loader reads only the two fixed filenames, no more than16KiB
each, using the unchanged pins and existing no-symlink/no-junction checks.
All map inputs are validated before output directory creation. There is no
fallback, JSON-source normalization, hash replacement or resource discovery.
Output retains the existing fresh workspace/local-only boundary.

The test context can explicitly supply `P06T_EXTENDED_MAP_SOURCE`; it passes
that argument without changing the default constant or raw hashes. Existing
physical/source assertions are retained. New negatives cover late wrong map
pin with no publication, oversize/missing/non-directory input and an actual
temporary NTFS junction. The default path-choice check uses exact source bytes
in an authored temporary directory; it does not qualify a physical scene.

## OBSERVED actual checks

Actual11 unittest cases passed with0fail/0error/0skip in0.398s. Actual CLI
`--map-source` also returned `PASS_SOURCE_PROJECTION_ONLY`. Both child groups
were assigned to the already-proven exact OwnJob43 before their gated commands
started; each completed with exit0 and ownJob active0. Native/SQL/network/
services/physics processes were not started. All925 branch runtime bytes and
primary200/raw925 stayed equal before/after. The two original D configs kept
their exact rawSHA before/after. No D output or client resource copy occurred.

Commands (run by the bounded own74 driver):

```text
P06T_EXTENDED_MAP_SOURCE=D:/WoT_9.1_Server/local/evidence/20261014-p05b-handling-fixes-01/pools-ms1-c17
P06T_EXTENDED_TEST_TAG=tests474
P06T_EXTENDED_TEST_OUT=C:/wot091-map-source74/w/local/evidence/map-source74-tests01
python -B -X utf8 -m unittest discover -s tests -p test_p06t_extended_profiles.py -v

python -B -X utf8 tools/p06t_extended_profiles.py --original-root C:/WoT_0.9.1_RU_0717_original --map-source D:/WoT_9.1_Server/local/evidence/20261014-p05b-handling-fixes-01/pools-ms1-c17 --out C:/wot091-map-source74/w/local/evidence/map-source74-cli01
```

These are environment values plus argv documentation, not shell-portable
assignment syntax. The driver uses a closed C-only environment, no inherited
PYTHONPATH, and fresh C output/temp directories.

External evidence prefix:
`C:/Users/NSNull/AppData/Local/Temp/wot091-night-workspace-kcadgetk/p06t-map-source74`.
An exact finite copy of the small helper/control/log/source-map proof is kept
at `C:/wot091-map-source74/w/local/evidence/20261017-p06t-map-source74` with an
exclusive manifest and source-before/after hashes. No original resources,
credentials, DB or executable payload is part of that copy.

* `base-copy-result.json`: initial raw925 equality, filtered Git blobs and
  parent tree equality; primary index/config remained unchanged.
* `actual01/{source-before,source-after,input-before}.json`: exact source and
  original input authorities, environment and driver pins.
* `actual01/unittest/{request,result,stdout.log,stderr.log}` and corresponding
  `actual01/cli`: actual commands, exit/Job accounting and hashed logs.
* `actual01/result.json` SHA
  `125a892e009d69cd14feda0f02d900c842db99290b20ec17119420e9d9e45a19`.

An initial syntax error in the external own driver occurred before any child,
test or CLI started and is retained in `driver-syntax-failure01.json`. It was
corrected before the actual successful run; production/test sources were not
changed to hide an execution failure.

## Limits, rollback and acceptance

Source projection outputs retain historical resource references present in the
selected raw inputs. They are not automatically a relocated/qualified scene;
actual Jolt getters, gateway build, native UI/gameplay and new stand activation
are NOT_RUN and are outside this small authoring card. The full primary Python
suite and its preserved failures remain independent.

No archive, cache, original client, database or prepared stand was modified.
Rollback is to retain/ignore this separate branch or revert its two source
files in a future integration; no data restore is required. Status:
PASS_EXPLICIT_PINNED_SOURCE_AUTHORING_COMPONENT_ONLY, review-ready dependent
branch. Sole next step: review the branch and decide later integration without
changing the frozen primary during current morning/suite acceptance.
