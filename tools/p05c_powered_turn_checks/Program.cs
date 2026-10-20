using System.Numerics;
using System.Security.Cryptography;
using System.Text.Json;
using JoltPhysicsSharp;
using MapDrive;

// Actual native Jolt, real BattleTank construction, matched fresh worlds.
// No test-only physics copy, body setters, or mutable global handling switches.
internal static class PoweredTurnChecks
{
    static readonly BattleSceneInput.Control Stop = new(0, 0, true, 100), Drive = new(1, 0, false, 100);
    sealed record Frame(float Speed, float[] Values, string Sha, float LeftDelta, float RightDelta);
    sealed record Run(string Kind, int Steps, int Grade, int Prefix, int Throttle, int Steer, bool Brake,
        bool? Enabled, string EntrySha, float EntrySpeed, Frame[] Window, Frame[] Release, string TraceSha);
    static void Need(bool value, string code) { if (!value) throw new InvalidDataException(code); }
    static string Sha(byte[] raw) => Convert.ToHexString(SHA256.HashData(raw)).ToLowerInvariant();
    static bool Equal(Frame a, Frame b) => a.Sha == b.Sha;
    static Run Measure(BattleSceneInput.Manifest manifest, string kind, int steps, int grade, int prefix,
        BattleSceneInput.Control command, bool? enabled)
    {
        using var pairs = new ObjectLayerPairFilterTable(2); pairs.EnableCollision(0, 1); pairs.EnableCollision(1, 1);
        using var broad = new BroadPhaseLayerInterfaceTable(2, 2); broad.MapObjectToBroadPhaseLayer(0, 0); broad.MapObjectToBroadPhaseLayer(1, 1);
        using var filter = new ObjectVsBroadPhaseLayerFilterTable(broad, 2, pairs, 2);
        using var jobs = new InlineJobSystem();
        using var world = new PhysicsSystem(new PhysicsSystemSettings { MaxBodies = 32, MaxBodyPairs = 8192,
            MaxContactConstraints = 8192, ObjectLayerPairFilter = pairs, BroadPhaseLayerInterface = broad, ObjectVsBroadPhaseLayerFilter = filter });
        float slope = MathF.Tan(grade * MathF.PI / 180);
        Vector3[] vertices = [new(-500, -500*slope, -500), new(500, -500*slope, -500), new(-500, 500*slope, 500), new(500, 500*slope, 500)];
        IndexedTriangle[] triangles = [new(0, 2, 3), new(0, 3, 1)];
        using var mesh = new MeshShapeSettings(vertices.AsSpan(), triangles.AsSpan()); using var shape = new MeshShape(mesh);
        using var settings = new BodyCreationSettings(shape, Vector3.Zero, Quaternion.Identity, MotionType.Static, 0) { Friction = 1 };
        var floor = world.BodyInterface.CreateBody(settings); world.BodyInterface.AddBody(floor.ID, Activation.DontActivate);
        BattleTank? tank = null;
        try
        {
            var source = manifest.Actors.Single(a => a.Kind == kind) with { Slot = 0, Spawn = new Vector3(0, 3, 0), Yaw = 0 };
            tank = enabled.HasValue ? new BattleTank(world, source, null, enabled.Value) : new BattleTank(world, source, null);
            world.OptimizeBroadPhase(); var controller = tank.Constraint.GetController<TrackedVehicleController>();
            float Speed() => Vector3.Dot(tank.Body.GetLinearVelocity(), Vector3.Transform(Vector3.UnitZ, tank.Body.Rotation));
            Frame Capture(float leftDelta, float rightDelta)
            {
                var q = tank.Body.Rotation; var p = tank.Body.Position; var v = tank.Body.GetLinearVelocity(); var w = tank.Body.GetAngularVelocity();
                var engine = controller.Engine; var transmission = controller.Transmission;
                var values = new List<float> { p.X,p.Y,p.Z,q.X,q.Y,q.Z,q.W,v.X,v.Y,v.Z,w.X,w.Y,w.Z,
                    controller.ForwardInput, controller.LeftRatio, controller.RightRatio, controller.BrakeInput,
                    engine.CurrentRPM, transmission.CurrentGear, transmission.CurrentRatio, transmission.ClutchFriction,
                    controller.LeftTrack.AngularVelocity, controller.RightTrack.AngularVelocity, leftDelta, rightDelta };
                for (int i = 0; i < 6; i++)
                {
                    var wheel = tank.Constraint.GetWheel(i);
                    values.AddRange([wheel.HasContact ? 1 : 0,
                        wheel.SuspensionLambda, wheel.LongitudinalLambda, wheel.LateralLambda]);
                }
                Need(values.All(float.IsFinite), "nonfinite actual state");
                var array = values.ToArray(); return new Frame(Speed(), array, Sha(JsonSerializer.SerializeToUtf8Bytes(array)), leftDelta, rightDelta);
            }
            Frame Step(BattleSceneInput.Control input, int tick)
            {
                float beforeLeft = controller.LeftTrack.AngularVelocity, beforeRight = controller.RightTrack.AngularVelocity;
                tank.BeforeStep(input, (tick - 1) % 6 + 1, false);
                float afterLeft = controller.LeftTrack.AngularVelocity, afterRight = controller.RightTrack.AngularVelocity;
                // Powered-policy edits can only retard track rotation, bounded by source torque.
                if (input.Throttle != 0 && input.Steer != 0 && !input.Brake)
                {
                    foreach (var pair in new[] { (beforeLeft, afterLeft, controller.LeftTrack), (beforeRight, afterRight, controller.RightTrack) })
                    {
                        Need(MathF.Abs(pair.Item2) <= MathF.Abs(pair.Item1) + 1e-5f, "powered brake added track energy");
                        Need(MathF.Abs(pair.Item2-pair.Item1)*pair.Item3.Inertia*60 <= pair.Item3.MaxBrakeTorque + .5f, "source brake torque bound");
                    }
                }
                var error = world.Update(1f / 60, steps, jobs); jobs.CheckThread(); Need(error == PhysicsUpdateError.None, "actual Jolt update fault");
                tank.AfterStep(); return Capture(afterLeft-beforeLeft, afterRight-beforeRight);
            }
            for (int tick = 1; tick <= 180; tick++) Step(Stop, tick); tank.CheckSettled();
            for (int tick = 1; tick <= prefix; tick++) Step(Drive, tick);
            string entry = Capture(0, 0).Sha; float entrySpeed = Speed();
            var window = new Frame[240]; var release = new Frame[240];
            for (int tick = 1; tick <= 240; tick++) window[tick-1] = Step(command, prefix+tick);
            for (int tick = 1; tick <= 240; tick++)
            {
                release[tick-1] = Step(Drive, prefix+240+tick);
                Need(release[tick-1].LeftDelta == 0 && release[tick-1].RightDelta == 0, "extra brake after steering release");
            }
            string trace = Sha(JsonSerializer.SerializeToUtf8Bytes(window.Concat(release).Select(f => f.Sha)));
            return new Run(kind, steps, grade, prefix, command.Throttle, command.Steer, command.Brake, enabled, entry, entrySpeed, window, release, trace);
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
            var rows = new List<object>(); int actualRuns=0, lowExact=0, straightExact=0, excludedExact=0, replayExact=0, defaultExact=0;
            foreach (string kind in new[]{"ms1","is7"}) foreach (int steps in new[]{1,4})
            {
                foreach (int grade in new[]{0,12}) foreach (int prefix in new[]{0,480}) foreach (int steer in new[]{0,-1,1})
                {
                    var command = new BattleSceneInput.Control(1,steer,false,100);
                    var before = Measure(manifest,kind,steps,grade,prefix,command,false);
                    var after = Measure(manifest,kind,steps,grade,prefix,command,true); actualRuns+=2;
                    Need(before.EntrySha==after.EntrySha, "matched start state");
                    for (int i=0;i<240;i++)
                    {
                        float previous = i==0 ? before.EntrySpeed : before.Window[i-1].Speed;
                        if (MathF.Abs(previous)>4) break;
                        Need(Equal(before.Window[i],after.Window[i]), "low-speed force changed"); lowExact++;
                    }
                    if (steer==0) { Need(before.TraceSha==after.TraceSha, "straight behavior changed"); straightExact++; }
                    if (grade==0 && prefix==480 && steer!=0)
                    {
                        Need(after.Window[59].Speed < after.EntrySpeed && before.Window[239].Speed-after.Window[239].Speed >= .25f, "high-speed powered turn did not decelerate");
                        Need(after.Release[59].Speed>after.Window[239].Speed && after.Release[239].Speed>after.Release[59].Speed, "drive did not recover after release");
                    }
                    if (grade==12 && prefix==0) Need(after.Window[239].Speed >= .95f*before.Window[239].Speed, "12-degree launch progress below 95 percent baseline");
                    rows.Add(new {kind,steps,grade,prefix,steer,baseline_entry=before.EntrySpeed,baseline_a1=before.Window[59].Speed-before.EntrySpeed,
                        candidate_a1=after.Window[59].Speed-after.EntrySpeed,baseline_v4=before.Window[239].Speed,candidate_v4=after.Window[239].Speed,
                        release_v1=after.Release[59].Speed,release_v4=after.Release[239].Speed,baseline_trace=before.TraceSha,candidate_trace=after.TraceSha});
                    if (grade==0 && prefix==480 && steer==1)
                    {
                        var replay = Measure(manifest,kind,steps,grade,prefix,command,true); actualRuns++; Need(replay.TraceSha==after.TraceSha,"same-build replay changed"); replayExact++;
                        var production = Measure(manifest,kind,steps,grade,prefix,command,null); actualRuns++; Need(production.TraceSha==after.TraceSha,"shared production default not enabled"); defaultExact++;
                    }
                }
                foreach (var command in new[]{new BattleSceneInput.Control(0,1,false,100),Stop,new BattleSceneInput.Control(-1,1,false,100)})
                {
                    var before = Measure(manifest,kind,steps,0,480,command,false);
                    var after = Measure(manifest,kind,steps,0,480,command,true); actualRuns+=2;
                    if (command.Throttle < 0)
                    {
                        int reversalSteps = 0;
                        for (int i=0;i<240 && before.Window[i].Values[16]>0;i++)
                        { Need(Equal(before.Window[i],after.Window[i]),"reversal-brake behavior changed"); reversalSteps++; }
                        Need(reversalSteps>0,"reversal brake not exercised");
                    }
                    // A released-throttle turn is a clutch-brake turn under the same
                    // shared policy (2026-10-20); tools/p05c_coast_turn_checks gates it.
                    else if (command.Steer != 0) Need(after.Window[119].Speed < before.Window[119].Speed - 1, "coast turn did not shed speed");
                    else Need(before.TraceSha==after.TraceSha,"coast/brake behavior changed");
                    excludedExact++;
                }
            }
            var result = new {schema="p05c-powered-turn-checks.v1",status="PASS",actual_native_jolt=true,native_client="NOT_RUN",historical_physics=false,
                shared_project_policy=new{inner_deceleration_mps2=2,start_mps=4,full_mps=8},manifest_sha256=manifest.Hash,
                actual_runs=actualRuns,low_speed_exact_steps=lowExact,straight_exact_pairs=straightExact,excluded_exact_pairs=excludedExact,
                repeat_exact=replayExact,production_default_exact=defaultExact,body_pose_or_velocity_setters_after_spawn=0,rows};
            using var stream = new FileStream(Path.Combine(output,"result.json"),FileMode.CreateNew,FileAccess.Write,FileShare.Read);
            JsonSerializer.Serialize(stream,result,new JsonSerializerOptions{WriteIndented=true}); Console.WriteLine(JsonSerializer.Serialize(new{status="PASS",actual_runs=actualRuns,low_speed_exact_steps=lowExact})); return 0;
        }
        catch (Exception ex) { Console.Error.WriteLine(ex); return 1; }
        finally { if(initialized)Foundation.Shutdown(); }
    }
}
