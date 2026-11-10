using System.Globalization;
using System.Numerics;
using System.Text.Json;
using System.Text.Json.Nodes;
using JoltPhysicsSharp;
using MapDrive;

// PHYS-01 regression probe: production server/physics/*.cs bodies, constraint and handling on authored
// flat/tilted floors. Only the world geometry and the initial pose are test-authored. Not a native or
// historical proof. Usage: Phys01Checks <repo-root> <mode> [baseline]; baseline = former Jolt gearbox.
internal static class Probe
{
    const string Is7Physics = """
    {"body_center_offset":[0.0,1.0385702341794967,0.04841578006744385],"body_half_extents":[1.6451992988586426,0.5439350754022598,3.6090246438980103],"engine_max_torque_nm":2949.8732082310435,"lateral_friction":1.0,"longitudinal_friction":1.2,"mass_kg":68190.0,"max_forward_mps":16.555688000000004,"max_reverse_mps":4.1667000000000005,"stationary_steering_ratio":0.2,"suspension_max":0.35,"suspension_min":0.1,"track_max_brake_torque":75089.74730797112,"wheel_points":[[-1.30381,0.6675649869441986,-2.4024],[-1.30381,0.6675649869441986,0],[-1.30381,0.6675649869441986,2.4024],[1.30381,0.6675649869441986,-2.4024],[1.30381,0.6675649869441986,0],[1.30381,0.6675649869441986,2.4024]],"wheel_radius":0.3875649869441986}
    """;
    static readonly BattleSceneInput.Control Stop = BattleSceneInput.Control.Stop;
    static BattleSceneInput.Control C(int t, int s) => new(t, s, t == 0 && s == 0, 100);
    static readonly Dictionary<string, JsonElement> Definitions = new();
    static bool Reference = true;

    static JsonElement Config(string kind)
    {
        JsonNode physics; double yaw;
        if (kind == "is7") { physics = JsonNode.Parse(Is7Physics)!; yaw = 0.4886921905584123; }
        else
        {
            var d = Definitions[kind];
            physics = JsonNode.Parse(d.GetProperty("physics").GetRawText())!;
            yaw = d.GetProperty("handling").GetProperty("max_yaw_rate_rad_s").GetDouble();
        }
        var o = physics.AsObject();
        o["version"] = 3; o["profile"] = "test_lab";
        o["bounds_xz"] = new JsonArray(-900, -900, 900, 900);
        o["handling"] = new JsonObject { ["version"] = 1, ["policy"] = "p05b-track-yaw-v1", ["max_yaw_rate_rad_s"] = yaw };
        return JsonDocument.Parse(o.ToJsonString()).RootElement.Clone();
    }

