# P03I-N — bounded native MS-1 queue smoke

Status: **PASS_NATIVE_MAP_DRIVE_QUEUE_SMOKE / P03I_FULL_HANDOFF_NOT_RUN**.

Card: `P03I_NATIVE_MS1_QUEUE`
Branch: `codex/p03i-native-ms1-queue`

## Goal

Record one owner-driven click on the ordinary random-battle button using the
existing MS-1, correlate the authenticated session with the local map-drive
worker, and keep the strict P03I native handoff gate honest.

## Run

The client was prepared in a fresh research-copy overlay and started with:

```powershell
python -B -X utf8 tools\interactive_client.py prepare --out local\evidence\20261008-p03i-native-ms1-queue-01\install --public-key local\server\native-public.pem --endpoint 127.0.0.1:20014 --registration-url http://127.0.0.1:3091/register --profile-dir local\evidence\20261008-p03i-native-ms1-queue-01\profile --trace-dir local\evidence\20261008-p03i-native-ms1-queue-01\runtime --enable-map-drive --compiler local\toolchains\cpython-2.7.3-x86\python.exe --disable-legacy-license-dialog
python -B -X utf8 tools\manual_client_run.py --install local\evidence\20261008-p03i-native-ms1-queue-01\install --service local\server\service.json
```

The owner logged in, clicked `В бой!` once, and closed the client. The
research overlay restored with `PASS`; the native process exited with code 0.

## Evidence classification

The server log records request `202` / command `700` accepted for native
vehicle inventory `1`, queue type `1`, then starts `01_karelia`. The worker
reaches ready, creates the avatar and vehicle, binds the client, and receives
the first input. The native trace independently shows the selected MS-1
inventory ID `1`, `BattleQueue`, `PlayerAvatar.onEnterWorld`, `onSpaceLoaded`,
and `userSeesWorld`. CAPTCHA had zero blocked calls and the guard was restored.

This is a **server-side map-drive queue and battle-entry smoke PASS**. It is
not a full P03I native handoff acceptance: the route is the compatibility
map-drive path, and the run does not independently decode the live Account
body's two leading `INT16` values, `INT64` vehicle field, both `INT32`
gameplay/arena fields, or expose native `onEnqueued(queueType)` arguments.

Receipt: `local/evidence/20261008-p03i-native-ms1-queue-01/native-gate-audit.json`.

## Checks and limits

- `native-outcome.json`: client start/exit/restore/capture **PASS**, 386 raw
  packets retained.
- `gateway-span.log`: queue `accepted=true`, worker exit code `0`.
- `native-*.jsonl`: click, queue view, selected inventory, avatar/world entry,
  and clean teardown are present.
- Git working tree contains documentation only; no original client, research
  client, deployed service, fixture, database, gateway or physics code changed.
- IS-7 crew, ammunition, equipment and persistence remain **NOT_RUN**.
- No owner screenshot was captured because the client was closed after entry.

Rollback is a single revert of this documentation card; ignored evidence can
be removed independently after preserving its hashes.

The next step is a dedicated raw-frame/callback capture that satisfies the
original P03I fields, followed by an IS-7 run only after its server-owned crew
and shell fixture is explicitly admitted.
