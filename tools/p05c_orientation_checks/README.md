# P05C quaternion to Euler checks

This standalone .NET 9 console test compiles the actual
`server/physics/BodyOrientation.cs` helper. It has no Jolt or test-framework
package dependencies. All intermediate/output files belong to
`local/build/physics-orientation01`; it does not start a worker or game client.

The oracle transforms each unit basis axis with the input quaternion using
`System.Numerics.Vector3.Transform`. The output yaw/pitch/roll is independently
reconstructed as `Ry(yaw) * Rx(pitch) * Rz(roll)`, the project convention measured
against the original client Math matrix. Comparing the complete basis avoids
false failures when equivalent Euler values change branch past 90 degrees.

Cases cover exact and nearby positive/negative pitch poles, positive/negative
180 degrees, full roll sweeps, arbitrary yaw/roll combinations, arbitrary axes,
and both quaternion signs. A case requires finite canonical angles and maximum
absolute component error no greater than `4e-6` across all three basis vectors.
Inputs are normalized unit quaternions; malformed external input validation is
outside this helper check.

Run from the repository root after the production helper exists:

```powershell
dotnet restore tools/p05c_orientation_checks/OrientationChecks.csproj --source local/nuget-packages
dotnet run --project tools/p05c_orientation_checks/OrientationChecks.csproj --no-restore -c Release
```

Exit zero and the JSON `PASS` confirm only this quaternion/Euler mapping on the
executing .NET platform. The test does not execute the Rust native wire encoder,
Jolt integration, vehicle rollover/contact physics, original-client rendering,
camera behavior, network transport, or historical World of Tanks physics.
Native RPY versus YPR message ordering requires its own real wire regression.
Actual command output/evidence must be retained separately; source existence is
not evidence that a run passed.
