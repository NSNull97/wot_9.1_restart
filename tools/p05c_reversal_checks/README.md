# Intent-based reversal brake component

This tool compile-links current `server/physics` directly. Do not ship a copied
physics tree with it. The production `BattleTank` five-argument seam compares
`enableIntentReversalBrake=false/true`, with powered-turn policy true in both
arms. The ordinary shared constructor enables intent braking; the separate
`TrackedHandling` optional flag defaults false for the legacy Program route.
The proposed patch preserves the existing -0.5 m/s arm/exit threshold. A new
validated raw throttle direction can arm braking; after exit the same held
throttle cannot rearm solely because gravity rolls the body back. No engine,
profile, gear ratio, brake coefficient, body pose or velocity is retuned.

`DriverLogicUnits` is explicitly a driver-logic unit. It calls the production
helper against native six-wheel controller readbacks, but supplies signed-speed
metrics and never calls PhysicsSystem.Update. It proves input/state transitions,
not traction. It covers both profiles, repeated W and six-substep command reuse,
steering/cruise changes, strict -0.50001/-0.5 boundaries, release and re-press,
sign replacement during braking, explicit Stop/coast cancellation, speed-cap
motor cuts, rejected inputs preserving state, and 40 rapid direction flips.
Its expected old-policy negative control must still show automatic braking.

`MovingReverseChecks` uses actual native Jolt and genuine BattleTank bodies.
Both tanks and 1/4 collision steps get naturally settled fresh worlds, short
90-tick or long480-tick straight prefixes, and eight seconds of opposite input.
Matched entry, the entire accepted first brake phase, complete flat trajectories
and selected replays must match exactly. There are 16 flat matched pairs plus
16 repeats:48 worlds. Another8 paired uniform16/21-degree cases plus8 repeats
use fixed600 STOP settle and unmodified production CheckSettled. They report
NOT_EXERCISED when no genuine rollback occurs; successful climbing is not a
required universal vehicle claim. The combined core run has72 actual worlds.

The separate `RampFreshChecks.csproj` is a targeted physical acceptance check.
It uses eight shared vertices/six upward triangles: flat z=-150..0, ramp0..80
at16/21 degrees, plateau80..150, width60m. Spawn z=-30/y3; 180 STOP ticks,
600 W ticks, up to900 neutral coast ticks until actual signed speed<-.6,
then480 fresh W ticks. It requires matched pre-fresh trajectories, an identical
first brake phase and no subsequent rearm while W stays held; all candidate
replays must match. Missing natural rollback is explicitly NOT_EXERCISED;
pre-fresh divergence is explicitly NOT_MATCHED and never fresh-intent proof.
The top-level run fails unless all eight cases are exercised and matched,
with 24 actual worlds and zero NOT_EXERCISED or NOT_MATCHED cases.
Neither physical test sets body pose/velocity after spawn. Native client UI,
handling feel and original map reproduction remain separate acceptance gates.

Build into a fresh private C output, with DOTNET_CLI_HOME there, the existing
project-local NUGET_PACKAGES cache, and an offline NuGet.Config containing only
`<configuration><packageSources><clear /></packageSources></configuration>`.
Copy the exact server/physics/packages.lock.json to BUILD/packages.lock.json;
use NuGetLockFilePath so no lock/obj/bin is written under tracked tools.
The following commands assume the five core files are copied to
`tools/p05c_reversal_checks`; optional ramp uses the two additional files.

```powershell
dotnet restore tools/p05c_reversal_checks/ReversalChecks.csproj --locked-mode --configfile BUILD/nuget-offline.config -p:NuGetLockFilePath=BUILD/packages.lock.json -p:BaseIntermediateOutputPath=BUILD/core-obj/
dotnet build tools/p05c_reversal_checks/ReversalChecks.csproj --no-restore -c Release -p:NuGetLockFilePath=BUILD/packages.lock.json -p:BaseIntermediateOutputPath=BUILD/core-obj/ -p:OutputPath=BUILD/core-bin/ -p:UseSharedCompilation=false
dotnet BUILD/core-bin/ReversalChecks.dll --local-root LOCAL --manifest MANIFEST --manifest-sha256 SHA --mode all --out FRESH_CORE_EVIDENCE
dotnet restore tools/p05c_reversal_checks/RampFreshChecks.csproj --locked-mode --configfile BUILD/nuget-offline.config -p:NuGetLockFilePath=BUILD/packages.lock.json -p:BaseIntermediateOutputPath=BUILD/ramp-obj/
dotnet build tools/p05c_reversal_checks/RampFreshChecks.csproj --no-restore -c Release -p:NuGetLockFilePath=BUILD/packages.lock.json -p:BaseIntermediateOutputPath=BUILD/ramp-obj/ -p:OutputPath=BUILD/ramp-bin/ -p:UseSharedCompilation=false
dotnet BUILD/ramp-bin/RampFreshChecks.dll --local-root LOCAL --manifest MANIFEST --manifest-sha256 SHA --out FRESH_RAMP_EVIDENCE
```

Use absolute BUILD/LOCAL/MANIFEST/output paths. The verified staging manifest
is `local/evidence/20261017-p05c-mixed-physics01/new-flat03/scene.json`, SHA256
`c8eaccfd07745c0f4212e74df6d221e18630de76b543bc1bcae9a01ce273324d`.
All outputs require fresh paths, all result files use CreateNew. Retain failed
builds/runs before rerunning. The original180-tick uniform-slope settle failure
and an initial lock-reference mismatch are retained in staging; neither was
silently renamed PASS. Fixed600 STOP settling kept production checks unchanged.