    sealed class World : IDisposable
    {
        public readonly ObjectLayerPairFilterTable Pairs; public readonly BroadPhaseLayerInterfaceTable Broad;
        public readonly ObjectVsBroadPhaseLayerFilterTable Filter; public readonly InlineJobSystem Jobs; public readonly PhysicsSystem System;
        public readonly List<BattleTank> Tanks = new(); readonly List<IDisposable> shapes = new();
        public bool HullContact; public int Tick;
        public World()
        {
            Pairs = new ObjectLayerPairFilterTable(2); Pairs.EnableCollision(0, 1); Pairs.EnableCollision(1, 1);
            Broad = new BroadPhaseLayerInterfaceTable(2, 2); Broad.MapObjectToBroadPhaseLayer(0, 0); Broad.MapObjectToBroadPhaseLayer(1, 1);
            Filter = new ObjectVsBroadPhaseLayerFilterTable(Broad, 2, Pairs, 2); Jobs = new InlineJobSystem();
            System = new PhysicsSystem(new PhysicsSystemSettings { MaxBodies = 64, MaxBodyPairs = 8192, MaxContactConstraints = 8192,
                ObjectLayerPairFilter = Pairs, BroadPhaseLayerInterface = Broad, ObjectVsBroadPhaseLayerFilter = Filter });
            System.OnContactAdded += (PhysicsSystem _, in Body a, in Body b, in ContactManifold m, ref ContactSettings s) => Contact(a, b, ref s);
            System.OnContactPersisted += (PhysicsSystem _, in Body a, in Body b, in ContactManifold m, ref ContactSettings s) => Contact(a, b, ref s);
        }
        void Contact(in Body a, in Body b, ref ContactSettings settings)
        {
            uint x = a.ID.ID, y = b.ID.ID;
            var first = Tanks.FirstOrDefault(t => t.Body.ID.ID == x); var second = Tanks.FirstOrDefault(t => t.Body.ID.ID == y);
            // Mirrors BattleScene.Contact.
            if ((first?.ReferenceRules ?? false) || (second?.ReferenceRules ?? false))
                settings.CombinedFriction = ReferenceTraction.HullContactFriction(first != null && second != null);
            if (first != null && second != null) HullContact = true;
        }
        public void Static(Vector3 half, Vector3 position, Quaternion rotation)
        {
            var shape = new BoxShape(half); shapes.Add(shape);
            using var s = new BodyCreationSettings(shape, position, rotation, MotionType.Static, 0) { Friction = 1 };
            var body = System.BodyInterface.CreateBody(s); System.BodyInterface.AddBody(body.ID, Activation.DontActivate);
        }
        public BattleTank Add(string kind, Vector3 spawn, float yaw)
        {
            var config = Config(kind);
            var half = CheckedInput.Vector(config.GetProperty("body_half_extents"), .1f, 5);
            float mass = config.GetProperty("mass_kg").GetSingle();
            AngularBodyBinding binding;
            if (kind == "is7") binding = AngularBodyBinding.Select(config);
            else using (var shape = new BoxShape(half))
            using (var settings = TrackedBodySettings.Create(shape, mass, new Vector3(0, 300, 0), Quaternion.Identity))
            {
                var body = System.BodyInterface.CreateBody(settings); var m = body.MotionProperties;
                binding = new AngularBodyBinding(kind, new string('0', 64), mass, half, m.InverseMassUnchecked, m.InverseInertiaDiagonal, m.InertiaRotation);
                System.BodyInterface.DestroyBody(body.ID);
            }
            var actor = new BattleSceneInput.Actor(Tanks.Count, kind, new string('0', 64), config, binding, spawn, yaw);
            var tank = new BattleTank(System, actor, null, true, true, Reference); Tanks.Add(tank); return tank;
        }
        // Mirrors BattleScene.Advance for tanks without a destructible catalog: four collision steps,
        // HoldForwardAgainstContact with the per-batch hull-contact flag.
        public void Step(params BattleSceneInput.Control[] controls)
        {
            if (Tick % 6 == 0) { HullContact = false; foreach (var t in Tanks) t.BeginAdvance(); }
            for (int i = 0; i < Tanks.Count; i++) Tanks[i].BeforeStep(controls[i], Tick % 6 + 1, false);
            var r = System.Update(1f / 60, TrackedBodySettings.StockCollisionSteps, Jobs);
            if (r != PhysicsUpdateError.None) throw new InvalidOperationException("Jolt update error");
            for (int i = 0; i < Tanks.Count; i++) { Tanks[i].HullContact = HullContact; Tanks[i].HoldForwardAgainstContact(HullContact, controls[i].Throttle); Tanks[i].AfterStep(); }
            Tick++;
        }
        public void Dispose() { foreach (var t in Tanks.AsEnumerable().Reverse()) t.Dispose(); System.Dispose(); foreach (var s in shapes) s.Dispose(); }
    }
    static float Fwd(BattleTank t) => Vector3.Dot(t.Body.GetLinearVelocity(), Vector3.Transform(Vector3.UnitZ, t.Body.Rotation));
    static float Mass(BattleTank t) => t.Source.Config.GetProperty("mass_kg").GetSingle();
    static string F(float v) => v.ToString("0.###", CultureInfo.InvariantCulture);

    static void Flat(World w) => w.Static(new Vector3(800, .5f, 800), new Vector3(0, -.5f, 0), Quaternion.Identity);

    static void Accel(string kind)
    {
        using var w = new World(); Flat(w); var t = w.Add(kind, new Vector3(0, .1f, -700), 0);
        for (int i = 0; i < 180; i++) w.Step(Stop);
        var ctl = t.Constraint.GetController<TrackedVehicleController>();
        Console.WriteLine($"## accel {kind} mass={Mass(t)} weight_kN={F(Mass(t) * 9.81f / 1000)}");
        float prev = 0; float peak = 0; float t10 = -1, tmax = -1; float limit = t.Source.Config.GetProperty("max_forward_mps").GetSingle();
        for (int i = 1; i <= 60 * 40; i++)
        {
            w.Step(C(1, 0)); float v = Fwd(t);
            if (i % 30 == 0)
            {
                float a = (v - prev) / .5f; prev = v; peak = MathF.Max(peak, a);
                if (i <= 60 * 12 || i % 300 == 0) Console.WriteLine($"t={F(i / 60f)} v={F(v)} a={F(a)} F_kN={F(a * Mass(t) / 1000)} F/W={F(a / 9.81f)} gear={ctl.Transmission.CurrentGear} rpm={F(ctl.Engine.CurrentRPM)} power_kW={F(a * Mass(t) * v / 1000)}");
            }
            if (t10 < 0 && v >= 10) t10 = i / 60f;
            if (tmax < 0 && v >= limit * .95f) tmax = i / 60f;
        }
        Console.WriteLine($"summary {kind}: peak_a={F(peak)} peak_F/W={F(peak / 9.81f)} t_to_10mps={F(t10)} t_to_95pct={F(tmax)} limit={F(limit)}");
    }

