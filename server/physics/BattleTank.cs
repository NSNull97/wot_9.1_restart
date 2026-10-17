using System.Numerics;
using JoltPhysicsSharp;

namespace MapDrive;

// Per-body resources/state only; the shared coordinator owns PhysicsSystem.Update.
internal sealed class BattleTank : IDisposable
{
    public readonly BattleSceneInput.Actor Source;
    public readonly Body Body;
    public readonly VehicleConstraint Constraint;
    public readonly AngularFractureResponse? Fracture;
    public readonly List<AngularFractureResponse.Contact> ReservedContacts = new();
    public readonly List<object> ObjectContacts = new();
    readonly PhysicsSystem world;
    readonly BoxShape shape;
    readonly VehicleCollisionTesterRay tester;
    readonly WheelSettingsTV[] wheels;
    readonly TrackedVehicleController controller;
    readonly TrackedHandling handling;
    readonly Queue<int> masks = new(6);
    readonly Vector3 center;
    readonly float forwardLimit, reverseLimit;
    public Vector3 PreVelocity;
    public BattleTank(PhysicsSystem system, BattleSceneInput.Actor source, CheckedInput.CatalogSpec? catalog)
        : this(system, source, catalog, true, true) { }
    // The explicit policy seam also compares baseline/candidate in one actual
    // Jolt build. Network/shared callers always use the three-argument form.
    internal BattleTank(PhysicsSystem system, BattleSceneInput.Actor source, CheckedInput.CatalogSpec? catalog,
        bool enablePoweredTurnLoss)
        : this(system, source, catalog, enablePoweredTurnLoss, true) { }
    internal BattleTank(PhysicsSystem system, BattleSceneInput.Actor source, CheckedInput.CatalogSpec? catalog,
        bool enablePoweredTurnLoss, bool enableIntentReversalBrake)
    {
        world = system; Source = source;
        var c = source.Config;
        float N(string key, float min, float max) => CheckedInput.Number(c.GetProperty(key), min, max);
        center = CheckedInput.Vector(c.GetProperty("body_center_offset"), -5, 5);
        float mass = N("mass_kg", 1000, 100000), radius = N("wheel_radius", .05f, 1), brake = N("track_max_brake_torque", 100, source.Kind is "wt-e100-128" or "fv215b-183" ? 300000 : 100000);
        forwardLimit = N("max_forward_mps", 1, 20); reverseLimit = N("max_reverse_mps", .5f, 10);
        var rotation = Quaternion.CreateFromAxisAngle(Vector3.UnitY, source.Yaw);
        shape = new BoxShape(source.Binding.HalfExtents);
        using var bodySettings = TrackedBodySettings.Create(shape,mass,source.Spawn + Vector3.Transform(center,rotation),rotation);
        Body=world.BodyInterface.CreateBody(bodySettings);
        world.BodyInterface.AddBody(Body.ID,Activation.Activate);
        source.Binding.Verify(Body);
        var points = c.GetProperty("wheel_points").EnumerateArray().Select(v => CheckedInput.Vector(v, -5, 5)).ToArray();
        if (points.Length != 6) throw new InvalidDataException("IPC7 support count");
        wheels = points.Select(p => new WheelSettingsTV
        {
            Position = p - center, SuspensionDirection = -Vector3.UnitY, WheelUp = Vector3.UnitY, WheelForward = Vector3.UnitZ,
            SuspensionMinLength = N("suspension_min", 0, 1), SuspensionMaxLength = N("suspension_max", .05f, 1), Radius = radius, Width = .25f,
            LongitudinalFriction = N("longitudinal_friction", .1f, 2), LateralFriction = N("lateral_friction", .1f, 2),
            SuspensionSpring = new SpringSettings(SpringMode.FrequencyAndDamping, 2, .7f)
        }).ToArray();
        using var settings = new TrackedVehicleControllerSettings();
        var engine = settings.Engine; engine.MaxTorque = N("engine_max_torque_nm", 10, 10000); settings.Engine = engine;
        var transmission = settings.Transmission;
        transmission.SwitchTime = TrackedHandling.GearSwitchTime; transmission.ClutchReleaseTime = TrackedHandling.ClutchReleaseTime;
        transmission.SwitchLatency = TrackedHandling.GearSwitchLatency; settings.Transmission = transmission;
        settings.SetTrack(0, new VehicleTrackSettings { DrivenWheel = 1, Wheels = [0, 1, 2], MaxBrakeTorque = brake, Inertia = TrackedHandling.TrackInertia(mass, radius) });
        settings.SetTrack(1, new VehicleTrackSettings { DrivenWheel = 4, Wheels = [3, 4, 5], MaxBrakeTorque = brake, Inertia = TrackedHandling.TrackInertia(mass, radius) });
        Constraint = new VehicleConstraint(Body, new VehicleConstraintSettings
        {
            // Owner policy 2026-10-17: shared battles allow side/roof rollovers.
            // PI spans the full up-vector angle; no artificial upright tether.
            // Legacy single-vehicle Program keeps its accepted handling policy.
            Up = Vector3.UnitY, Forward = Vector3.UnitZ, Wheels = wheels, Controller = settings, MaxPitchRollAngle = MathF.PI
        });
        tester = new VehicleCollisionTesterRay(1); Constraint.SetVehicleCollisionTester(tester);
        world.AddConstraint(Constraint); world.AddStepListener(Constraint);
        controller = Constraint.GetController<TrackedVehicleController>();
        handling = new TrackedHandling(MathF.Abs(points[3].X - points[0].X),
            CheckedInput.Number(c.GetProperty("handling").GetProperty("max_yaw_rate_rad_s"), .1f, 1.5f), mass, wheels, enablePoweredTurnLoss, enableIntentReversalBrake);
        handling.VerifyWheelSettings(Constraint);
        Fracture = catalog == null ? null : new AngularFractureResponse(mass, catalog, source.Binding);
    }
    public void BeginAdvance() { Fracture?.BeginAdvance(); ObjectContacts.Clear(); ReservedContacts.Clear(); }
    public void BeforeStep(BattleSceneInput.Control input, int substep, bool capture)
    {
        var q = Body.Rotation; PreVelocity = Body.GetLinearVelocity();
        if (capture) Fracture?.BeginSubstep(substep, AngularMotionFrame.Capture(Body, Source.Binding));
        var forward = Vector3.Transform(Vector3.UnitZ, q); var up = Vector3.Transform(Vector3.UnitY, q);
        handling.Apply(controller, Vector3.Dot(PreVelocity, forward), Vector3.Dot(Body.GetAngularVelocity(), up),
            input.Throttle, input.Steer, input.Brake, forwardLimit * input.SpeedPercent / 100, reverseLimit * input.SpeedPercent / 100, 1f / 60);
    }
    // Contact hold is a bounded server-side traction policy.  When a forward
    // command is active and this hull is pushing another hull, a solver impulse
    // must not turn the pusher into a backwards teleport.  We remove only the
    // negative component along the authoritative forward axis and preserve the
    // lateral/vertical solver result.
    public bool HoldForwardAgainstContact(bool contact, int throttle)
    {
        if (!contact || throttle <= 0) return false;
        var forward = Vector3.Transform(Vector3.UnitZ, Body.Rotation);
        var velocity = Body.GetLinearVelocity();
        float signed = Vector3.Dot(velocity, forward);
        if (!float.IsFinite(signed) || signed >= -.05f) return false;
        world.BodyInterface.SetLinearVelocity(Body.ID, velocity - forward * signed);
        return true;
    }
    public void AfterStep()
    {
        int mask = 0;
        for (int i = 0; i < 6; i++) if (Constraint.GetWheel(i).HasContact) mask |= 1 << i;
        if (masks.Count == 6) masks.Dequeue(); masks.Enqueue(mask);
        var pos = Body.Position; var velocity = Body.GetLinearVelocity(); var angular = Body.GetAngularVelocity();
        var bounds = Source.Config.GetProperty("bounds_xz");
        if (!Finite(pos, 2000) || pos.Y < -100 || pos.Y > 500 || !Finite(velocity, 25.001f) || !Finite(angular, 20) ||
            pos.X < bounds[0].GetSingle() - 1 || pos.X > bounds[2].GetSingle() + 1 || pos.Z < bounds[1].GetSingle() - 1 || pos.Z > bounds[3].GetSingle() + 1)
            throw new InvalidOperationException("IPC7 authoritative body motion outside bounds");
    }
    static bool Finite(Vector3 v, float max) => float.IsFinite(v.X) && float.IsFinite(v.Y) && float.IsFinite(v.Z) && MathF.Abs(v.X) <= max && MathF.Abs(v.Y) <= max && MathF.Abs(v.Z) <= max;
    public void CheckSettled()
    {
        if (Enumerable.Range(0, 6).Count(i => Constraint.GetWheel(i).HasContact) < 3 || Body.GetLinearVelocity().Length() > 1)
            throw new InvalidOperationException($"IPC7 actor failed to settle slot={Source.Slot} kind={Source.Kind} position={Body.Position} velocity={Body.GetLinearVelocity()}");
    }
    public object Metrics(BattleSceneInput.Control input) => MixedContactDiagnostics.Capture(
        Source.Slot, Source.Kind, Source.ConfigHash, Body, Constraint, controller, input);
    public object State()
    {
        Source.Binding.Verify(Body);
        var q = Body.Rotation; var origin = Body.Position - Vector3.Transform(center, q);
        var velocity = Body.GetLinearVelocity(); var angular = Body.GetAngularVelocity();
        var forward = Vector3.Transform(Vector3.UnitZ, q);
        var v = AngularMotionFrame.V;
        return new
        {
            slot = Source.Slot, kind = Source.Kind, config_sha256 = Source.ConfigHash, profile_sha256 = Source.Binding.ProfileSha256,
            state = new
            {
                position = v(origin), direction = v(BodyOrientation.ToYawPitchRoll(q)),
                speed = Vector3.Dot(velocity, forward), rspeed = angular.Y, contacts = Enumerable.Range(0, 6).Count(i => Constraint.GetWheel(i).HasContact),
                linear_velocity = v(velocity), angular_velocity = v(angular), wheel_contact_masks = masks.ToArray(),
                object_contacts = ObjectContacts.ToArray(), fractures = Fracture?.Receipts.Select(r => r.ToWire()).ToArray() ?? [],
                body_binding = Source.Binding.ToWire(), motion_witnesses = Fracture?.Witnesses.Select(w => w.ToWire()).ToArray() ?? []
            }
        };
    }
    public void Dispose()
    {
        world.RemoveStepListener(Constraint); world.RemoveConstraint(Constraint); Constraint.Dispose();
        world.BodyInterface.RemoveAndDestroyBody(Body.ID);
        tester.Dispose(); foreach (var wheel in wheels) wheel.Dispose(); shape.Dispose();
    }
}
