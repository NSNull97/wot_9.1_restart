using System.Numerics;
using System.Text.Json;
using JoltPhysicsSharp;

namespace MapDrive;

// Optional private diagnostics after a completed six-substep batch. No setters,
// force edits, solver changes or extra physics update are performed here.
internal sealed class MixedContactDiagnostics : IDisposable
{
    const int MaxRecords = 12000, MaxRecordBytes = 65536;
    const long MaxTotalBytes = 32 * 1024 * 1024;
    readonly FileStream stream;
    int records;
    long lastSequence = -1, lastTick = -1, totalBytes;

    public MixedContactDiagnostics(string root, string path)
    {
        var full = Path.GetFullPath(path, root);
        var parent = Path.GetDirectoryName(full) ?? throw new InvalidDataException("mixed diagnostic parent missing");
        CheckedInput.Owned(root, parent);
        if (!Directory.Exists(parent) || string.IsNullOrEmpty(Path.GetFileName(full)))
            throw new InvalidDataException("mixed diagnostics require existing owned parent");
        stream = new FileStream(full, FileMode.CreateNew, FileAccess.Write, FileShare.Read);
    }

    public static object Capture(int slot, string kind, string configSha256, Body body,
        VehicleConstraint constraint, TrackedVehicleController controller, BattleSceneInput.Control input)
    {
        CheckedInput.Sha256(configSha256);
        if (slot is < 0 or > 5 || kind is not ("ms1" or "is7" or "t26" or "t34" or "t3485" or "wt-e100-128" or "fv215b-183")&&!GeneratedVehicleProfiles.IsGenerated(kind)
            || constraint.WheelsCount != 6)
            throw new InvalidDataException("mixed diagnostic actor identity");
        var rotation = body.Rotation;
        var linear = body.GetLinearVelocity();
        var angular = body.GetAngularVelocity();
        var inverse = Quaternion.Conjugate(rotation);
        var engine = controller.Engine;
        var transmission = controller.Transmission;
        object Track(VehicleTrack track) => new {
            angular_velocity_rad_s = F(track.AngularVelocity), inertia_kg_m2 = F(track.Inertia),
            differential_ratio = F(track.DifferentialRatio), max_brake_torque_nm = F(track.MaxBrakeTorque)
        };
        var wheels = Enumerable.Range(0, 6).Select(index => {
            var wheel = constraint.GetWheel(index);
            bool contact = wheel.HasContact;
            return new {
                index, contact, hard_point = wheel.HasHitHardPoint,
                contact_body_id = contact ? (uint?)wheel.ContactBodyID.ID : null,
                contact_position_m = contact ? V(wheel.ContactPosition) : null,
                contact_normal = contact ? V(wheel.ContactNormal) : null,
                contact_point_velocity_mps = contact ? V(wheel.ContactPointVelocity) : null,
                suspension_length_m = F(wheel.SuspensionLength), suspension_impulse_ns = F(wheel.SuspensionLambda),
                longitudinal_impulse_ns = F(wheel.LongitudinalLambda), lateral_impulse_ns = F(wheel.LateralLambda),
                angular_velocity_rad_s = F(wheel.AngularVelocity)
            };
        }).ToArray();
        return new {
            slot, kind, config_sha256 = configSha256, body_id = body.ID.ID,
            position_m = V(body.Position), rotation_xyzw = new[] { F(rotation.X), F(rotation.Y), F(rotation.Z), F(rotation.W) },
            linear_velocity_mps = V(linear), angular_velocity_rad_s = V(angular),
            body_velocity_mps = V(Vector3.Transform(linear, inverse)), body_angular_velocity_rad_s = V(Vector3.Transform(angular, inverse)),
            requested = new { throttle = input.Throttle, steer = input.Steer, brake = input.Brake, speed_percent = input.SpeedPercent },
            controller_input = new { motor = F(controller.ForwardInput), left_ratio = F(controller.LeftRatio),
                right_ratio = F(controller.RightRatio), brake = F(controller.BrakeInput) },
            engine = new { rpm = F(engine.CurrentRPM), offered_torque_nm = F(engine.GetTorque(MathF.Abs(controller.ForwardInput))) },
            transmission = new { gear = transmission.CurrentGear, clutch_friction = F(transmission.ClutchFriction),
                ratio = F(transmission.CurrentRatio), switching = transmission.IsSwitchingGear },
            tracks = new { left = Track(controller.LeftTrack), right = Track(controller.RightTrack) }, wheels
        };
    }

    public void Write(long sequence, long tick, object[] actors, object[] hullContacts, int omittedCallbacks)
    {
        if (records >= MaxRecords || sequence is < 0 or > 36000 || tick != 180 + sequence * 6
            || sequence <= lastSequence || tick <= lastTick || actors.Length is < 1 or > 6
            || hullContacts.Length > 64 || omittedCallbacks < 0)
            throw new InvalidDataException("mixed diagnostic sequence/count bound");
        var raw = JsonSerializer.SerializeToUtf8Bytes(new {
            version = 1, @event = "mixed_contact_diagnostic", seq = sequence, tick,
            sample_period_ticks = 6, step_seconds = 1f / 60, actors, hull_contacts = hullContacts,
            hull_contact_omitted_callbacks = omittedCallbacks,
            sample_scope = "last completed 1/60-second substep of this six-step batch; impulses are not accumulated",
            delivered_ground_torque = "UNKNOWN; engine offered torque is not delivered track/ground torque",
            manifold_scope = "first actual callback per actor/body pair per batch before fracture policy; separate from body box SAT estimate"
        });
        if (raw.Length + 1 > MaxRecordBytes || totalBytes + raw.Length + 1 > MaxTotalBytes)
            throw new InvalidDataException("mixed diagnostic byte bound");
        using (var doc = JsonDocument.Parse(raw))
        {
            var rows = doc.RootElement.GetProperty("actors").EnumerateArray().ToArray();
            for (int i = 0; i < rows.Length; i++)
                if (rows[i].GetProperty("slot").GetInt32() != i)
                    throw new InvalidDataException("mixed diagnostic ordered complete actors");
        }
        stream.Write(raw); stream.WriteByte(10); stream.Flush();
        records++; totalBytes += raw.Length + 1; lastSequence = sequence; lastTick = tick;
    }

    static float F(float value) => float.IsFinite(value) ? value : throw new InvalidDataException("nonfinite mixed diagnostic");
    static float[] V(Vector3 value) => new[] { F(value.X), F(value.Y), F(value.Z) };
    public void Dispose() => stream.Dispose();
}
