using JoltPhysicsSharp;

namespace MapDrive;

// PHYS-01 stage A. Traction follows the 0.9.1 parameter set of res/scripts/common/physics_shared.pyc
// instead of the default Jolt gearbox: drive force = power / max(speed, linMinPowerDivider), bounded by
// the track grip (COHESION), and a hull that touches another hull holds with CONTACT_COHESION.
// The numbers come from the client; how the native WGVehiclePhysics combines them is UNKNOWN, so this
// mapping onto one Jolt gear and a torque curve is a project interpretation, not a port.
internal static class ReferenceTraction
{
    public const float Cohesion = 1.3f, ContactCohesion = .9f;
    // Steel on steel/ground; Jolt combines two bodies as sqrt(a*b). Project value, not a client number.
    public const float HullFriction = .1f;
    public const float MinPowerSpeed = 1f;    // linMinPowerDivider, m/s
    public const float SourcePowerRpm = 2500; // the profile generator: torque = power / (2*pi*2500/60)
    // Share of the transmission torque that reaches one track; calibrated by tools/phys01_checks (accel).
    public const float TrackShare = 1f;
    const float MaxRpm = 6000, TopSpeedMargin = 1.25f;
    const int CurvePoints = 32;

    public static float PowerWatts(float profileTorque) => profileTorque * (2 * MathF.PI * SourcePowerRpm / 60);

    // One forward and one reverse gear: engine speed is proportional to track speed, so the normalised
    // torque curve min(1, knee/x) is the constant-power law above MinPowerSpeed. Returns the track
    // differential ratio. TrackShare is the measured share of the transmission torque per track.
    public static float Configure(ref VehicleEngineSettings engine, VehicleTransmissionSettings transmission,
        float profileTorque, float radius, float speedLimit, float trackShare)
    {
        if (!float.IsFinite(profileTorque) || profileTorque <= 0 || !float.IsFinite(radius) || radius <= 0 ||
            !float.IsFinite(speedLimit) || speedLimit < 1 || !float.IsFinite(trackShare) || trackShare <= 0)
            throw new InvalidDataException("reference traction torque/radius/speed bounds");
        float top = speedLimit * TopSpeedMargin, knee = MinPowerSpeed / top;
        float differential = MaxRpm * (2 * MathF.PI / 60) * radius / top;
        engine.MaxTorque = PowerWatts(profileTorque) / MinPowerSpeed * radius / (2 * trackShare * differential);
        engine.MaxRPM = MaxRpm; engine.MinRPM = MaxRpm * knee * .5f;
        var curve = engine.NormalizedTorque ?? throw new InvalidOperationException("engine torque curve absent");
        curve.Clear(); curve.Reserve(CurvePoints + 2);
        curve.AddPoint(0, 1); curve.AddPoint(knee, 1);
        for (int i = 1; i <= CurvePoints; i++)
        {
            float x = knee * MathF.Pow(1 / knee, i / (float)CurvePoints);
            curve.AddPoint(x, knee / x);
        }
        transmission.Mode = TransmissionMode.Auto;
        transmission.GearRatios = new float[] { 1 }; transmission.ReverseGearRatios = new float[] { -1 };
        return differential;
    }
}
