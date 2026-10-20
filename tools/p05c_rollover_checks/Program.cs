using System.Globalization;
using System.Numerics;
using System.Security.Cryptography;
using System.Text.Json;
using JoltPhysicsSharp;
using MapDrive;

// Diagnostic initial conditions belong only to this executable. After the one
// rotation/impulse, all integration, contacts, handling and state are production.
internal static class RolloverChecks
{
    sealed record Options(string Root, string Manifest, string Hash, float Roll, float Omega, float Height, int Ticks);
    static float[] V(Vector3 value) => [value.X, value.Y, value.Z];
    static float[] Q(Quaternion value) => [value.X, value.Y, value.Z, value.W];
    static string Sha(string path) => Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant();
    static Options Parse(string[] args)
    {
        if (args.Length < 6 || args.Length > 14 || args.Length % 2 != 0) throw new InvalidDataException("expected --local-root ROOT --manifest PATH --manifest-sha256 SHA [--initial-roll-degrees 60] [--initial-angular-speed 1.5] [--height 6] [--ticks 720]");
        var values = new Dictionary<string, string>(StringComparer.Ordinal);
        for (int i = 0; i < args.Length; i += 2)
            if (!values.TryAdd(args[i], args[i + 1])) throw new InvalidDataException("duplicate option");
        string[] allowed = ["--local-root", "--manifest", "--manifest-sha256", "--initial-roll-degrees", "--initial-angular-speed", "--height", "--ticks"];
        if (values.Keys.Except(allowed).Any()) throw new InvalidDataException("unknown option");
        float Number(string key, float fallback, float min, float max)
        {
            float value = values.TryGetValue(key, out var raw) ? float.Parse(raw, CultureInfo.InvariantCulture) : fallback;
            if (!float.IsFinite(value) || value < min || value > max) throw new InvalidDataException("option outside diagnostic bound: " + key);
            return value;
        }
        var hash = values["--manifest-sha256"];
        if (hash.Length != 64 || hash.Any(c => !char.IsAsciiHexDigit(c))) throw new InvalidDataException("manifest SHA256");
        float ticks = Number("--ticks", 720, 600, 1200);
        if (ticks != (int)ticks) throw new InvalidDataException("whole tick count required");
        return new(Path.GetFullPath(values["--local-root"]), Path.GetFullPath(values["--manifest"]), hash.ToLowerInvariant(),
            Number("--initial-roll-degrees", 60, 30, 80), Number("--initial-angular-speed", 1.5f, .5f, 3), Number("--height", 6, 3, 10), (int)ticks);
    }
    static Vector3 Reconstruct(Vector3 basis, Vector3 ypr)
    {
        // Independent analytic R_y(yaw) R_x(pitch) R_z(roll), not the utility under test.
        float sy = MathF.Sin(ypr.X), cy = MathF.Cos(ypr.X), sp = MathF.Sin(ypr.Y), cp = MathF.Cos(ypr.Y), sr = MathF.Sin(ypr.Z), cr = MathF.Cos(ypr.Z);
        var z = new Vector3(cr * basis.X - sr * basis.Y, sr * basis.X + cr * basis.Y, basis.Z);
        var x = new Vector3(z.X, cp * z.Y - sp * z.Z, sp * z.Y + cp * z.Z);
        return new(cy * x.X + sy * x.Z, x.Y, -sy * x.X + cy * x.Z);
    }
    static float BasisError(Quaternion q, Vector3 ypr)
    {
        float max = 0;
        foreach (var axis in new[] { Vector3.UnitX, Vector3.UnitY, Vector3.UnitZ })
        {
            var error = Vector3.Abs(Vector3.Transform(axis, q) - Reconstruct(axis, ypr));
            max = MathF.Max(max, MathF.Max(error.X, MathF.Max(error.Y, error.Z)));
        }
        return max;
    }
    static object Run(Options o, BattleSceneInput.Actor original, bool tether, out bool passed)
    {
        using var pairs = new ObjectLayerPairFilterTable(2); pairs.EnableCollision(0, 1); pairs.EnableCollision(1, 1);
        using var broad = new BroadPhaseLayerInterfaceTable(2, 2); broad.MapObjectToBroadPhaseLayer(0, 0); broad.MapObjectToBroadPhaseLayer(1, 1);
        using var filter = new ObjectVsBroadPhaseLayerFilterTable(broad, 2, pairs, 2);
        using var jobs = new InlineJobSystem();
        using var world = new PhysicsSystem(new PhysicsSystemSettings
        {
            MaxBodies = 32, MaxBodyPairs = 8192, MaxContactConstraints = 8192,
            ObjectLayerPairFilter = pairs, BroadPhaseLayerInterface = broad, ObjectVsBroadPhaseLayerFilter = filter
        });
        var bodies = world.BodyInterface;
        using var floorShape = new BoxShape(new Vector3(50, .5f, 50));
        using var floorSettings = new BodyCreationSettings(floorShape, new Vector3(0, -.5f, 0), Quaternion.Identity, MotionType.Static, 0) { Friction = 1 };
        var floor = bodies.CreateBody(floorSettings); bodies.AddBody(floor.ID, Activation.DontActivate);
        try
        {
            var source = original with { Spawn = new Vector3(0, o.Height, 0), Yaw = 0 };
            using var tank = new BattleTank(world, source, null);
            if (tether) tank.Constraint.SetMaxPitchRollAngle(MathF.PI / 3);
            int contactTick = -1, callbackCount = 0, callbackFault = 0, tick = 0;
            void Contact(in Body a, in Body b, in ContactManifold m)
            {
                try
                {
                    jobs.CheckThread();
                    if (++callbackCount > o.Ticks * 16) throw new InvalidOperationException("diagnostic contact callback bound");
                    if ((a.ID == tank.Body.ID && b.ID == floor.ID || b.ID == tank.Body.ID && a.ID == floor.ID) && !m.IsNull && m.PointCount > 0) contactTick = tick;
                }
                catch { callbackFault = 1; }
            }
            world.OnContactAdded += (PhysicsSystem _, in Body a, in Body b, in ContactManifold m, ref ContactSettings s) => Contact(a, b, m);
            world.OnContactPersisted += (PhysicsSystem _, in Body a, in Body b, in ContactManifold m, ref ContactSettings s) => Contact(a, b, m);
            var initial = Quaternion.CreateFromAxisAngle(Vector3.UnitZ, o.Roll * MathF.PI / 180);
            bodies.SetRotation(tank.Body.ID, initial, Activation.Activate);
            var inverse = tank.Body.GetInverseInertia();
            if (!float.IsFinite(inverse.M33) || inverse.M33 <= 0 || MathF.Abs(inverse.M13) > 1e-6f || MathF.Abs(inverse.M23) > 1e-6f)
                throw new InvalidOperationException("diagnostic roll axis is not a principal inertia axis");
            float impulse = o.Omega / inverse.M33;
            bodies.AddAngularImpulse(tank.Body.ID, new Vector3(0, 0, impulse));
            var initialAngular = tank.Body.GetAngularVelocity();
            world.OptimizeBroadPhase();
            int firstBeyond90 = -1, roofStableTicks = 0, checkedStates = 0;
            float maximumTilt = 0, maximumBasisError = 0;
            var samples = new List<object>();
            string? error = null;
            try
            {
                for (tick = 1; tick <= o.Ticks; tick++)
                {
                    if ((tick - 1) % 6 == 0) tank.BeginAdvance();
                    tank.BeforeStep(BattleSceneInput.Control.Stop, (tick - 1) % 6 + 1, false);
                    var update = world.Update(1f / 60, 1, jobs); jobs.CheckThread();
                    if (update != PhysicsUpdateError.None || callbackFault != 0) throw new InvalidOperationException("actual Jolt update/contact fault");
                    tank.AfterStep();
                    var q = tank.Body.Rotation; var up = Vector3.Transform(Vector3.UnitY, q);
                    float tilt = MathF.Acos(Math.Clamp(up.Y, -1, 1)) * 180 / MathF.PI;
                    maximumTilt = MathF.Max(maximumTilt, tilt);
                    if (firstBeyond90 < 0 && tilt > 90) firstBeyond90 = tick;
                    var linear = tank.Body.GetLinearVelocity(); var angular = tank.Body.GetAngularVelocity();
                    bool roofStable = up.Y < -.95f && linear.Length() < .1f && angular.Length() < .1f && contactTick >= tick - 1;
                    roofStableTicks = roofStable ? roofStableTicks + 1 : 0;
                    if (tick % 6 != 0) continue;
                    var state = JsonSerializer.SerializeToElement(tank.State()).GetProperty("state");
                    var direction = state.GetProperty("direction");
                    var ypr = new Vector3(direction[0].GetSingle(), direction[1].GetSingle(), direction[2].GetSingle());
                    maximumBasisError = MathF.Max(maximumBasisError, BasisError(q, ypr)); checkedStates++;
                    if (maximumBasisError > 4e-6f) throw new InvalidOperationException("actual BattleTank.State full basis reconstruction error");
                    samples.Add(new { tick, quaternion_xyzw = Q(q), direction_ypr = V(ypr), tilt_degrees = tilt,
                        position_com = V(tank.Body.Position), linear_velocity = V(linear), angular_velocity = V(angular),
                        wheel_contacts = state.GetProperty("contacts").GetInt32(), floor_contact = contactTick >= tick - 1, roof_stable_ticks = roofStableTicks });
                }
            }
            catch (Exception e) { error = e.GetType().Name + ": " + e.Message; }
            var finalUp = Vector3.Transform(Vector3.UnitY, tank.Body.Rotation);
            float finalTilt = MathF.Acos(Math.Clamp(finalUp.Y, -1, 1)) * 180 / MathF.PI;
            bool gate = tether ? finalTilt <= 65 && roofStableTicks == 0 : firstBeyond90 > 0 && roofStableTicks >= 60;
            passed = error == null && gate && checkedStates == o.Ticks / 6 && maximumBasisError <= 4e-6f;
            return new { kind = source.Kind, source_slot = original.Slot, config_sha256 = source.ConfigHash,
                profile_sha256 = source.Binding.ProfileSha256, mass_kg = source.Config.GetProperty("mass_kg").GetSingle(),
                variant = tether ? "same_actual_constraint_test_override_PI_over_3" : "production_BattleTank_default_PI",
                result = passed ? "PASS" : "FAIL", error, initial_roll_degrees = o.Roll, initial_angular_speed = o.Omega,
                actual_initial_angular_velocity = V(initialAngular), one_initial_angular_impulse = impulse,
                ticks_requested = o.Ticks, ticks_completed = Math.Min(tick - 1, o.Ticks), first_beyond_90_tick = firstBeyond90,
                maximum_tilt_degrees = maximumTilt, final_tilt_degrees = finalTilt, final_roof_stable_ticks = roofStableTicks,
                final_floor_contact_tick = contactTick, checked_production_states = checkedStates, maximum_basis_error = maximumBasisError,
                contact_callbacks = callbackCount, samples };
        }
        finally { bodies.RemoveAndDestroyBody(floor.ID); }
    }
    public static int Main(string[] args)
    {
        bool initialized = false;
        try
        {
            var o = Parse(args);
            var manifest = BattleSceneInput.Load(o.Root, o.Manifest, o.Hash);
            if (manifest.Actors.Length != 2 || !manifest.Actors.Select(a => a.Kind).Order().SequenceEqual(new[] { "is7", "ms1" }))
                throw new InvalidDataException("expected genuine two-actor MS1/IS7 manifest");
            if (!Foundation.Init(false)) throw new InvalidOperationException("Jolt initialization failed");
            initialized = true;
            var results = new List<object>(); bool all = true;
            foreach (var actor in manifest.Actors)
                foreach (bool tether in new[] { false, true })
                {
                    try { results.Add(Run(o, actor, tether, out bool pass)); all &= pass; }
                    catch (Exception e) { all = false; results.Add(new { kind = actor.Kind, tether, result = "FAIL", error = e.GetType().Name + ": " + e.Message }); }
                }
            var binaries = Directory.EnumerateFiles(AppContext.BaseDirectory, "*.dll", SearchOption.AllDirectories)
                .Where(p => Path.GetFileName(p).Contains("Jolt", StringComparison.OrdinalIgnoreCase)).Order()
                .Select(p => new { path = p, sha256 = Sha(p), bytes = new FileInfo(p).Length }).ToArray();
            Console.WriteLine(JsonSerializer.Serialize(new { version = 1, result = all ? "PASS" : "FAIL", utc = DateTimeOffset.UtcNow,
                actual_pinned_jolt = true, native_client_acceptance = "NOT_RUN", historical_physics = "UNKNOWN",
                manifest_path = o.Manifest, manifest_sha256 = manifest.Hash, map = manifest.Map,
                authored_diagnostic_world = "flat 100m box, top y=0; genuine actor configs; catalog and map meshes deliberately not loaded",
                fixed_step = 1f / 60, collision_steps = 1, initial_body_origin_height = o.Height,
                subsequent_pose_or_velocity_setters = 0, controls = "production Control.Stop every substep", binaries, cases = results },
                new JsonSerializerOptions { WriteIndented = true }));
            return all ? 0 : 1;
        }
        catch (Exception e) { Console.WriteLine(JsonSerializer.Serialize(new { result = "FAIL", error = e.GetType().Name + ": " + e.Message })); return 1; }
        finally { if (initialized) Foundation.Shutdown(); }
    }
}
