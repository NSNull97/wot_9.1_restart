# ORG-0A stale path inventory (2026-10-07)

Scan scope: tracked-source candidates and project documents under the project
root, excluding `.git/`, `local/` and both client copies. The scan searched for
`tools/wg_probe/src`, `tools/wg_probe/Cargo`,
`local/vendor/wg-toolkit-rs/target/debug`, `target/debug/p01-wg-probe`,
`client_original` and `client_work`.

The complete occurrence list (file, line, old path, canonical path and
classification), including all 22 entries of `server/layout.json`, is kept in
[ORG-0A_STALE_PATHS.tsv](../evidence-index/ORG-0A_STALE_PATHS.tsv).

## Canonical layout

`server/layout.json` is the path authority. The old source modules below are
relocated to `server/gateway/src/` and are not duplicated:

`login091.rs`, `redirect091.rs`, `baseapp091.rs`, `channel091.rs`,
`reliable091.rs`, `transport091.rs`, `capture091.rs`, `account091.rs`,
`hangar091.rs`, `identity091.rs`, `arena091.rs`, `arena_control091.rs`,
`arena_vehicle091.rs`, `arena_ready091.rs`, `arena_movement091.rs`,
`map_drive091.rs`, `map_drive_worker091.rs`, `map_drive_world091.rs`,
`map_drive_service091.rs`, `gateway091.rs`.

Only `tools/wg_probe/src/main.rs` remains in that historical crate directory.
The relocation map itself is intentional and is not a live-link defect.

## File-level inventory

### Deployed/legacy boundary intentionally retained

These are live or legacy launch boundaries whose old EXE path is deliberately
preserved; ORG-0A does not change the deployed service:

- `server/build.py`
- `server/control/service.py`
- `tools/check_baseapp_probe.py`
- `tools/check_channel_probe.py`
- `tools/check_gateway_probe.py`
- `tools/check_redirect_probe.py`
- `tools/check_server_reliable.py`
- `tools/gateway_suite.py`

The normal deployed EXE remains guarded by SHA256
`daef0dde9e012beac4e0f363bf66b672ec4a154473be4b05b00cfe4cc0608c3b`.

### Historical readers/verifiers — direct old-source reads, NOT_RUN after relocation

These tools still inspect frozen evidence or old source pins and must be
adapted in a separate card through `server/layout.json`; they are not used as
new native acceptance by ORG-0A:

- `tools/retired_base_probe.py`
- `tools/verify_inprocess_relogin.py`
- `tools/verify_ms1_ammo_native.py`
- `tools/verify_arena_space_native.py`
- `tools/verify_arena_movement_native.py`
- `tools/verify_arena_ready_native.py`
- `tools/verify_arena_vehicle_native.py`
- `tools/verify_avatar_base_native.py`

The full unittest run confirms three old-source `FileNotFoundError` errors
through account-switch, inprocess-relogin and retired-base tests; ORG-0B owns
their classification. Their new native rerun is NOT_RUN; the unit failures
are retained as FAIL.

### Historical documentation/commands

The following documents contain old commands, source names or absolute
research paths as historical reproduction records. They are not claims that
those paths are current live sources:

- `docs/research/INTEGRATION_SPIKES.md`
- `docs/research/OVERNIGHT_20261005_FILES.md`
- `docs/research/OVERNIGHT_20261005.md`
- `docs/research/P01_BOOTSTRAP_AND_NATIVE_LOGIN.md`
- `docs/research/P02_ACCOUNT_READY.md`
- `docs/research/P02_ARENA_MOVEMENT.md`
- `docs/research/P02_ARENA_READY.md`
- `docs/research/P02_BASEAPP_REPLY.md`
- `docs/research/P02_CHANNEL_ACK.md`
- `docs/research/P02_HANGAR.md`
- `docs/research/P02_LAB_GATEWAY.md`
- `docs/research/P02_LOGIN_REDIRECT.md`
- `docs/research/P02_MAP_DRIVE.md`
- `docs/research/P02_MS1_AMMO.md`
- `docs/research/P02_MS1_CREW.md`
- `docs/research/P02_NATIVE_ACCOUNT.md`
- `docs/research/P02_SERVER_RELIABLE.md`
- `docs/research/P02_SNIPER_CAMERA_PROTOCOL.md`
- `docs/research/P02_UNIFIED_ACCOUNT.md`
- `docs/research/REPRODUCE.md`

`local/vendor/...`, client roots and packet/capture outputs referenced by these
documents remain ignored local evidence. No external repository code, raw
client asset or executable was copied; provenance is recorded in
`EXTERNAL_REPOSITORIES_20261007.md`.

## Result

No live path was silently rewritten in ORG-0A. Current runtime ownership is
`server/layout.json`; historical direct readers are explicitly marked here and
remain a separate maintenance/ORG-0B concern.
