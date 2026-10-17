using System.Globalization;
using System.Numerics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using JoltPhysicsSharp;
using MapDrive;

internal static class SlopeChecks
{
    sealed record Options(string Root, string Manifest, string Hash, string Out, int Ticks, string Mode, string Steps, string Cone);
    static readonly BattleSceneInput.Control Drive = new(1, 0, false, 100);
    static float[] V(Vector3 v) => [v.X, v.Y, v.Z];
    static string Sha(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    static Options Parse(string[] args)
    {
        if (args.Length < 8 || args.Length > 16 || args.Length % 2 != 0) throw new InvalidDataException("expected --local-root ROOT --manifest PATH --manifest-sha256 SHA --out NEWDIR [--ticks 2400] [--mode both] [--collision-steps both] [--cone 180]");
        var fields = new Dictionary<string, string>(StringComparer.Ordinal);
        for (int i = 0; i < args.Length; i += 2) if (!fields.TryAdd(args[i], args[i + 1])) throw new InvalidDataException("duplicate option");
        string[] allowed = ["--local-root", "--manifest", "--manifest-sha256", "--out", "--ticks", "--mode", "--collision-steps", "--cone"];
        if (fields.Keys.Except(allowed).Any()) throw new InvalidDataException("unknown option");
        string Choice(string key, string fallback, params string[] choices)
        {
            string value = fields.GetValueOrDefault(key, fallback);
            return choices.Contains(value) ? value : throw new InvalidDataException("option outside bounds: " + key);
        }
        int ticks = int.Parse(fields.GetValueOrDefault("--ticks", "2400"), CultureInfo.InvariantCulture);
        if (ticks is < 600 or > 3600 || ticks % 6 != 0) throw new InvalidDataException("ticks must be 600..3600 and divisible by six");
        string root = Path.GetFullPath(fields["--local-root"]);
        string output = Path.GetFullPath(fields["--out"], root);
        if (Directory.Exists(output) || File.Exists(output) || !Directory.Exists(Path.GetDirectoryName(output))) throw new InvalidDataException("output must be a new directory beneath an existing owned parent");
        string parent = CheckedInput.Owned(root, Path.GetDirectoryName(output)!);
        if (string.IsNullOrEmpty(Path.GetFileName(output)) || Path.Combine(parent, Path.GetFileName(output)) != output)
            throw new InvalidDataException("new output must be a plain child of its checked parent");
        string hash = fields["--manifest-sha256"]; CheckedInput.Sha256(hash);
        return new(root, Path.GetFullPath(fields["--manifest"]), hash, output, ticks,
            Choice("--mode", "both", "both", "solo", "push"), Choice("--collision-steps", "both", "both", "1", "4"), Choice("--cone", "180", "both", "60", "180"));
    }
    static Vector3 Origin(BattleTank tank) => tank.Body.Position - Vector3.Transform(CheckedInput.Vector(tank.Source.Config.GetProperty("body_center_offset"), -5, 5), tank.Body.Rotation);
    static (Vector3[] Vertices, IndexedTriangle[] Triangles, object Proof) Geometry(int degrees)
    {
        float height = 80 * MathF.Tan(degrees * MathF.PI / 180);
        float[] zs = [-150, 0, 80, 150], ys = [0, 0, height, height];
        var vertices = new Vector3[8];
        for (int row = 0; row < 4; row++) { vertices[row * 2] = new(-30, ys[row], zs[row]); vertices[row * 2 + 1] = new(30, ys[row], zs[row]); }
        var triangles = new IndexedTriangle[6];
        var indices = new uint[6][];
        for (uint row = 0; row < 3; row++)
        {
            uint a = row * 2, b = a + 1, c = a + 2, d = a + 3;
            indices[row * 2] = [a, c, d]; indices[row * 2 + 1] = [a, d, b];
            triangles[row * 2] = new(a, c, d); triangles[row * 2 + 1] = new(a, d, b);
        }
        foreach (var t in indices)
        {
            var normal = Vector3.Cross(vertices[t[1]] - vertices[t[0]], vertices[t[2]] - vertices[t[0]]);
            if (!float.IsFinite(normal.LengthSquared()) || normal.Y <= 0) throw new InvalidDataException("authored mesh winding/degenerate face");
        }
        var document = new { kind = "authored_test_lab_continuous_flat_ramp_v1", degrees, vertices_xyz = vertices.Select(V).ToArray(), triangles_abc = indices };
        var proof = new { document, sha256 = Sha(JsonSerializer.SerializeToUtf8Bytes(document)), historical_091_geometry = false };
        return (vertices, triangles, proof);
    }
    static object Run(Options o, BattleSceneInput.Manifest manifest, int degrees, bool push, int steps, int cone, out bool passed)
    {
        string tag = $"slope-{degrees:D2}-{(push ? "push" : "solo")}-step{steps}-cone{cone}";
        var geometry = Geometry(degrees);
        using var pairs = new ObjectLayerPairFilterTable(2); pairs.EnableCollision(0, 1); pairs.EnableCollision(1, 1);
        using var broad = new BroadPhaseLayerInterfaceTable(2, 2); broad.MapObjectToBroadPhaseLayer(0, 0); broad.MapObjectToBroadPhaseLayer(1, 1);
        using var filter = new ObjectVsBroadPhaseLayerFilterTable(broad, 2, pairs, 2);
        using var jobs = new InlineJobSystem();
        using var world = new PhysicsSystem(new PhysicsSystemSettings { MaxBodies = 32, MaxBodyPairs = 8192, MaxContactConstraints = 8192,
            ObjectLayerPairFilter = pairs, BroadPhaseLayerInterface = broad, ObjectVsBroadPhaseLayerFilter = filter });
        using var shapeSettings = new MeshShapeSettings(geometry.Vertices.AsSpan(), geometry.Triangles.AsSpan());
        using var shape = new MeshShape(shapeSettings);
        var bodies = world.BodyInterface;
        using var floorSettings = new BodyCreationSettings(shape, Vector3.Zero, Quaternion.Identity, MotionType.Static, 0) { Friction = 1 };
        var floor = bodies.CreateBody(floorSettings); bodies.AddBody(floor.ID, Activation.DontActivate);
        var tanks = new List<BattleTank>();
        int tick = 0, pairTick = -1, callbacks = 0, callbackFault = 0;
        Vector3 pairNormal = default, pairPoint = default;
        float pairDepth = 0, maxPairDepth = 0;
        var hullContacts = new Dictionary<(int, uint), object>(); int omittedHull = 0;
        var diagnosticsPath = Path.Combine(o.Out, tag + ".mixed.ndjson");
        var pairPath = Path.Combine(o.Out, tag + ".pairs.ndjson");
        using var diagnostics = new MixedContactDiagnostics(o.Root, diagnosticsPath);
        using var pairStream = new FileStream(pairPath, FileMode.CreateNew, FileAccess.Write, FileShare.Read);
        long pairBytes = 0;
        try
        {
            var is7 = manifest.Actors.Single(a => a.Kind == "is7") with { Slot = 0, Spawn = new Vector3(0, 3, -45), Yaw = 0 };
            tanks.Add(new BattleTank(world, is7, null));
            if (push)
            {
                var ms1 = manifest.Actors.Single(a => a.Kind == "ms1") with { Slot = 1, Spawn = new Vector3(0, 3, -24), Yaw = 0 };
                tanks.Add(new BattleTank(world, ms1, null));
            }
            if (cone == 60) foreach (var tank in tanks) tank.Constraint.SetMaxPitchRollAngle(MathF.PI / 3);
            void Contact(in Body a, in Body b, in ContactManifold m)
            {
                try
                {
                    jobs.CheckThread();
                    if (++callbacks > (o.Ticks + 180) * 64) throw new InvalidOperationException("bounded pair contact callbacks");
                    if (m.IsNull || m.PointCount == 0) return;
                    float depth = m.PenetrationDepth;
                    if (!float.IsFinite(depth)) throw new InvalidDataException("nonfinite native manifold depth");
                    var aId = a.ID; var bId = b.ID;
                    var first = tanks.FirstOrDefault(t => t.Body.ID == aId);
                    var second = tanks.FirstOrDefault(t => t.Body.ID == bId);
                    if (first != null || second != null)
                    {
                        var actor = first ?? second!; var other = first != null ? b : a;
                        var key = (actor.Source.Slot, other.ID.ID);
                        if (!hullContacts.ContainsKey(key))
                        {
                            if (hullContacts.Count == 64) omittedHull++;
                            else hullContacts.Add(key, new { slot = actor.Source.Slot, other_body_id = other.ID.ID,
                                other_kind = first != null && second != null ? "tank" : "authored_test_lab_surface",
                                substep = (tick - 1) % 6 + 1, penetration_depth_m = depth,
                                point = V(first != null ? m.GetWorldSpaceContactPointOn1(0) : m.GetWorldSpaceContactPointOn2(0)),
                                normal_actor_to_other = V(first != null ? m.WorldSpaceNormal : -m.WorldSpaceNormal) });
                        }
                    }
                    if (!push) return;
                    bool forward = a.ID == tanks[0].Body.ID && b.ID == tanks[1].Body.ID;
                    bool reverse = b.ID == tanks[0].Body.ID && a.ID == tanks[1].Body.ID;
                    if (!forward && !reverse) return;
                    pairTick = tick; pairNormal = forward ? m.WorldSpaceNormal : -m.WorldSpaceNormal;
                    pairDepth = depth; maxPairDepth = MathF.Max(maxPairDepth, depth);
                    pairPoint = forward ? m.GetWorldSpaceContactPointOn1(0) : m.GetWorldSpaceContactPointOn2(0);
                }
                catch { callbackFault = 1; }
            }
            world.OnContactAdded += (PhysicsSystem _, in Body a, in Body b, in ContactManifold m, ref ContactSettings s) => Contact(a, b, m);
            world.OnContactPersisted += (PhysicsSystem _, in Body a, in Body b, in ContactManifold m, ref ContactSettings s) => Contact(a, b, m);
            world.OptimizeBroadPhase();
            void Step(bool drive)
            {
                foreach (var tank in tanks) tank.BeforeStep(drive && tank.Source.Slot == 0 ? Drive : BattleSceneInput.Control.Stop, (tick - 1) % 6 + 1, false);
                var update = world.Update(1f / 60, steps, jobs); jobs.CheckThread();
                if (update != PhysicsUpdateError.None || callbackFault != 0) throw new InvalidOperationException("actual Jolt update/contact fault");
                foreach (var tank in tanks) tank.AfterStep();
            }
            for (tick = 1; tick <= 180; tick++) Step(false);
            foreach (var tank in tanks) tank.CheckSettled();
            diagnostics.Write(0, 180, tanks.Select(t => t.Metrics(BattleSceneInput.Control.Stop)).ToArray(), [], 0);
            var driver = tanks[0];
            float startZ = Origin(driver).Z, maxZ = startZ, firstContactSpeed = 0, rampEntrySpeed = 0, worstSlopeSpeed = float.PositiveInfinity;
            int firstFlatContact = -1, flatPushTicks = 0, rampWheelTick = -1, centerEntryTick = -1, postRampPairTicks = 0,
                longestStall = 0, stallTicks = 0, negativeSpeedTicks = 0, lastDriveTick = 0;
            bool reached = false; string? error = null;
            var checkpoints = new List<object>();
            try
            {
                for (int driveTick = 1; driveTick <= o.Ticks; driveTick++)
                {
                    tick = 180 + driveTick; lastDriveTick = driveTick;
                    if ((driveTick - 1) % 6 == 0)
                    {
                        foreach (var tank in tanks) tank.BeginAdvance();
                        hullContacts.Clear(); omittedHull = 0;
                    }
                    Step(true);
                    var origin = Origin(driver); float speed = driver.Body.GetLinearVelocity().Z;
                    maxZ = MathF.Max(maxZ, origin.Z);
                    bool pairNow = pairTick == tick;
                    if (push && pairNow && origin.Z < -4 && speed > .5f)
                    {
                        flatPushTicks++;
                        if (firstFlatContact < 0) { firstFlatContact = driveTick; firstContactSpeed = speed; }
                    }
                    bool rampWheel = Enumerable.Range(0, 6).Any(i => { var w = driver.Constraint.GetWheel(i); return w.HasContact && w.ContactBodyID == floor.ID && w.ContactPosition.Z > .5f && w.ContactPosition.Z < 79; });
                    if (rampWheel && rampWheelTick < 0) { rampWheelTick = driveTick; rampEntrySpeed = speed; }
                    if (origin.Z >= 0 && centerEntryTick < 0) centerEntryTick = driveTick;
                    if (rampWheelTick > 0)
                    {
                        worstSlopeSpeed = MathF.Min(worstSlopeSpeed, speed);
                        stallTicks = MathF.Abs(speed) < .2f ? stallTicks + 1 : 0; longestStall = Math.Max(longestStall, stallTicks);
                        if (speed < -.2f) negativeSpeedTicks++;
                        if (pairNow) postRampPairTicks++;
                    }
                    if (MathF.Abs(origin.X) > 20 || origin.Z > 100) throw new InvalidOperationException("diagnostic left bounded ramp lane");
                    if (driveTick % 6 == 0)
                    {
                        long sequence = driveTick / 6;
                        var metrics = tanks.Select(t => t.Metrics(t.Source.Slot == 0 ? Drive : BattleSceneInput.Control.Stop)).ToArray();
                        diagnostics.Write(sequence, tick, metrics, hullContacts.Values.ToArray(), omittedHull);
                        var pairRow = new { tick, drive_tick = driveTick, pair_contact_this_substep = pairNow, last_pair_tick = pairTick,
                            normal_is7_to_ms1 = pairNow ? V(pairNormal) : null, point_on_is7_m = pairNow ? V(pairPoint) : null,
                            penetration_depth_m = pairNow ? (float?)pairDepth : null, ramp_wheel_contact = rampWheel,
                            actors = tanks.Select(t => new { kind = t.Source.Kind, origin_m = V(Origin(t)), state = t.State() }).ToArray() };
                        var bytes = JsonSerializer.SerializeToUtf8Bytes(pairRow);
                        if (bytes.Length > 32768 || pairBytes + bytes.Length + 1 > 16 * 1024 * 1024) throw new InvalidDataException("bounded pair diagnostic bytes");
                        pairStream.Write(bytes); pairStream.WriteByte(10); pairStream.Flush(); pairBytes += bytes.Length + 1;
                        if (driveTick % 60 == 0) checkpoints.Add(new { drive_tick = driveTick, is7_origin = V(origin), is7_velocity_z = speed,
                            ms1_origin = push ? V(Origin(tanks[1])) : null, pair_contact = pairNow, ramp_wheel_contact = rampWheel, longest_stall_ticks = longestStall });
                    }
                    bool climbing = origin.Z >= 20 && (!push || Origin(tanks[1]).Z >= 20 && pairTick >= tick - 60 && flatPushTicks >= 30);
                    if (driveTick % 6 == 0 && climbing && rampWheelTick > 0 && Vector3.Transform(Vector3.UnitY, driver.Body.Rotation).Y > .5f)
                    { reached = true; break; }
                }
            }
            catch (Exception e) { error = e.GetType().Name + ": " + e.Message; }
            passed = reached && error == null;
            return new { tag, result = passed ? "PASS" : "FAIL", error, geometry = geometry.Proof,
                collision_steps = steps, current_runtime_policy = steps == (push ? 4 : 1), constraint_cone_degrees = cone,
                production_default_constraint = cone == 180, push_stop_ms1 = push, requested_drive_ticks = o.Ticks, actual_drive_ticks = lastDriveTick,
                never_released_throttle_after_settle = true, start_is7_origin_z = startZ, final_is7_origin = V(Origin(driver)), maximum_is7_origin_z = maxZ,
                final_ms1_origin = push ? V(Origin(tanks[1])) : null, first_flat_pair_contact_drive_tick = firstFlatContact,
                first_flat_pair_contact_is7_speed_z = firstContactSpeed, flat_pushing_ticks_over_half_mps = flatPushTicks,
                first_ramp_wheel_drive_tick = rampWheelTick, is7_speed_z_at_first_ramp_wheel = rampEntrySpeed,
                first_is7_center_ramp_drive_tick = centerEntryTick, pair_ticks_after_first_ramp_wheel = postRampPairTicks,
                longest_under_point_two_mps_after_ramp_ticks = longestStall, reverse_after_ramp_ticks = negativeSpeedTicks,
                minimum_speed_z_after_ramp = float.IsFinite(worstSlopeSpeed) ? (float?)worstSlopeSpeed : null,
                contact_callbacks = callbacks, maximum_pair_manifold_depth_m = push && pairTick > 0 ? (float?)maxPairDepth : null,
                depth_scope = "actual ContactManifold.PenetrationDepth; no SAT proxy",
                final_driver_metrics = driver.Metrics(Drive),
                mixed_diagnostics_path = diagnosticsPath, pair_diagnostics_path = pairPath, checkpoints };
        }
        finally { foreach (var tank in tanks.AsEnumerable().Reverse()) tank.Dispose(); bodies.RemoveAndDestroyBody(floor.ID); }
    }
    public static int Main(string[] args)
    {
        bool initialized = false;
        try
        {
            var o = Parse(args);
            var manifest = BattleSceneInput.Load(o.Root, o.Manifest, o.Hash);
            if (manifest.Actors.Length != 2 || !manifest.Actors.Select(a => a.Kind).Order().SequenceEqual(new[] { "is7", "ms1" })) throw new InvalidDataException("requires genuine MS1/IS7 manifest");
            Directory.CreateDirectory(o.Out);
            CheckedInput.Owned(o.Root, o.Out);
            if (!Foundation.Init(false)) throw new InvalidOperationException("Jolt initialization failed"); initialized = true;
            var results = new List<object>(); bool all = true;
            foreach (int degrees in new[] { 6, 12 })
                foreach (bool push in o.Mode == "both" ? new[] { false, true } : new[] { o.Mode == "push" })
                    foreach (int steps in o.Steps == "both" ? new[] { 1, 4 } : new[] { int.Parse(o.Steps, CultureInfo.InvariantCulture) })
                        foreach (int cone in o.Cone == "both" ? new[] { 180, 60 } : new[] { int.Parse(o.Cone, CultureInfo.InvariantCulture) })
                        {
                            try { results.Add(Run(o, manifest, degrees, push, steps, cone, out bool pass)); all &= pass; }
                            catch (Exception e) { all = false; results.Add(new { degrees, push, steps, cone, result = "FAIL", error = e.GetType().Name + ": " + e.Message }); }
                        }
            var summary = new { version = 1, result = all ? "PASS" : "FAIL", utc = DateTimeOffset.UtcNow, actual_jolt = true,
                native_acceptance = "NOT_RUN", historical_091_ramp = false, owner_stall_cause = "UNKNOWN",
                manifest_path = o.Manifest, manifest_sha256 = manifest.Hash,
                actual_configs = manifest.Actors.Select(a => new { kind = a.Kind, config_sha256 = a.ConfigHash, profile_sha256 = a.Binding.ProfileSha256 }).ToArray(),
                setup = "authored test_lab mesh; genuine configs; no historical map/catalog; natural 180-tick settle; IS7 z=-45, STOP MS1 z=-24; only IS7 sustained throttle afterwards",
                pass_criterion = "IS7 origin >=20m uphill, actual ramp wheel support; push also MS1 >=20m, recent pair contact <=60ticks, >=30 flat pushing ticks at >0.5m/s; driver up.y>0.5; no fault",
                source_power_friction_edits = false, continuing_pose_velocity_setters = 0, cases = results };
            var bytes = JsonSerializer.SerializeToUtf8Bytes(summary, new JsonSerializerOptions { WriteIndented = true });
            using (var file = new FileStream(Path.Combine(o.Out, "summary.json"), FileMode.CreateNew, FileAccess.Write, FileShare.Read)) file.Write(bytes);
            Console.WriteLine(Encoding.UTF8.GetString(bytes)); return all ? 0 : 1;
        }
        catch (Exception e) { Console.WriteLine(JsonSerializer.Serialize(new { result = "FAIL", error = e.GetType().Name + ": " + e.Message })); return 1; }
        finally { if (initialized) Foundation.Shutdown(); }
    }
}
