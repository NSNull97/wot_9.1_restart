using System.Numerics;
using System.Text.Json;
using JoltPhysicsSharp;

namespace MapDrive;

// TURRET-01: one detached turret+gun as a dynamic Jolt body. It is simulated
// to rest in its own debris PhysicsSystem built from the scene's static shapes
// (terrain, static obstacles, present catalog objects, map walls) plus dead
// vehicles as static boxes. The battle world is never stepped or changed.
// Live vehicles are not obstacles of the debris body (PROJECT policy).
internal static class TurretFlight
{
    public const string Policy = "project.turret01.detached-turret-jolt-body.v1";
    const int MaxPoints = 98, MaxSamples = 101, SubstepsPerSample = 6;
    // PROJECT surface policy; 0.9.1 client data carries no debris material.
    const float Friction = .8f, Restitution = .1f;
    public sealed record Request(int Slot, Vector3 Position, Vector3 Direction, Vector3 Linear, Vector3 Angular,
        Vector3[] Turret, Vector3[] Gun, int[] Wrecks);
    public sealed record Static(Shape Shape, Vector3 Position, Quaternion Rotation);
    public sealed record Wreck(int Slot, Vector3 HalfExtents, Vector3 Position, Quaternion Rotation);
    public sealed record Result(List<(Vector3 Position, Vector3 Direction)> Samples, bool Slept, int Substeps);

    public static Request Parse(JsonElement request, BattleSceneInput.Manifest manifest, uint generation, long seq, CheckedInput.Scene scene)
    {
        CheckedInput.Fields(request, "version", "op", "generation", "manifest_sha256", "catalog_sha256", "advance_seq",
            "scene_version", "removed_object_ids", "scene_sha256", "flight");
        BattleSceneInput.Header(request, manifest, generation);
        if (request.GetProperty("op").GetString() != "turret_flight" || request.GetProperty("advance_seq").GetInt64() != seq ||
            request.GetProperty("scene_version").GetUInt32() != scene.Version || request.GetProperty("scene_sha256").GetString() != scene.Hash ||
            !request.GetProperty("removed_object_ids").EnumerateArray().Select(v => v.GetUInt32()).SequenceEqual(scene.Ids.Order()))
            throw new InvalidDataException("IPC7 turret flight sequence/scene");
        var f = request.GetProperty("flight");
        CheckedInput.Fields(f, "slot", "position", "direction", "linear_velocity", "angular_velocity", "turret_points", "gun_points", "wreck_slots");
        int slot = f.GetProperty("slot").GetInt32();
        if (slot < 0 || slot >= manifest.Actors.Length) throw new InvalidDataException("IPC7 turret slot");
        Vector3[] Points(JsonElement rows)
        {
            if (rows.ValueKind != JsonValueKind.Array || rows.GetArrayLength() is < 4 or > MaxPoints) throw new InvalidDataException("IPC7 turret points bound");
            return rows.EnumerateArray().Select(v => CheckedInput.Vector(v, -20, 20)).ToArray();
        }
        var wrecks = f.GetProperty("wreck_slots");
        if (wrecks.ValueKind != JsonValueKind.Array || wrecks.GetArrayLength() > manifest.Actors.Length) throw new InvalidDataException("IPC7 wreck slots bound");
        var wreckSlots = wrecks.EnumerateArray().Select(v => v.GetInt32()).ToArray();
        if (wreckSlots.Any(s => s < 0 || s >= manifest.Actors.Length) || wreckSlots.Zip(wreckSlots.Skip(1)).Any(p => p.First >= p.Second))
            throw new InvalidDataException("IPC7 wreck slots order");
        var linear = CheckedInput.Vector(f.GetProperty("linear_velocity"), -20, 20);
        var angular = CheckedInput.Vector(f.GetProperty("angular_velocity"), -10, 10);
        if (linear.Length() > 20 || angular.Length() > 10) throw new InvalidDataException("IPC7 turret launch bound");
        return new(slot, CheckedInput.Vector(f.GetProperty("position"), -2000, 2000), CheckedInput.Vector(f.GetProperty("direction"), -MathF.PI - .001f, MathF.PI + .001f),
            linear, angular, Points(f.GetProperty("turret_points")), Points(f.GetProperty("gun_points")), wreckSlots);
    }

    // Native body convention Ry(yaw) * Rx(pitch) * Rz(roll), see BodyOrientation.
    static Quaternion Rotation(Vector3 direction) => Quaternion.CreateFromYawPitchRoll(direction.X, direction.Y, direction.Z);

    static (Vector3 Min, Vector3 Max) Bounds(IEnumerable<Vector3> local, Vector3 position, Quaternion rotation)
    {
        var min = new Vector3(float.MaxValue); var max = new Vector3(float.MinValue);
        foreach (var p in local) { var w = position + Vector3.Transform(p, rotation); min = Vector3.Min(min, w); max = Vector3.Max(max, w); }
        return (min, max);
    }
    static bool Overlap((Vector3 Min, Vector3 Max) a, (Vector3 Min, Vector3 Max) b) =>
        a.Min.X <= b.Max.X && b.Min.X <= a.Max.X && a.Min.Y <= b.Max.Y && b.Min.Y <= a.Max.Y && a.Min.Z <= b.Max.Z && b.Min.Z <= a.Max.Z;

