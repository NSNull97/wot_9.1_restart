# Actual Jolt rollover component gate

This diagnostic executable compile-links the actual `server/physics/*.cs`,
excluding only its production entrypoint `Program.cs`. It uses exactly
JoltPhysicsSharp 2.22.0 / JoltPhysics.Native 1.1.0 and the production embedded
profile definitions. Restore uses the existing offline package cache.

Pass the existing, hash-pinned two-actor MS1/IS7 manifest. The actual
`BattleSceneInput.Load` validates the original actor configuration references.
Each actor then runs alone on a deliberately authored 100m flat box with the
production collision layers, inline job system, body, vehicle constraint,
handling, 1/60 update, bound checks and state publication. The historical map
meshes and destruction catalog are not loaded in this diagnostic world.

There is one test-only initial 60-degree roll and one angular impulse targeting
1.5 rad/s about the actor's actual principal roll inertia. Afterwards only
gravity, physical contacts and production `Control.Stop` run for 720 steps.
No production pose/velocity setters or power/friction changes are introduced.
The production PI case must cross 90 degrees and spend the final 60 ticks
resting on its roof (up.y < -0.95, speed and angular speed < 0.1, floor contact).
The same actual constraint with a test-only PI/3 override must end within
65 degrees and must not be resting on its roof. Every six ticks the actual
`BattleTank.State` yaw/pitch/roll is independently reconstructed and compared
with all three quaternion basis vectors, with absolute component tolerance
4e-6. This checks production state output, not native wire compatibility.

Before building, set `DOTNET_CLI_HOME`, `BaseIntermediateOutputPath`,
`MSBuildProjectExtensionsPath` and `OutputPath` to a fresh ignored evidence
directory; disable shared compilation. Example (PowerShell, in checkout):

```powershell
$checkOut = 'C:/wot091-night-20261017-01/w/local/build/physics-rollover01'
$env:DOTNET_CLI_HOME = "$checkOut/dotnet-home"
$env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
$env:DOTNET_SKIP_FIRST_TIME_EXPERIENCE = '1'
$env:DOTNET_CLI_USE_MSBUILD_SERVER = '0'
$env:MSBUILDDISABLENODEREUSE = '1'
dotnet restore tools/p05c_rollover_checks/RolloverChecks.csproj --source local/nuget-packages --ignore-failed-sources
dotnet build tools/p05c_rollover_checks/RolloverChecks.csproj --no-restore -c Release -p:UseSharedCompilation=false
dotnet "$checkOut/bin/net9.0/RolloverChecks.dll" --local-root C:/wot091-night-20261017-01/w/local --manifest C:/wot091-night-20261017-01/w/local/test-runs/p05c-scenes/battle-118080-4131859507633949383-1.json --manifest-sha256 87e61d7c481918a10a221f254a929ce3cda746ba313d358b87747f6d640fda22
```

JSON stdout retains bounded samples and all FAILs; the executable returns
nonzero if any case fails. Store command, stdout/stderr and source hashes in
that evidence directory. Optional bounded diagnostic argv are
`--initial-roll-degrees 30..80`, `--initial-angular-speed 0.5..3`,
`--height 3..10`, and whole `--ticks 600..1200`; each run reports its setup.
Preserve the first failing run before trying a new setup. This component gate
does not close native handling, mixed contact or historical compatibility.
