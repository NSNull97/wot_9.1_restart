# Released-throttle (coast) turn checks

Owner run 2026-10-20 (T-34 vs T-34-85): releasing W while holding A/D kept the
tank rolling in circles (~308 degrees in 13.6 s, 12.3 -> 5.8 m/s). The gateway
maps no movement keys to a full brake (#717 movement flags 0), but a steer-only
key has no forward request, and the rolling-turn phase braked the tracks only
below 1.25 m/s.

This executable compile-links current production physics and uses real
`BattleTank`, JoltPhysicsSharp 2.22.0 and native Jolt 1.1.0 on a flat authored
plane, exactly like `tools/p05c_powered_turn_checks`. Every run builds a fresh
world from the same hash-pinned MS-1/IS-7 manifest, settles 180 ticks, drives
straight for 0 or 8 s, then holds a released-throttle command (0, steer, no
brake) for 30 s. There are no body pose/velocity setters after spawn. The
explicit internal `BattleTank` policy argument compares disabled/enabled in one
build.

Shared test_lab policy under the same flag as the powered turn: during the whole
rolling turn the inner track decelerates at 6 m/s^2 and the outer at 3 m/s^2
(per-track half-mass), capped by source brake torque and never past zero. The
historical 0.9.1 coast law is UNKNOWN; these are project values.

Gates (48 runs): exact traces for straight coast and for a steer-only start from
rest (the policy must not touch them); from 8 s of straight drive the turn must
stop within 4 s, turn 10-180 degrees before rest (no circling), keep pivoting
after rest, be at least 3x faster than the disabled baseline and stay left/right
symmetric within 10 %; every policy edit only removes track energy within the
source brake torque. Native client handling stays NOT_RUN until the owner run.

```powershell
dotnet restore tools/p05c_coast_turn_checks/CoastTurnChecks.csproj --source local/nuget-packages --ignore-failed-sources -p:BaseIntermediateOutputPath=C:/path/to/fresh-build/obj/
dotnet build tools/p05c_coast_turn_checks/CoastTurnChecks.csproj --no-restore -c Release -p:BaseIntermediateOutputPath=C:/path/to/fresh-build/obj/ -p:OutputPath=C:/path/to/fresh-build/bin/ -p:UseSharedCompilation=false
dotnet C:/path/to/fresh-build/bin/CoastTurnChecks.dll --local-root C:/path/to/checkout/local --manifest C:/path/to/scene.json --manifest-sha256 HASH --out C:/path/to/checkout/local/evidence/FRESH
```