    // Stall force: drive into an immovable wall and read the summed longitudinal wheel impulses.
    static void Stall(string kind)
    {
        using var w = new World(); Flat(w);
        var t = w.Add(kind, new Vector3(0, .1f, 0), 0);
        float hz = t.Source.Binding.HalfExtents.Z;
        w.Static(new Vector3(10, 5, 1), new Vector3(0, 5, hz + 1.3f), Quaternion.Identity);
        for (int i = 0; i < 180; i++) w.Step(Stop);
        double sum = 0; int n = 0;
        for (int i = 1; i <= 600; i++)
        {
            w.Step(C(1, 0));
            if (i > 300) { for (int k = 0; k < 6; k++) sum += MathF.Abs(t.Constraint.GetWheel(k).LongitudinalLambda); n++; }
        }
        double force = sum / n * 60 * TrackedBodySettings.StockCollisionSteps; // impulse per collision sub-step
        var ctl = t.Constraint.GetController<TrackedVehicleController>();
        Console.WriteLine("   wheels: " + string.Join(" | ", Enumerable.Range(0, 6).Select(k => { var wh = t.Constraint.GetWheel(k); return $"N={F(wh.SuspensionLambda * 240 / 1000)}kN L={F(wh.LongitudinalLambda * 240 / 1000)}kN c={wh.HasContact}"; })) + $" trackW={F(ctl.LeftTrack.AngularVelocity)}/{F(ctl.RightTrack.AngularVelocity)} pitchUpY={F(Vector3.Transform(Vector3.UnitZ, t.Body.Rotation).Y)} motor={F(ctl.ForwardInput)} offered_Nm={F(ctl.Engine.GetTorque(1))}");
        Console.WriteLine($"## stall {kind}: mean_longitudinal_force_kN={F((float)force / 1000)} F/W={F((float)(force / (Mass(t) * 9.81)))} gear={ctl.Transmission.CurrentGear} rpm={F(ctl.Engine.CurrentRPM)} v={F(Fwd(t))}");
    }

    static void Push(string pusher, string target, float gap, float targetYaw, bool targetBraked, string label)
    {
        using var w = new World(); Flat(w);
        var a = w.Add(pusher, new Vector3(0, .1f, 0), 0);
        var cb = Config(target); var hb = CheckedInput.Vector(cb.GetProperty("body_half_extents"), .1f, 5);
        float reach = MathF.Abs(MathF.Sin(targetYaw)) > .5f ? hb.X : hb.Z;
        float z0 = a.Source.Binding.HalfExtents.Z + reach + gap;
        var b = w.Add(target, new Vector3(0, .1f, z0), targetYaw);
        var free = new BattleSceneInput.Control(0, 0, false, 100);
        for (int i = 0; i < 180; i++) w.Step(Stop, Stop);
        float startA = a.Body.Position.Z, startB = b.Body.Position.Z; int contact = -1; float vContact = 0;
        var marks = new List<string>();
        for (int i = 1; i <= 60 * 25 && (contact < 0 || i - contact <= 600); i++)
        {
            w.Step(C(1, 0), targetBraked ? Stop : free);
            if (contact < 0 && w.HullContact) { contact = i; vContact = Fwd(a); }
            if (contact >= 0 && new[] { 30, 60, 180, 300, 600 }.Contains(i - contact))
                marks.Add($"+{F((i - contact) / 60f)}s vA={F(Fwd(a))} vB={F(b.Body.GetLinearVelocity().Z)} dB={F(b.Body.Position.Z - startB)}");
        }
        string Load(BattleTank t) { var c = t.Constraint.GetController<TrackedVehicleController>(); float w = Mass(t) * 9.81f / 1000;
            return $"N/W={F(Enumerable.Range(0, 6).Sum(k => t.Constraint.GetWheel(k).SuspensionLambda) * 240 / 1000 / w)} L/W={F(Enumerable.Range(0, 6).Sum(k => t.Constraint.GetWheel(k).LongitudinalLambda) * 240 / 1000 / w)} contacts={Enumerable.Range(0, 6).Count(k => t.Constraint.GetWheel(k).HasContact)} trackV={F(c.LeftTrack.AngularVelocity * t.Constraint.GetWheel(0).Settings.Radius)} motor={F(c.ForwardInput)} brake={F(c.BrakeInput)} pitch={F(MathF.Asin(Vector3.Transform(Vector3.UnitZ, t.Body.Rotation).Y) * 57.2958f)}"; }
        marks.Add("pusher " + Load(a)); marks.Add("target " + Load(b));
        var upB = Vector3.Transform(Vector3.UnitY, b.Body.Rotation); var upA = Vector3.Transform(Vector3.UnitY, a.Body.Rotation);
        Console.WriteLine($"## push {label}: {pusher}({Mass(a)}kg) -> {target}({Mass(b)}kg) gap={gap} braked={targetBraked} contact_t={F(contact / 60f)} v_at_contact={F(vContact)}");
        foreach (var m in marks) Console.WriteLine("   " + m);
        Console.WriteLine($"   final: pusher_travel={F(a.Body.Position.Z - startA)} target_travel={F(b.Body.Position.Z - startB)} target_side={F(b.Body.Position.X)} tiltA={F(MathF.Acos(Math.Clamp(upA.Y, -1, 1)) * 57.2958f)} tiltB={F(MathF.Acos(Math.Clamp(upB.Y, -1, 1)) * 57.2958f)} yB={F(b.Body.Position.Y)}");
    }

