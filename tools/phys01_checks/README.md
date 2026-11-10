# PHYS-01 regression probe

Compiles the production `server/physics/*.cs` (all but `Program.cs`) with JoltPhysicsSharp 2.22.0 and drives real
`BattleTank` bodies on authored geometry: a flat slab, tilted slabs, boxes and ramps. Step 1/60 s, four collision
steps, the same hull-contact handling as `BattleScene.Advance`. Vehicles: IS-7 and `france-Bat_Chatillon25t`.

It measures the model's law. It is not a map, a native client or a historical proof.

```powershell
dotnet build tools/phys01_checks/Phys01Checks.csproj -c Release
dotnet local/build/phys01-checks/bin/Phys01Checks.dll <repo-root> all            # current rules
dotnet local/build/phys01-checks/bin/Phys01Checks.dll <repo-root> all baseline   # former Jolt gearbox
```

Modes: `accel`, `stall`, `push`, `slope`, `turn`, `bump`, `basics` (pivot, reverse, brake), `steep`, `ramp`, `rock`, `side`, `wall`, `wedge`, `launch`, `coast`, `grade`, `ride`, `all`.
A stand vehicle absent from the generated table joins `launch`, `coast`, `grade` and `ride` through `PHYS01_EXTRA_KIND`
(a generated kind name) and `PHYS01_EXTRA_CONFIG` (its battle config file).
Output is plain text, one `##` line per case. Build output goes to the ignored `local/build/phys01-checks/`.

Two `slope ... 35deg steer=-1` cases end with `motion outside bounds`: the vehicle drives below the world floor
(-100 m) on the endless slab. That is the probe's geometry, not a finding.
