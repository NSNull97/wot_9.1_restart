using System.Numerics;
using JoltPhysicsSharp;

namespace MapDrive;

// PHYS-01 stage B. Body parameters of the 0.9.1 set (res/scripts/common/physics_shared.pyc):
// gravity G * GRAVITY_FACTOR, the centre of mass lowered by _computeCenterOfMassShift, side friction .6.
// The inertia tensor stays the profile's box tensor about the (moved) centre of mass: the client also
// sets inertia explicitly and independently of the shift, and the qualified native bits stay valid.
internal static class ReferenceBody
{
    // physics_shared NUM_SPRINGS = 5 pairs. Spread evenly between the front and rear carrying points of each side;
    // the client's own track length and +-.45 width are not in the profile, so these stations are a project reading.
    public static Vector3[] FivePairs(Vector3[] points)
    {
        var result = new Vector3[10];
        for (int side = 0; side < 2; side++)
            for (int i = 0; i < 5; i++)
                result[side * 5 + i] = Vector3.Lerp(points[side * 3], points[side * 3 + 2], i / 4f);
        return result;
    }
    public const float GravityFactor = 1.25f, SideFriction = .6f;
    const float DynRatioMin = 9.5f, DynRatioMid = 13, DynRatioMax = 21; // W/kg
    const float CmyMin = -.15f, CmyMid = -.2f, CmyMax = -.3f;           // fraction of the hull height

    // _powerCurve(enginePower / mass, DYN_RATIO_*, CMY_*)
    public static float CenterOfMassShift(float powerWatts, float massKg)
    {
        if (!float.IsFinite(powerWatts) || powerWatts <= 0 || !float.IsFinite(massKg) || massKg <= 0)
            throw new InvalidDataException("reference centre of mass power/mass bounds");
        float range = DynRatioMax - DynRatioMin;
        float arg = Math.Clamp((powerWatts / massKg - DynRatioMin) / range, 0, 1);
        float argMid = (DynRatioMid - DynRatioMin) / range, valueRange = CmyMax - CmyMin;
        float power = MathF.Log((CmyMid - CmyMin) / valueRange) / MathF.Log(argMid);
        return MathF.Pow(arg, power) * valueRange + CmyMin;
    }

    // The same box and tensor as TrackedBodySettings.Create, with the centre of mass moved by offsetY.
    public static BodyCreationSettings Create(BoxShape box, Vector3 half, float mass, float offsetY,
        Vector3 position, Quaternion rotation, out OffsetCenterOfMassShape shape)
    {
        var offset = new Vector3(0, offsetY, 0);
        shape = new OffsetCenterOfMassShape(in offset, box);
        var properties = new MassProperties();
        properties.SetMassAndInertiaOfSolidBox(2 * half, 1);
        properties.ScaleToMass(mass);
        return new BodyCreationSettings(shape, position, rotation, MotionType.Dynamic, 1)
        {
            OverrideMassProperties = OverrideMassProperties.MassAndInertiaProvided,
            MassPropertiesOverride = properties,
            AllowSleeping = false, MaxLinearVelocity = 25, Friction = 1, GravityFactor = GravityFactor
        };
    }
}
