# P02 source-bundle to shared profile13 native battle

## Goal
Run one bounded native two-client battle through the already accepted `legacy091-profile13` shared-world route while requiring the portable source-bundle to verify the primary owner identity. The bundle is a provenance guard; profile13 reservation/FrozenLoadout remains authoritative for battle state.

## Scope
- Add an explicit `legacy091-profile13-source-bundle` command with the existing profile13 arguments plus a bundle root.
- Canonicalize and verify the bundle under `config.local_root` before binding sockets.
- On authenticated primary owner admission, load and validate the bundle seed and log a hash-anchored verification marker. Other profile13 owners continue through the existing shared reservation path.
- Keep the existing `legacy091-profile13` command and state machine unchanged.
- Run one bounded native two-client Prokhorovka battle and record gateway/client/capture evidence.

## Acceptance
- Rust CLI and shared-server tests/build pass.
- Gateway log contains startup bundle verification and per-owner verification for the primary account.
- Native evidence reaches shared battle entry and records at least one real battle snapshot/impact or terminal lifecycle marker; no claim beyond captured evidence.
- No original client or external service is modified.