    // Tilted plane: rotation about world Z by alpha; the tank heads along the contour (+Z).
    static void Slope(string kind, float degrees, int throttle, int steer, float seconds, string label)
    {
        using var w = new World(); float alpha = degrees * MathF.PI / 180;
        var q = Quaternion.CreateFromAxisAngle(Vector3.UnitZ, alpha);
        var n = Vector3.Transform(Vector3.UnitY, q); var across = Vector3.Transform(Vector3.UnitX, q); // across points uphill (+X rises)
        w.Static(new Vector3(800, .5f, 800), -.5f * n, q);
        var t = w.Add(kind, new Vector3(0, 50, 0), 0);
        var center = CheckedInput.Vector(t.Source.Config.GetProperty("body_center_offset"), -5, 5);
        w.System.BodyInterface.SetPositionAndRotation(t.Body.ID, Vector3.Transform(center + new Vector3(0, .12f, 0), q), q, Activation.Activate);
        w.System.BodyInterface.SetLinearVelocity(t.Body.ID, Vector3.Zero);
        float maxTilt = 0, maxSlip = 0; int over = -1; float settleDown = 0;
        float Tilt() => MathF.Acos(Math.Clamp(Vector3.Dot(Vector3.Transform(Vector3.UnitY, t.Body.Rotation), n), -1, 1)) * 57.2958f;
        string error = "";
        try
        {
            for (int i = 0; i < 180; i++) w.Step(Stop);
            settleDown = -Vector3.Dot(t.Body.Position, across); float tiltSettle = Tilt();
            for (int i = 1; i <= seconds * 60; i++)
            {
                w.Step(C(throttle, steer));
                float tilt = Tilt(); maxTilt = MathF.Max(maxTilt, tilt);
                if (over < 0 && tilt > 70) over = i;
                var v = t.Body.GetLinearVelocity(); float lat = Vector3.Dot(v, Vector3.Transform(Vector3.UnitX, t.Body.Rotation));
                maxSlip = MathF.Max(maxSlip, MathF.Abs(lat));
            }
            Console.WriteLine($"## slope {label} {kind} {degrees}deg throttle={throttle} steer={steer}: settle_slide_down={F(settleDown)}m settle_tilt={F(tiltSettle)} max_tilt_vs_plane={F(maxTilt)} final_tilt={F(Tilt())} rollover_at={(over < 0 ? "none" : F(over / 60f) + "s")} max_lateral_speed={F(maxSlip)} downhill_travel={F(-Vector3.Dot(t.Body.Position, across))} forward_travel={F(t.Body.Position.Z)} speed={F(Fwd(t))} contacts={Enumerable.Range(0, 6).Count(k => t.Constraint.GetWheel(k).HasContact)}");
        }
        catch (Exception e) { error = e.Message; Console.WriteLine($"## slope {label} {kind} {degrees}deg throttle={throttle} steer={steer}: ERROR {error} max_tilt={F(maxTilt)} rollover_at={(over < 0 ? "none" : F(over / 60f) + "s")}"); }
    }

