using System.Numerics;
using System.Security.Cryptography;
using System.Text.Json;
using JoltPhysicsSharp;
using MapDrive;

// Actual native Jolt, real BattleTank construction, matched fresh worlds.
// No test-only physics copy, body setters, or mutable global handling switches.
// Released-throttle (coast) turns from speed: owner run 2026-10-20 circled
// ~308 degrees in 13.6 s and kept 5.8 of 12.3 m/s.
internal static class CoastTurnChecks
{
    static readonly BattleSceneInput.Control Stop = new(0, 0, true, 100), Drive = new(1, 0, false, 100);
    const int Settle = 180, Prefix = 480, Window = 1800;
    const float RestSpeed = .3f;
    sealed record Run(string Kind, int Steps, int Prefix, int Steer, bool Enabled, string EntrySha, float EntrySpeed,
        float[] Speeds, float RestSeconds, float RestYawDegrees, float YawDegrees, float RestDistance, string TraceSha);
    static void Need(bool value, string code) { if (!value) throw new InvalidDataException(code); }
    static string Sha(byte[] raw) => Convert.ToHexString(SHA256.HashData(raw)).ToLowerInvariant();
    static Run Measure(BattleSceneInput.Manifest manifest, string kind, int steps, int prefix, int steer, bool enabled)
    {
        using var pairs = new ObjectLayerPairFilterTable(2); pairs.EnableCollision(0, 1); pairs.EnableCollision(1, 1);
        using var broad = new BroadPhaseLayerInterfaceTable(2, 2); broad.MapObjectToBroadPhaseLayer(0, 0); broad.MapObjectToBroadPhaseLayer(1, 1);
        using var filter = new ObjectVsBroadPhaseLayerFilterTable(broad, 2, pairs, 2);
        using var jobs = new InlineJobSystem();
        using var world = new PhysicsSystem(new PhysicsSystemSettings { MaxBodies = 32, MaxBodyPairs = 8192,
            MaxContactConstraints = 8192, ObjectLayerPairFilter = pairs, BroadPhaseLayerInterface = broad, ObjectVsBroadPhaseLayerFilter = filter });
        Vector3[] vertices = [new(-2000, 0, -2000), new(2000, 0, -2000), new(-2000, 0, 2000), new(2000, 0, 2000)];
        IndexedTriangle[] triangles = [new(0, 2, 3), new(0, 3, 1)];
        using var mesh = new MeshShapeSettings(vertices.AsSpan(), triangles.AsSpan()); using var shape = new MeshShape(mesh);
        using var settings = new BodyCreationSettings(shape, Vector3.Zero, Quaternion.Identity, MotionType.Static, 0) { Friction = 1 };
        var floor = world.BodyInterface.CreateBody(settings); world.BodyInterface.AddBody(floor.ID, Activation.DontActivate);
        BattleTank? tank = null;
        try
        {
            var source = manifest.Actors.Single(a => a.Kind == kind) with { Slot = 0, Spawn = new Vector3(0, 3, 0), Yaw = 0 };
            tank = new BattleTank(world, source, null, enabled);
            world.OptimizeBroadPhase(); var controller = tank.Constraint.GetController<TrackedVehicleController>();
            float Speed() => Vector3.Dot(tank.Body.GetLinearVelocity(), Vector3.Transform(Vector3.UnitZ, tank.Body.Rotation));
            string State()
            {
                var q = tank.Body.Rotation; var p = tank.Body.Position; var v = tank.Body.GetLinearVelocity(); var w = tank.Body.GetAngularVelocity();
                float[] values = [p.X,p.Y,p.Z,q.X,q.Y,q.Z,q.W,v.X,v.Y,v.Z,w.X,w.Y,w.Z,controller.LeftTrack.AngularVelocity,controller.RightTrack.AngularVelocity];
                Need(values.All(float.IsFinite), "nonfinite actual state");
                return Sha(JsonSerializer.SerializeToUtf8Bytes(values));
            }
            void Step(BattleSceneInput.Control input, int tick)
            {
                float beforeLeft = controller.LeftTrack.AngularVelocity, beforeRight = controller.RightTrack.AngularVelocity;
                tank.BeforeStep(input, (tick - 1) % 6 + 1, false);
                if (input.Throttle == 0 && input.Steer != 0 && !input.Brake)
                {
                    // Coast-policy edits can only retard track rotation, bounded by source torque.
                    foreach (var (before, after, track) in new[] { (beforeLeft, controller.LeftTrack.AngularVelocity, controller.LeftTrack),
                        (beforeRight, controller.RightTrack.AngularVelocity, controller.RightTrack) })
                    {
                        Need(MathF.Abs(after) <= MathF.Abs(before) + 1e-5f, "coast brake added track energy");
                        Need(MathF.Abs(after - before) * track.Inertia * 60 <= track.MaxBrakeTorque + .5f, "source brake torque bound");
                    }
                }
                var error = world.Update(1f / 60, steps, jobs); jobs.CheckThread(); Need(error == PhysicsUpdateError.None, "actual Jolt update fault");
                tank.AfterStep();
            }
            for (int tick = 1; tick <= Settle; tick++) Step(Stop, tick); tank.CheckSettled();
            for (int tick = 1; tick <= prefix; tick++) Step(Drive, tick);
            string entry = State(); float entrySpeed = Speed();
            var command = new BattleSceneInput.Control(0, steer, false, 100);
            var speeds = new float[Window]; var states = new string[Window]; float rest = -1, yaw = 0, distance = 0, restYaw = 0, restDistance = 0;
            for (int tick = 1; tick <= Window; tick++)
            {
                var p0 = tank.Body.Position;
                Step(command, prefix + tick);
                var p1 = tank.Body.Position; distance += Vector2.Distance(new(p0.X, p0.Z), new(p1.X, p1.Z));
                yaw += tank.Body.GetAngularVelocity().Y / 60 * 180 / MathF.PI;
                speeds[tick - 1] = Speed(); states[tick - 1] = State();
                if (rest < 0 && MathF.Abs(speeds[tick - 1]) < RestSpeed) { rest = tick / 60f; restYaw = yaw; restDistance = distance; }
            }
            string trace = Sha(JsonSerializer.SerializeToUtf8Bytes(states));
            return new Run(kind, steps, prefix, steer, enabled, entry, entrySpeed, speeds, rest, restYaw, yaw, restDistance, trace);
        }
        finally { tank?.Dispose(); world.BodyInterface.RemoveAndDestroyBody(floor.ID); }
    }
    public static int Main(string[] args)
    {
        bool initialized = false;
        try
        {
            Need(args.Length == 8, "--local-root ROOT --manifest PATH --manifest-sha256 SHA --out FRESH");
            var options = new Dictionary<string,string>(); for (int i=0;i<args.Length;i+=2) Need(options.TryAdd(args[i],args[i+1]), "duplicate option");
            Need(options.Keys.Order().SequenceEqual(new[]{"--local-root","--manifest","--manifest-sha256","--out"}), "exact options");
            string root = Path.GetFullPath(options["--local-root"]), output = Path.GetFullPath(options["--out"]);
            CheckedInput.Owned(root, Path.GetDirectoryName(output)!); Need(!Directory.Exists(output) && !File.Exists(output), "fresh output required");
            var manifest = BattleSceneInput.Load(root, options["--manifest"], options["--manifest-sha256"]);
            Directory.CreateDirectory(output); Need(Foundation.Init(false), "native Jolt init"); initialized = true;
            var rows = new List<object>(); int actualRuns = 0, exactPairs = 0, coastGates = 0;
            foreach (string kind in new[]{"ms1","is7"}) foreach (int steps in new[]{1,4}) foreach (int prefix in new[]{0,Prefix})
            {
                var runs = new Dictionary<(int, bool), Run>();
                foreach (int steer in new[]{0,1,-1}) foreach (bool enabled in new[]{false,true})
                { runs[(steer, enabled)] = Measure(manifest, kind, steps, prefix, steer, enabled); actualRuns++; }
                Need(runs.Values.Select(r => r.EntrySha).Distinct().Count() == 1, "matched start state");
                // Straight coast and a steer-only start from rest never enter
                // the rolling-turn phase: the shared policy must not touch them.
                Need(runs[(0,false)].TraceSha == runs[(0,true)].TraceSha, "straight coast changed"); exactPairs++;
                if (prefix == 0)
                    foreach (int steer in new[]{1,-1}) { Need(runs[(steer,false)].TraceSha == runs[(steer,true)].TraceSha, "pivot from rest changed"); exactPairs++; }
                else
                {
                    foreach (int steer in new[]{1,-1})
                    {
                        var before = runs[(steer,false)]; var after = runs[(steer,true)];
                        Need(after.EntrySpeed > 8, "rolling-turn entry speed");
                        Need(after.RestSeconds > 0 && after.RestSeconds <= 4, "released-throttle turn must stop within 4 s");
                        Need(before.RestSeconds < 0 || before.RestSeconds > 3 * after.RestSeconds, "baseline was not the long coast");
                        float turned = steer * after.RestYawDegrees;
                        Need(turned >= 10 && turned <= 180, "rolling turn must turn without circling");
                        Need(steer * (after.YawDegrees - after.RestYawDegrees) > 90, "pivot after rest still turns");
                        coastGates++;
                    }
                    Need(MathF.Abs(runs[(1,true)].RestYawDegrees + runs[(-1,true)].RestYawDegrees) <= .1f * MathF.Abs(runs[(1,true)].RestYawDegrees), $"left/right symmetry {kind}/{steps}: {runs[(1,true)].RestYawDegrees} vs {runs[(-1,true)].RestYawDegrees}, rest {runs[(1,true)].RestSeconds}/{runs[(-1,true)].RestSeconds}");
                }
                foreach (var r in runs.Values)
                    rows.Add(new { kind, steps, prefix, steer = r.Steer, enabled = r.Enabled, entry_mps = r.EntrySpeed,
                        v1 = r.Speeds[59], v2 = r.Speeds[119], v4 = r.Speeds[239], v8 = r.Speeds[479], v30 = r.Speeds[Window - 1],
                        rest_seconds = r.RestSeconds, rest_yaw_degrees = r.RestYawDegrees, rest_distance_m = r.RestDistance,
                        window_yaw_degrees = r.YawDegrees, trace = r.TraceSha });
            }
            var result = new {schema="p05c-coast-turn-checks.v1",status="PASS",actual_native_jolt=true,native_client="NOT_RUN",historical_physics=false,
                shared_project_policy=new{coast_turn_inner_deceleration_mps2=6,coast_turn_outer_deceleration_mps2=3,enter_mps=1.5,pivot_handoff_mps=1.25},
                manifest_sha256=manifest.Hash,actual_runs=actualRuns,exact_pairs=exactPairs,coast_turn_gates=coastGates,body_pose_or_velocity_setters_after_spawn=0,rows};
            using var stream = new FileStream(Path.Combine(output,"result.json"),FileMode.CreateNew,FileAccess.Write,FileShare.Read);
            JsonSerializer.Serialize(stream,result,new JsonSerializerOptions{WriteIndented=true});
            Console.WriteLine(JsonSerializer.Serialize(new{status="PASS",actual_runs=actualRuns,exact_pairs=exactPairs,coast_turn_gates=coastGates})); return 0;
        }
        catch (Exception ex) { Console.Error.WriteLine(ex); return 1; }
        finally { if(initialized)Foundation.Shutdown(); }
    }
}
