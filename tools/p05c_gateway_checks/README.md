# Local P05C gateway check harness

This small Cargo manifest compiles the actual `server/gateway/src/main.rs` from
an isolated worktree against the explicitly approved dependency checkout at
`D:/WoT_9.1_Server/local/vendor/wg-toolkit-rs/wg-toolkit`. It does not copy or link
client resources, vendor sources or toolchains. The production Cargo manifest is
unchanged. Existing resource-heavy gateway tests still require the canonical
checkout; this harness is for focused P05C/core compilation and tests.

Use the Rust1.90 GNU environment described in `docs/DEV_NOTES.md`, set
`WOT091_ROOT=D:/WoT_9.1_Server`, and run:

```powershell
cargo test --offline --manifest-path tools/p05c_gateway_checks/Cargo.toml --no-run
cargo test --offline --manifest-path tools/p05c_gateway_checks/Cargo.toml p05c_ -- --test-threads=1
cargo test --offline --manifest-path tools/p05c_gateway_checks/Cargo.toml model::scene_tests -- --test-threads=1
```

The actual runtime test reads the pinned resource references from the existing
`local/stands/p08b-profile13-01/battle-profiles.json` and uses
`WOT_P05C_ARTIFACTS`, defaulting to the canonical authored
`local/build/server/physics-p05c-night01/artifacts.json`. It creates only small
manifests under `local/test-runs`. This proves actual gateway core/scalar/IPC/Jolt
integration, without launching a native client or asserting UI acceptance.
