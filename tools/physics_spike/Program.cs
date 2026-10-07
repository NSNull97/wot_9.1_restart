using System.Numerics;
using System.Text.Json;
using JoltPhysicsSharp;

// Isolated API/ABI experiment. These synthetic shapes are not WoT geometry.
// API reference: JoltPhysicsSharp 77a5be2dd30d587c1981dfcaf15851f18041b39c,
// samples/HelloWorld (MIT); no sample implementation copied.
if (!Foundation.Init(false))
    throw new InvalidOperationException("Jolt initialization failed");

try
{
    using var pairs = new ObjectLayerPairFilterTable(2);
    pairs.EnableCollision(0, 1);
    pairs.EnableCollision(1, 1);
    using var broad = new BroadPhaseLayerInterfaceTable(2, 2);
    broad.MapObjectToBroadPhaseLayer(0, 0);
    broad.MapObjectToBroadPhaseLayer(1, 1);
    using var filter = new ObjectVsBroadPhaseLayerFilterTable(broad, 2, pairs, 2);
    using var jobs = new JobSystemThreadPool();
    using var world = new PhysicsSystem(new PhysicsSystemSettings
    {
        MaxBodies = 64, MaxBodyPairs = 64, MaxContactConstraints = 64,
        ObjectLayerPairFilter = pairs, BroadPhaseLayerInterface = broad,
        ObjectVsBroadPhaseLayerFilter = filter
    });
    int contacts = 0;
    world.OnContactAdded += (PhysicsSystem system, in Body body1, in Body body2,
        in ContactManifold manifold, ref ContactSettings settings) => contacts++;
    using var groundShape = new BoxShape(new Vector3(5, 0.5f, 5));
    using var sphereShape = new SphereShape(0.5f);
    using var groundSettings = new BodyCreationSettings(groundShape,
        new Vector3(0, -0.5f, 0), Quaternion.Identity, MotionType.Static, 0);
    using var sphereSettings = new BodyCreationSettings(sphereShape,
        new Vector3(0, 2, 0), Quaternion.Identity, MotionType.Dynamic, 1);
    var bodies = world.BodyInterface;
    var ground = bodies.CreateBody(groundSettings);
    var sphere = bodies.CreateBody(sphereSettings);
    bodies.AddBody(ground.ID, Activation.DontActivate);
    bodies.AddBody(sphere.ID, Activation.Activate);
    try
    {
        world.OptimizeBroadPhase();
        var snapshots = new List<object>();
        for (int tick = 1; tick <= 300; tick++)
        {
            var error = world.Update(1.0f / 60, 1, jobs);
            if (error != PhysicsUpdateError.None)
                throw new InvalidOperationException($"Update {tick}: {error}");
            var p = bodies.GetCenterOfMassPosition(sphere.ID);
            if (!float.IsFinite(p.Y) || p.Y < 0.40f)
                throw new InvalidOperationException($"Sphere penetrated floor: {p}");
            if (tick % 30 == 0)
                snapshots.Add(new { tick, x = p.X, y = p.Y, z = p.Z });
        }
        var final = bodies.GetCenterOfMassPosition(sphere.ID);
        if (contacts == 0 || Math.Abs(final.Y - 0.5f) > 0.03f)
            throw new InvalidOperationException($"No stable contact: count={contacts}, y={final.Y}");
        Console.WriteLine(JsonSerializer.Serialize(new
        {
            status = "PASS", scenario = "synthetic sphere falls onto static box, 300 steps at 60 Hz",
            runtime = Environment.Version.ToString(), platform = Environment.OSVersion.ToString(),
            package = "JoltPhysicsSharp 2.22.0 / JoltPhysics.Native 1.1.0",
            contacts, finalY = final.Y, snapshots,
            trackedControllerTypePresent = typeof(TrackedVehicleController).FullName,
            historicalPhysics = "NOT_TESTED", trackedControllerSimulation = "NOT_RUN",
            crossPlatformDeterminism = "NOT_RUN"
        }, new JsonSerializerOptions { WriteIndented = true }));
    }
    finally
    {
        bodies.RemoveAndDestroyBody(sphere.ID);
        bodies.RemoveAndDestroyBody(ground.ID);
    }
}
finally
{
    Foundation.Shutdown();
}