    // Flat: full speed, then a powered turn. Reports slip angle, roll and speed kept.
    static void Turn(string kind, int steer)
    {
        using var w = new World(); Flat(w); var t = w.Add(kind, new Vector3(0, .1f, -600), 0);
        for (int i = 0; i < 180; i++) w.Step(Stop);
        for (int i = 0; i < 60 * 25; i++) w.Step(C(1, 0));
        float v0 = Fwd(t); float maxSlipAngle = 0, maxRoll = 0, maxYaw = 0, maxLatAcc = 0; Vector3 prevV = t.Body.GetLinearVelocity();
        for (int i = 1; i <= 60 * 8; i++)
        {
            w.Step(C(1, steer));
            var v = t.Body.GetLinearVelocity(); var q = t.Body.Rotation;
            float f = Vector3.Dot(v, Vector3.Transform(Vector3.UnitZ, q)), l = Vector3.Dot(v, Vector3.Transform(Vector3.UnitX, q));
            maxSlipAngle = MathF.Max(maxSlipAngle, MathF.Abs(MathF.Atan2(l, MathF.Abs(f))) * 57.2958f);
            maxRoll = MathF.Max(maxRoll, MathF.Acos(Math.Clamp(Vector3.Transform(Vector3.UnitY, q).Y, -1, 1)) * 57.2958f);
            maxYaw = MathF.Max(maxYaw, MathF.Abs(t.Body.GetAngularVelocity().Y));
            var acc = (v - prevV) * 60; prevV = v; maxLatAcc = MathF.Max(maxLatAcc, MathF.Abs(Vector3.Dot(acc, Vector3.Transform(Vector3.UnitX, q))));
        }
        float vTurn = Fwd(t);
        // release everything while still turning: coast behaviour
        for (int i = 0; i < 120; i++) w.Step(C(0, steer));
        Console.WriteLine($"## turn {kind} steer={steer}: v_straight={F(v0)} v_after_8s_turn={F(vTurn)} max_slip_angle_deg={F(maxSlipAngle)} max_tilt_deg={F(maxRoll)} max_yaw_rate={F(maxYaw)} profile_yaw={F(t.Source.Config.GetProperty("handling").GetProperty("max_yaw_rate_rad_s").GetSingle())} max_lat_acc={F(maxLatAcc)} v_after_2s_coast_turn={F(Fwd(t))}");
    }

    // One-sided bump: a 0.35 m high, 1 m long box under the right track at speed.
    static void Bump(string kind, float height)
    {
        using var w = new World(); Flat(w);
        var t = w.Add(kind, new Vector3(0, .1f, -250), 0);
        float x = MathF.Abs(t.Source.Config.GetProperty("wheel_points")[3][0].GetSingle());
        w.Static(new Vector3(.6f, height, .5f), new Vector3(x, 0, 0), Quaternion.Identity);
        for (int i = 0; i < 180; i++) w.Step(Stop);
        float maxTilt = 0; int over = -1; float vBefore = 0; string error = "";
        try
        {
            for (int i = 1; i <= 60 * 40; i++)
            {
                w.Step(C(1, 0));
                if (t.Body.Position.Z < -8) vBefore = Fwd(t);
                float tilt = MathF.Acos(Math.Clamp(Vector3.Transform(Vector3.UnitY, t.Body.Rotation).Y, -1, 1)) * 57.2958f;
                if (t.Body.Position.Z > -8) maxTilt = MathF.Max(maxTilt, tilt);
                if (over < 0 && tilt > 70) over = i;
                if (t.Body.Position.Z > 60) break;
            }
        }
        catch (Exception e) { error = " ERROR " + e.Message; }
        Console.WriteLine($"## bump {kind} h={height}: v_before={F(vBefore)} max_tilt_deg={F(maxTilt)} rollover={(over < 0 ? "none" : "yes")} v_after={F(Fwd(t))} yaw_deviation_deg={F(MathF.Atan2(Vector3.Transform(Vector3.UnitZ, t.Body.Rotation).X, Vector3.Transform(Vector3.UnitZ, t.Body.Rotation).Z) * 57.2958f)}{error}");
    }


    // Side slope with a rock (box) under the uphill or downhill track.
    static void SlopeRock(string kind, float degrees, float rock, bool uphill, float runUp)
    {
        using var w = new World(); float alpha = degrees * MathF.PI / 180;
        var q = Quaternion.CreateFromAxisAngle(Vector3.UnitZ, alpha);
        var n = Vector3.Transform(Vector3.UnitY, q); var across = Vector3.Transform(Vector3.UnitX, q);
        w.Static(new Vector3(800, .5f, 800), -.5f * n, q);
        var t = w.Add(kind, new Vector3(0, 50, 0), 0);
        var center = CheckedInput.Vector(t.Source.Config.GetProperty("body_center_offset"), -5, 5);
        float x = MathF.Abs(t.Source.Config.GetProperty("wheel_points")[3][0].GetSingle()) * (uphill ? 1 : -1);
        w.Static(new Vector3(.6f, rock, .5f), across * x + new Vector3(0, 0, runUp), q);
        w.System.BodyInterface.SetPositionAndRotation(t.Body.ID, Vector3.Transform(center + new Vector3(0, .12f, 0), q), q, Activation.Activate);
        w.System.BodyInterface.SetLinearVelocity(t.Body.ID, Vector3.Zero);
        float maxTilt = 0; int over = -1; float vBefore = 0; string error = "";
        float Tilt() => MathF.Acos(Math.Clamp(Vector3.Dot(Vector3.Transform(Vector3.UnitY, t.Body.Rotation), n), -1, 1)) * 57.2958f;
        try
        {
            for (int i = 0; i < 180; i++) w.Step(Stop);
            for (int i = 1; i <= 60 * 30; i++)
            {
                w.Step(C(1, 0));
                if (t.Body.Position.Z < runUp - 8) vBefore = Fwd(t); else maxTilt = MathF.Max(maxTilt, Tilt());
                if (over < 0 && Tilt() > 70) over = i;
                if (t.Body.Position.Z > runUp + 40 || (over > 0 && i - over > 240)) break;
            }
        }
        catch (Exception e) { error = " ERROR " + e.Message; }
        var up = Vector3.Transform(Vector3.UnitY, t.Body.Rotation);
        Console.WriteLine($"## slope-rock {kind} slope={degrees} rock={rock} under={(uphill ? "uphill" : "downhill")} track v_before={F(vBefore)}: max_tilt_vs_plane={F(maxTilt)} rollover={(over < 0 ? "none" : "YES")} final_tilt={F(Tilt())} world_up_y={F(up.Y)} downhill_travel={F(-Vector3.Dot(t.Body.Position, across))}{error}");
    }

