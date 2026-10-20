using System.Numerics;

namespace MapDrive;

// Native body convention: Ry(yaw) * Rx(pitch) * Rz(roll).
// Euler angles need not be continuous through a pole; their reconstructed
// basis must describe the same body, including a side/roof rollover.
internal static class BodyOrientation
{
    public static Vector3 ToYawPitchRoll(Quaternion rotation)
    {
        var forward = Vector3.Transform(Vector3.UnitZ, rotation);
        var right = Vector3.Transform(Vector3.UnitX, rotation);
        float horizontal = MathF.Sqrt(forward.X * forward.X + forward.Z * forward.Z);
        if (horizontal > 1e-6f)
        {
            float yaw = MathF.Atan2(forward.X, forward.Z), pitch = MathF.Atan2(-forward.Y, horizontal);
            float sy = MathF.Sin(yaw), cy = MathF.Cos(yaw), sp = MathF.Sin(pitch), cp = MathF.Cos(pitch);
            // Undo the chosen yaw/pitch from the complete right axis. Near a
            // pitch pole two independent tiny-component atan2 calculations
            // amplify float error and can reconstruct the wrong body basis.
            float localX = cy * right.X - sy * right.Z;
            float localY = cp * right.Y + sp * (sy * right.X + cy * right.Z);
            return new(yaw, pitch, MathF.Atan2(localY, localX));
        }
        // At +/-90 pitch yaw and roll are not separately observable. Choose
        // roll=0 and retain the combined heading from the body's right axis.
        return new(MathF.Atan2(-right.Z, right.X), MathF.CopySign(MathF.PI / 2, -forward.Y), 0);
    }
}
