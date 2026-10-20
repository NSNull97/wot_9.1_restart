using System.Numerics;
using JoltPhysicsSharp;

namespace MapDrive;

// One construction path for actual battle bodies and authoring qualification.
// This preserves the existing MS-1/IS-7 BoxShape/CalculateInertia behavior.
internal static class TrackedBodySettings
{
    public const int StockCollisionSteps=4;
    public static BodyCreationSettings Create(BoxShape shape,float mass,Vector3 position,Quaternion rotation)
    {
        var settings=new BodyCreationSettings(shape,position,rotation,MotionType.Dynamic,1)
        {
            OverrideMassProperties=OverrideMassProperties.CalculateInertia,
            MassPropertiesOverride=new MassProperties { Mass=mass },
            AllowSleeping=false,MaxLinearVelocity=25,Friction=1
        };
        return settings;
    }
}
