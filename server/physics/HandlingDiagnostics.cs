using System.Numerics;
using System.Text.Json;
using JoltPhysicsSharp;

namespace MapDrive;

// Optional private evidence, never a client command or a change to the IPC state.
// Read after a completed physics step; no setter is used on the measured objects.
internal sealed class HandlingDiagnostics : IDisposable
{
    public const int MaxRecords = 12000;
    private const int MaxRecordBytes = 16384;
    private readonly FileStream stream;
    private readonly string configHash;
    private int records;
    private long lastSequence = -1, lastTick = -1;

    public HandlingDiagnostics(string root, string path, string configSha256)
    {
        CheckedInput.Sha256(configSha256);
        var full = Path.GetFullPath(path, root);
        var parent = Path.GetDirectoryName(full) ?? throw new InvalidDataException("diagnostic parent missing");
        // Owned requires an existing path. Check all parent components before
        // creating the fresh final child; CreateNew refuses any existing file.
        CheckedInput.Owned(root, parent);
        if (!Directory.Exists(parent) || string.IsNullOrEmpty(Path.GetFileName(full)))
            throw new InvalidDataException("diagnostic output requires an existing owned directory");
        stream = new FileStream(full, FileMode.CreateNew, FileAccess.Write, FileShare.Read);
        configHash = configSha256;
    }

    public void Write(long sequence, long tick, Quaternion rotation, Vector3 linearVelocity,
        Vector3 angularVelocity, TrackedVehicleController controller, VehicleConstraint constraint)
    {
        if (records >= MaxRecords) throw new InvalidDataException("handling diagnostic record bound exceeded");
        if (sequence < 0 || tick < 0 || sequence <= lastSequence || tick <= lastTick)
            throw new InvalidDataException("handling diagnostic sequence/tick not increasing");
        float[] V(Vector3 value) => [F(value.X), F(value.Y), F(value.Z)];
        float[] Q(Quaternion value) => [F(value.X), F(value.Y), F(value.Z), F(value.W)];
        var inverse = Quaternion.Conjugate(rotation);
        var localVelocity = Vector3.Transform(linearVelocity, inverse);
        var localAngularVelocity = Vector3.Transform(angularVelocity, inverse);
        var engine = controller.Engine;
        var transmission = controller.Transmission;
        object Track(VehicleTrack track) => new {
            angular_velocity_rad_s = F(track.AngularVelocity), driven_wheel = track.DrivenWheel,
            inertia_kg_m2 = F(track.Inertia), angular_damping = F(track.AngularDamping),
            differential_ratio = F(track.DifferentialRatio), max_brake_torque_nm = F(track.MaxBrakeTorque)
        };
        var wheels = Enumerable.Range(0, 6).Select(index => {
            var wheel = constraint.GetWheel(index);
            bool contact = wheel.HasContact;
            return new {
                index, contact, hard_point = wheel.HasHitHardPoint,
                angular_velocity_rad_s = F(wheel.AngularVelocity), suspension_length_m = F(wheel.SuspensionLength),
                suspension_impulse_ns = F(wheel.SuspensionLambda),
                longitudinal_impulse_ns = F(wheel.LongitudinalLambda), lateral_impulse_ns = F(wheel.LateralLambda),
                contact_normal = contact ? V(wheel.ContactNormal) : null,
                contact_longitudinal = contact ? V(wheel.ContactLongitudinal) : null,
                contact_lateral = contact ? V(wheel.ContactLateral) : null,
                ground_point_velocity_mps = contact ? V(wheel.ContactPointVelocity) : null
            };
        }).ToArray();
        var row = new {
            version = 1, @event = "handling_diagnostic", config_sha256 = configHash, seq = sequence, tick,
            sample_period_ticks = 6, step_seconds = 1f / 60,
            rotation_xyzw = Q(rotation), linear_velocity_mps = V(linearVelocity), angular_velocity_rad_s = V(angularVelocity),
            body_velocity_mps = V(localVelocity), body_angular_velocity_rad_s = V(localAngularVelocity),
            input = new { motor = F(controller.ForwardInput), left_ratio = F(controller.LeftRatio),
                right_ratio = F(controller.RightRatio), brake = F(controller.BrakeInput) },
            engine = new { rpm = F(engine.CurrentRPM), angular_velocity_rad_s = F(engine.AngularVelocity),
                offered_torque_nm = F(engine.GetTorque(MathF.Abs(controller.ForwardInput))) },
            transmission = new { gear = transmission.CurrentGear, clutch_friction = F(transmission.ClutchFriction),
                ratio = F(transmission.CurrentRatio), switching = transmission.IsSwitchingGear },
            tracks = new { left = Track(controller.LeftTrack), right = Track(controller.RightTrack) },
            wheels,
            impulse_scope = "last completed 1/60-second step only; not accumulated over the 10Hz sample interval",
            delivered_track_torque = "UNKNOWN; engine offered torque is not delivered ground torque"
        };
        var bytes = JsonSerializer.SerializeToUtf8Bytes(row);
        if (bytes.Length + 1 > MaxRecordBytes) throw new InvalidDataException("handling diagnostic record byte bound exceeded");
        stream.Write(bytes); stream.WriteByte((byte)'\n'); stream.Flush();
        records++; lastSequence = sequence; lastTick = tick;
    }

    private static float F(float value) => float.IsFinite(value) ? value
        : throw new InvalidDataException("non-finite handling diagnostic value");

    public void Dispose() => stream.Dispose();
}