    // Flat ground, a one-track ramp (rises along +Z) under the right track.
    // The slab ends at topHeight: a rock or embankment under one track, then a drop back to the ground.
    static void Ramp(string kind, float rampDegrees, float runUp, float topHeight)
    {
        using var w = new World(); Flat(w);
        var t = w.Add(kind, new Vector3(0, .1f, -runUp), 0);
        float x = MathF.Abs(t.Source.Config.GetProperty("wheel_points")[3][0].GetSingle());
        float a = rampDegrees * MathF.PI / 180; var q = Quaternion.CreateFromAxisAngle(Vector3.UnitX, -a);
        float halfLength = topHeight / MathF.Sin(a) / 2;
        var along = Vector3.Transform(Vector3.UnitZ, q); var nrm = Vector3.Transform(Vector3.UnitY, q);
        w.Static(new Vector3(.7f, .25f, halfLength), new Vector3(x, 0, 0) + along * halfLength - nrm * .25f, q);
        for (int i = 0; i < 180; i++) w.Step(Stop);
        float maxTilt = 0; int over = -1; float vBefore = 0; string error = "";
        float Tilt() => MathF.Acos(Math.Clamp(Vector3.Transform(Vector3.UnitY, t.Body.Rotation).Y, -1, 1)) * 57.2958f;
        try
        {
            for (int i = 1; i <= 60 * 40; i++)
            {
                w.Step(C(1, 0));
                if (t.Body.Position.Z < -6) vBefore = Fwd(t); else maxTilt = MathF.Max(maxTilt, Tilt());
                if (over < 0 && Tilt() > 70) over = i;
                if (t.Body.Position.Z > 40 || (over > 0 && i - over > 300)) break;
                if (t.Body.Position.Z > -6 && i > 60 * 20) break;
            }
        }
        catch (Exception e) { error = " ERROR " + e.Message; }
        Console.WriteLine($"## one-track ramp {kind} ramp={rampDegrees}deg top={topHeight}m run_up={runUp}m v_before={F(vBefore)}: max_tilt={F(maxTilt)} rollover={(over < 0 ? "none" : "YES")} final_tilt={F(Tilt())} final_z={F(t.Body.Position.Z)} final_x={F(t.Body.Position.X)}{error}");
    }

    // Steep traverse: where does the hull slide and where does it tip, standing and moving.
    static void Steep(string kind, float degrees)
    {
        using var w = new World(); float alpha = degrees * MathF.PI / 180;
        var q = Quaternion.CreateFromAxisAngle(Vector3.UnitZ, alpha);
        var n = Vector3.Transform(Vector3.UnitY, q); var across = Vector3.Transform(Vector3.UnitX, q);
        w.Static(new Vector3(800, .5f, 800), -.5f * n + new Vector3(0, 300, 0), q);
        var t = w.Add(kind, new Vector3(0, 400, 0), 0);
        var center = CheckedInput.Vector(t.Source.Config.GetProperty("body_center_offset"), -5, 5);
        w.System.BodyInterface.SetPositionAndRotation(t.Body.ID, new Vector3(0, 300, 0) + Vector3.Transform(center + new Vector3(0, .12f, 0), q), q, Activation.Activate);
        w.System.BodyInterface.SetLinearVelocity(t.Body.ID, Vector3.Zero);
        float Tilt() => MathF.Acos(Math.Clamp(Vector3.Dot(Vector3.Transform(Vector3.UnitY, t.Body.Rotation), n), -1, 1)) * 57.2958f;
        float Down() => -Vector3.Dot(t.Body.Position - new Vector3(0, 300, 0), across);
        string error = ""; float standDown = 0, standTilt = 0, maxTilt = 0; int over = -1;
        try
        {
            for (int i = 0; i < 360; i++) { w.Step(Stop); maxTilt = MathF.Max(maxTilt, Tilt()); if (over < 0 && Tilt() > 70) over = i; }
            standDown = Down(); standTilt = Tilt();
            for (int i = 0; i < 360 && over < 0; i++) { w.Step(C(1, 0)); maxTilt = MathF.Max(maxTilt, Tilt()); if (over < 0 && Tilt() > 70) over = i; }
        }
        catch (Exception e) { error = " ERROR " + e.Message; }
        Console.WriteLine($"## steep {kind} {degrees}deg: braked 6s slide_down={F(standDown)}m tilt={F(standTilt)}; then drive 6s slide_down_total={F(Down())}m max_tilt={F(maxTilt)} rollover={(over < 0 ? "none" : "YES")} world_up_y={F(Vector3.Transform(Vector3.UnitY, t.Body.Rotation).Y)}{error}");
    }


