# Shared powered-turn component checks

This executable compile-links current production physics and uses real `BattleTank`,
JoltPhysicsSharp 2.22.0 and native Jolt 1.1.0. Every comparison constructs a new
world with the same real, hash-pinned MS-1/IS-7 manifest and naturally settles
for 180 ticks. There are no body pose/velocity setters after spawn. The explicit
internal BattleTank policy argument compares disabled/enabled in one build;
the ordinary three-argument shared constructor must match enabled exactly.
The legacy `TrackedHandling` constructor default remains disabled.

The authored plane has grade 0 or 12 degrees. These are project regression
fixtures, not historical map geometry or a reproduction of the MS-1 contact
wedge. Test-lab powered steering uses inner-track deceleration 2 m/s², zero
through 4 m/s and a linear blend to full at 8 m/s, capped by source brake torque.
No source mass, engine power, profile hash or drivetrain ratio is changed.

The 128 actual world runs cover both profiles, 1/4 collision steps, 0/8-second
matched straight prefixes and straight/left/right controls, then four seconds
of straight steering release. Gates require exact initial state, exact straight
traces, exact initial low-speed frames through 4 m/s, negative high-speed flat
turn acceleration and at least 0.25 m/s speed loss relative to matched baseline,
12-degree launch speed at least 95% of baseline, immediate extra-brake release,
recovered straight speed, torque/energy bounds, deterministic selected repeats
and exact coast/brake/reversal pairs. Existing P05B gates are separate and must
still run; native handling/UI remain NOT_RUN until owner acceptance.

Use a fresh build/output folder and an existing offline NuGet cache. For example:

```powershell
dotnet restore tools/p05c_powered_turn_checks/PoweredTurnChecks.csproj --source local/nuget-packages --ignore-failed-sources -p:BaseIntermediateOutputPath=C:/path/to/fresh-build/obj/
dotnet build tools/p05c_powered_turn_checks/PoweredTurnChecks.csproj --no-restore -c Release -p:BaseIntermediateOutputPath=C:/path/to/fresh-build/obj/ -p:OutputPath=C:/path/to/fresh-build/bin/ -p:UseSharedCompilation=false
dotnet C:/path/to/fresh-build/bin/PoweredTurnChecks.dll --local-root C:/path/to/checkout/local --manifest C:/path/to/scene.json --manifest-sha256 HASH --out C:/path/to/checkout/local/evidence/FRESH
```

All inputs pass production bounded path/manifest validation. Output must be a
new directory below an existing local-root parent; `result.json` uses CreateNew.
Any failed assertion exits nonzero. Preserve failed output/logs before rerunning.