    public static Result Simulate(Request request, IReadOnlyList<Static> statics, IReadOnlyList<Wreck> wrecks)
    {
        using var pairs = new ObjectLayerPairFilterTable(2); pairs.EnableCollision(0, 1); pairs.EnableCollision(1, 1);
        using var broad = new BroadPhaseLayerInterfaceTable(2, 2); broad.MapObjectToBroadPhaseLayer(0, 0); broad.MapObjectToBroadPhaseLayer(1, 1);
        using var filter = new ObjectVsBroadPhaseLayerFilterTable(broad, 2, pairs, 2);
        using var jobs = new InlineJobSystem();
        using var world = new PhysicsSystem(new PhysicsSystemSettings
        {
            MaxBodies = statics.Count + wrecks.Count + 8, MaxBodyPairs = 1024, MaxContactConstraints = 1024,
            ObjectLayerPairFilter = pairs, BroadPhaseLayerInterface = broad, ObjectVsBroadPhaseLayerFilter = filter
        });
        var bodies = world.BodyInterface; var added = new List<BodyID>(); var boxes = new List<BoxShape>();
        try
        {
            BodyID AddStatic(Shape shape, Vector3 position, Quaternion rotation)
            {
                using var creation = new BodyCreationSettings(shape, position, rotation, MotionType.Static, 0) { Friction = 1 };
                var body = bodies.CreateBody(creation); bodies.AddBody(body.ID, Activation.DontActivate); added.Add(body.ID); return body.ID;
            }
            foreach (var s in statics) AddStatic(s.Shape, s.Position, s.Rotation);
            // The own hull wreck joins only once the turret has left its box:
            // the launch pose sits on (and may overlap) that approximate box.
            Wreck? parent = null;
            foreach (var w in wrecks)
            {
                var box = new BoxShape(w.HalfExtents); boxes.Add(box);
                if (w.Slot == request.Slot) parent = w; else AddStatic(box, w.Position, w.Rotation);
            }
            world.OptimizeBroadPhase();
            using var hullTurret = new ConvexHullShapeSettings(request.Turret);
            using var hullGun = new ConvexHullShapeSettings(request.Gun);
            using var compound = new StaticCompoundShapeSettings();
            compound.AddShape(Vector3.Zero, Quaternion.Identity, hullTurret);
            compound.AddShape(Vector3.Zero, Quaternion.Identity, hullGun);
            using var shape = new StaticCompoundShape(compound);
            var rotation = Rotation(request.Direction);
            // The request's yaw/pitch/roll must name the same basis that the
            // reply's ToYawPitchRoll reports (native Ry*Rx*Rz convention).
            var back = Rotation(BodyOrientation.ToYawPitchRoll(rotation));
            if ((Vector3.Transform(Vector3.UnitZ, back) - Vector3.Transform(Vector3.UnitZ, rotation)).Length() > 1e-3f ||
                (Vector3.Transform(Vector3.UnitX, back) - Vector3.Transform(Vector3.UnitX, rotation)).Length() > 1e-3f)
                throw new InvalidOperationException("IPC7 turret orientation convention");
            using var creation = new BodyCreationSettings(shape, request.Position, rotation, MotionType.Dynamic, 1)
            {
                MotionQuality = MotionQuality.LinearCast, Friction = Friction, Restitution = Restitution, AllowSleeping = true,
                LinearVelocity = request.Linear, AngularVelocity = request.Angular
            };
            var turret = bodies.CreateBody(creation); bodies.AddBody(turret.ID, Activation.Activate); added.Add(turret.ID);
            var points = request.Turret.Concat(request.Gun).ToArray();
            var parentBounds = parent == null ? default : Bounds(
                new Vector3[] { new(-1, -1, -1), new(1, -1, -1), new(-1, 1, -1), new(1, 1, -1), new(-1, -1, 1), new(1, -1, 1), new(-1, 1, 1), new(1, 1, 1) }
                    .Select(c => c * parent.HalfExtents), parent.Position, parent.Rotation);
            var samples = new List<(Vector3, Vector3)> { (request.Position, request.Direction) };
            bool slept = false; int substeps = 0;
            while (samples.Count < MaxSamples && !slept)
            {
                for (int i = 0; i < SubstepsPerSample; i++)
                {
                    if (parent != null && !Overlap(Bounds(points, turret.Position, turret.Rotation), parentBounds))
                    {
                        AddStatic(boxes[wrecks.ToList().IndexOf(parent)], parent.Position, parent.Rotation); parent = null;
                    }
                    var result = world.Update(1f / 60, 1, jobs); jobs.CheckThread();
                    if (result != PhysicsUpdateError.None) throw new InvalidOperationException("IPC7 turret flight update fault");
                    substeps++;
                }
                var position = turret.Position; var q = turret.Rotation;
                if (!float.IsFinite(position.X) || !float.IsFinite(position.Y) || !float.IsFinite(position.Z) || position.Length() > 2000)
                    throw new InvalidOperationException("IPC7 turret flight left bounds");
                samples.Add((position, BodyOrientation.ToYawPitchRoll(q)));
                slept = !bodies.IsActive(turret.ID);
            }
            return new(samples, slept, substeps);
        }
        finally
        {
            foreach (var id in added.AsEnumerable().Reverse()) bodies.RemoveAndDestroyBody(id);
            foreach (var box in boxes) box.Dispose();
        }
    }
}