    // Flat: pivot on the spot, reverse, and a brake stop from full speed.
    static void Basics(string kind)
    {
        using (var w = new World())
        {
            Flat(w); var t = w.Add(kind, new Vector3(0, .1f, 0), 0);
            for (int i = 0; i < 180; i++) w.Step(Stop);
            float yaw = 0, peak = 0; for (int i = 0; i < 360; i++) { w.Step(C(0, 1)); float r = t.Body.GetAngularVelocity().Y; yaw += r / 60; peak = MathF.Max(peak, MathF.Abs(r)); }
            var p = t.Body.Position;
            Console.WriteLine($"## pivot {kind}: turned_deg_in_6s={F(yaw * 57.2958f)} peak_yaw_rate={F(peak)} profile_yaw={F(t.Source.Config.GetProperty("handling").GetProperty("max_yaw_rate_rad_s").GetSingle())} drift_m={F(MathF.Sqrt(p.X * p.X + p.Z * p.Z))}");
        }
        using (var w = new World())
        {
            Flat(w); var t = w.Add(kind, new Vector3(0, .1f, 0), 0);
            for (int i = 0; i < 180; i++) w.Step(Stop);
            float tr = -1; float lim = t.Source.Config.GetProperty("max_reverse_mps").GetSingle();
            for (int i = 1; i <= 600; i++) { w.Step(C(-1, 0)); if (tr < 0 && -Fwd(t) >= lim * .95f) tr = i / 60f; }
            Console.WriteLine($"## reverse {kind}: v_after_10s={F(Fwd(t))} limit={F(lim)} t_to_95pct={F(tr)}");
        }
        using (var w = new World())
        {
            Flat(w); var t = w.Add(kind, new Vector3(0, .1f, -600), 0);
            for (int i = 0; i < 180; i++) w.Step(Stop);
            for (int i = 0; i < 60 * 25; i++) w.Step(C(1, 0));
            float v0 = Fwd(t), z0 = t.Body.Position.Z; int n = 0;
            while (MathF.Abs(Fwd(t)) > .1f && n < 1200) { w.Step(Stop); n++; }
            Console.WriteLine($"## brake {kind}: from_v={F(v0)} stop_time={F(n / 60f)} stop_distance={F(t.Body.Position.Z - z0)} mean_decel={F(v0 / MathF.Max(n / 60f, .01f))}");
        }
    }


    // A vehicle already lying on its side with forward speed: how far does it slide, and does throttle move it.
    static void SideSlide(string kind, float speed)
    {
        using var w = new World(); Flat(w); var t = w.Add(kind, new Vector3(0, 6, 0), 0);
        var half = t.Source.Binding.HalfExtents; var q = Quaternion.CreateFromAxisAngle(Vector3.UnitZ, MathF.PI / 2);
        w.System.BodyInterface.SetPositionAndRotation(t.Body.ID, new Vector3(0, half.X + .05f, 0), q, Activation.Activate);
        w.System.BodyInterface.SetLinearVelocity(t.Body.ID, new Vector3(0, 0, speed));
        int n = 0; while (n < 1800 && (n < 30 || t.Body.GetLinearVelocity().Length() > .1f)) { w.Step(C(1, 0)); n++; }
        float tilt = MathF.Acos(Math.Clamp(Vector3.Transform(Vector3.UnitY, t.Body.Rotation).Y, -1, 1)) * 57.2958f;
        Console.WriteLine($"## side-slide {kind} from {speed} m/s with throttle: distance={F(t.Body.Position.Z)} time={F(n / 60f)} final_tilt={F(tilt)}");
    }


    // Pivot on the spot with the hull against a wall: alongside (side gap) or nose-on. A vehicle must be able
    // to work itself free; reports the yaw reached and how far the hull moved off the wall.
    static void WallPivot(string kind, bool alongside, int steer)
    {
        using var w = new World(); Flat(w); var t = w.Add(kind, new Vector3(0, .1f, 0), 0);
        var half = t.Source.Binding.HalfExtents; var c = CheckedInput.Vector(t.Source.Config.GetProperty("body_center_offset"), -5, 5);
        if (alongside) w.Static(new Vector3(.5f, 3, 30), new Vector3(half.X + .55f, 3, 0), Quaternion.Identity);
        else w.Static(new Vector3(30, 3, .5f), new Vector3(0, 3, c.Z + half.Z + .55f), Quaternion.Identity);
        for (int i = 0; i < 180; i++) w.Step(Stop);
        float yaw = 0; for (int i = 0; i < 480; i++) { w.Step(C(0, steer)); yaw += t.Body.GetAngularVelocity().Y / 60; }
        var p = t.Body.Position;
        Console.WriteLine($"## wall-pivot {kind} wall={(alongside ? "alongside" : "ahead")} steer={steer}: turned_deg_in_8s={F(yaw * 57.2958f)} moved_x={F(p.X)} moved_z={F(p.Z - c.Z)}");
    }

