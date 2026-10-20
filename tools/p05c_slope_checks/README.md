# Continuous flat-to-ramp actual Jolt diagnostic

This separate component executable compile-links production physics, excluding
only its entrypoint `Program.cs`, with pinned JoltPhysicsSharp 2.22.0 and
JoltPhysics.Native 1.1.0. Actor configs come from the real hash-pinned two-actor
MS1/IS7 manifest and pass production `BattleSceneInput.Load` validation.

The test-lab terrain is deliberately authored, not historical 0.9.1 geometry:
one continuous six-triangle MeshShape strip, x=-30..30, flat z=-150..0,
6 or 12 degrees uphill z=0..80, then level to z=150. Shared vertices avoid a
gap or overlapping separate static floors. Each triangle's normal must point
up. The exact vertex/index document and its SHA256 appear in every case.
Original map meshes/catalog are not loaded or retagged with a new source kind.

IS7 starts at z=-45, MS1 at z=-24, both yaw zero and source origin y=3.
Production Control.Stop settles them naturally for 180 ticks. Thereafter IS7
receives `(throttle=1, steer=0, brake=false, speedPercent=100)` every substep;
MS1 stays on production Stop. There is no separate throttle phase or release
at the hill, no pose/velocity setters, no power/friction/profile edits.

Default matrix: 6/12 degrees x solo/pushing STOP MS1 x 1/4 collision steps.
Current runtime policy is solo=1, mixed=4; the other combinations are explicit
diagnostic controls. Default constraint is the production PI. Optional
`--cone both` includes the same real constraints with test-only PI/3 overrides.

The predeclared progress gate requires actual driver ramp wheel support and
IS7 origin at least 20m uphill with driver up.y>0.5. A pushing case additionally
requires MS1 at least 20m uphill, a pair manifold in the last 60 ticks, and at
least 30 flat pair-contact ticks while IS7 was already moving above 0.5m/s.
Exhausting the default 2400 drive ticks is FAIL, retained as evidence. These
engineering thresholds describe this authored diagnostic, not a historical
climbing claim. Failure alone does not establish the owner's stall cause.

Actual `MixedContactDiagnostics.Write` is sampled every six ticks, including
engine/RPM, clutch/gear, requested/controller controls, actual wheel body IDs,
normals, velocities and impulses. Separate bounded pair records retain actual
manifold point/normal/depth and production states. Penetration depth comes
from actual `ContactManifold.PenetrationDepth`, verified in the pinned managed
assembly by the parent; no SAT estimate is presented as native depth. The summary
reports first ramp support, forward speed, flat pushing, reverse ticks and
the longest under-0.2m/s interval after ramp support under sustained request.

Example from checkout (set isolated DOTNET_CLI_HOME and disable shared servers;
preserve exact commands and source hashes in the fresh build evidence folder):

```powershell
dotnet restore tools/p05c_slope_checks/SlopeChecks.csproj --source local/nuget-packages --ignore-failed-sources
dotnet build tools/p05c_slope_checks/SlopeChecks.csproj --no-restore -c Release -p:UseSharedCompilation=false
dotnet local/build/physics-slope01/bin/net9.0/SlopeChecks.dll --local-root C:/wot091-night-20261017-01/w/local --manifest C:/wot091-night-20261017-01/w/local/test-runs/p05c-scenes/battle-118080-4131859507633949383-1.json --manifest-sha256 87e61d7c481918a10a221f254a929ce3cda746ba313d358b87747f6d640fda22 --out C:/wot091-night-20261017-01/w/local/build/physics-slope01/probe
```

`--out` must name a new directory beneath an existing local-root parent. All
diagnostic files use CreateNew. Optional bounded argv: `--ticks 600..3600`
(divisible by six), `--mode both|solo|push`, `--collision-steps both|1|4`,
`--cone 180|60|both`. Preserve the initial FAILs before focused reruns. Exit
zero requires every requested case to meet the progress gate. Native UI,
owner handling and historical compatibility remain outside this gate.