    public static int Main(string[] args)
    {
        if (args.Length < 1 || !Directory.Exists(Path.Combine(args[0], "server/physics"))) { Console.Error.WriteLine("usage: Phys01Checks <repo-root> [mode] [baseline]"); return 2; }
        using (var doc = JsonDocument.Parse(File.ReadAllBytes(Path.Combine(args[0], "server/physics/Profiles/generated-definitions.json"))))
            foreach (var row in doc.RootElement.GetProperty("profiles").EnumerateArray()) Definitions[row.GetProperty("kind").GetString()!] = row.Clone();
        const string Bat = "france-Bat_Chatillon25t";
        if (!Foundation.Init(false)) throw new InvalidOperationException("Jolt init");
        try
        {
            string mode = args.Length > 1 ? args[1] : "all";
            Reference = !(args.Length > 2 && args[2] == "baseline");
            Console.WriteLine($"# traction={(Reference ? "reference (PHYS-01 stage A)" : "baseline (Jolt gearbox)")}");
            if (mode is "all" or "accel") { Accel("is7"); Accel(Bat); }
            if (mode is "all" or "stall") { Stall("is7"); Stall(Bat); }
            if (mode is "all" or "push")
            {
                Push("is7", Bat, .3f, 0, true, "standing start, target rear, braked (idle/dead)");
                Push("is7", Bat, .3f, MathF.PI / 2, true, "standing start, target side-on, braked (idle/dead)");
                Push("is7", Bat, .3f, 0, false, "standing start, target rear, tracks free (not reachable in production)");
                Push("is7", Bat, 40, 0, true, "running start 40 m, target rear, braked");
                Push("is7", Bat, 40, MathF.PI / 2, true, "running start 40 m, target side-on, braked");
                Push("is7", "is7", .3f, 0, true, "equal mass standing start, braked");
                Push(Bat, "is7", .3f, 0, true, "light pushes heavy, standing start, braked");
                Push(Bat, Bat, .3f, 0, true, "equal light, standing start, braked");
            }
            if (mode is "all" or "slope")
                foreach (string kind in new[] { "is7", Bat })
                    foreach (float deg in new[] { 10f, 15f, 20f, 25f, 30f, 35f })
                    {
                        Slope(kind, deg, 1, 0, 12, "traverse");
                        Slope(kind, deg, 1, 1, 12, "traverse+steerR");
                        Slope(kind, deg, 1, -1, 12, "traverse+steerL");
                        Slope(kind, deg, 0, 1, 8, "pivotR");
                    }
            if (mode is "all" or "turn") { foreach (string kind in new[] { "is7", Bat }) { Turn(kind, 1); Turn(kind, -1); } }
            if (mode is "all" or "bump") foreach (string kind in new[] { "is7", Bat }) foreach (float h in new[] { .15f, .25f, .35f, .5f }) Bump(kind, h);
            if (mode is "all" or "side") foreach (string kind in new[] { "is7", Bat }) SideSlide(kind, 12);
            if (mode is "all" or "wall") foreach (string kind in new[] { "is7", Bat }) foreach (bool along in new[] { true, false }) foreach (int st in new[] { 1, -1 }) WallPivot(kind, along, st);
            if (mode is "all" or "basics") foreach (string kind in new[] { "is7", Bat }) Basics(kind);
            if (mode is "all" or "steep") foreach (string kind in new[] { "is7", Bat }) foreach (float d in new[] { 40f, 45f, 50f, 55f }) Steep(kind, d);
            if (mode is "all" or "ramp") foreach (string kind in new[] { "is7", Bat }) foreach (float d in new[] { 20f, 30f }) foreach (float h in new[] { .8f, 1.2f, 2.7f }) foreach (float r in new[] { 12f, 150f }) Ramp(kind, d, r, h);
            if (mode is "all" or "rock") foreach (string kind in new[] { "is7", Bat }) foreach (float d in new[] { 15f, 25f, 30f }) foreach (float h in new[] { .3f, .5f, .7f }) { SlopeRock(kind, d, h, true, 60); SlopeRock(kind, d, h, false, 60); }
        }
        finally { Foundation.Shutdown(); }
        return 0;
    }
}
