using System.Numerics;
using System.Text.Json;
using MapDrive;

// Actual production helper, independent quaternion basis oracle. No Jolt,
// game process, native client, protocol serializer or historical physics claim.
internal static class Program
{
    const double BasisTolerance = 4e-6;
    static readonly Dictionary<string, int> Groups = new();
    static readonly List<object> Failures = new();
    static int cases, assertions, failed;
    static double maximumBasisError;
    static object? worstCase;

    static float Radians(double degrees) => (float)(degrees * Math.PI / 180);

    // Reconstruct the independently documented native rigid convention:
    // R = Ry(yaw) * Rx(pitch) * Rz(roll), +Y up and +Z forward.
    // This does not call Quaternion.CreateFromYawPitchRoll or the helper.
    static Vector3[] FromYpr(Vector3 ypr)
    {
        double sy = Math.Sin(ypr.X), cy = Math.Cos(ypr.X);
        double sp = Math.Sin(ypr.Y), cp = Math.Cos(ypr.Y);
        double sr = Math.Sin(ypr.Z), cr = Math.Cos(ypr.Z);
        return [
            new((float)(cy * cr + sy * sp * sr), (float)(cp * sr), (float)(-sy * cr + cy * sp * sr)),
            new((float)(-cy * sr + sy * sp * cr), (float)(cp * cr), (float)(sy * sr + cy * sp * cr)),
            new((float)(sy * cp), (float)-sp, (float)(cy * cp))
        ];
    }

    static float[] V(Vector3 value) => [value.X, value.Y, value.Z];
    static float[] Q(Quaternion value) => [value.X, value.Y, value.Z, value.W];

    static void Check(string group, string label, Quaternion rotation)
    {
        cases++;
        Groups[group] = Groups.GetValueOrDefault(group) + 1;
        var expected = new[] {
            Vector3.Transform(Vector3.UnitX, rotation),
            Vector3.Transform(Vector3.UnitY, rotation),
            Vector3.Transform(Vector3.UnitZ, rotation)
        };
        Vector3 ypr = BodyOrientation.ToYawPitchRoll(rotation);
        var reconstructed = FromYpr(ypr);
        bool finite = float.IsFinite(ypr.X) && float.IsFinite(ypr.Y) && float.IsFinite(ypr.Z);
        bool canonical = finite && Math.Abs((double)ypr.X) <= MathF.PI &&
            Math.Abs((double)ypr.Y) <= MathF.PI / 2 && Math.Abs((double)ypr.Z) <= MathF.PI;
        double error = 0;
        for (int axis = 0; axis < 3; axis++)
        {
            var actual = V(reconstructed[axis]);
            var oracle = V(expected[axis]);
            for (int component = 0; component < 3; component++)
                error = Math.Max(error, Math.Abs((double)actual[component] - oracle[component]));
        }
        assertions += 2;
        if (error > maximumBasisError)
        {
            maximumBasisError = error;
            worstCase = new { group, label, quaternion_xyzw = Q(rotation), ypr = V(ypr), basis_max_error = error };
        }
        if (!canonical || !double.IsFinite(error) || error > BasisTolerance)
        {
            failed++;
            if (Failures.Count < 12)
                Failures.Add(new { group, label, quaternion_xyzw = Q(rotation), ypr = V(ypr),
                    canonical, basis_max_error = double.IsFinite(error) ? (double?)error : null,
                    expected_basis = expected.Select(V), actual_basis = reconstructed.Select(V) });
        }
    }

    static void Pair(string group, string label, Quaternion rotation)
    {
        rotation = Quaternion.Normalize(rotation);
        Check(group, label + "/q", rotation);
        Check(group, label + "/-q", new(-rotation.X, -rotation.Y, -rotation.Z, -rotation.W));
    }

    static Quaternion Rotation(double yaw, double pitch, double roll) =>
        Quaternion.CreateFromYawPitchRoll(Radians(yaw), Radians(pitch), Radians(roll));

    static int Main()
    {
        double[] yaw = [-180, -137, -70, -1, 0, 37, 119, 180];
        double[] pitch = [-180, -135, -100, -90.01, -90.001, -90.0001, -90.00001,
            -90, -89.99999, -89.9999, -89.999, -89.99, -70, -1, 0, 1, 70,
            89.99, 89.999, 89.9999, 89.99999, 90, 90.00001, 90.0001, 90.001,
            90.01, 100, 135, 180];
        double[] roll = [-180, -179.999, -120, -90, -37, 0, 37, 90, 120, 179.999, 180];
        foreach (double y in yaw) foreach (double p in pitch) foreach (double r in roll)
            Pair("full_orientation_grid", $"yaw={y},pitch={p},roll={r}", Rotation(y, p, r));
        foreach (double y in new double[] { -137, 0, 37 })
            foreach (double r in new double[] { -120, 0, 37 })
                for (int quarter = -400; quarter <= 400; quarter++)
                    Pair("pitch_pole_sweep", $"yaw={y},pitch={quarter / 4.0},roll={r}", Rotation(y, quarter / 4.0, r));
        foreach (double y in new double[] { -137, 0, 37 })
            foreach (double p in new double[] { -89.999, 0, 89.999 })
                for (int half = -720; half <= 720; half++)
                    Pair("full_roll_sweep", $"yaw={y},pitch={p},roll={half / 2.0}", Rotation(y, p, half / 2.0));
        foreach (var axis in new[] { Vector3.Normalize(new Vector3(1, 2, 3)),
                     Vector3.Normalize(new Vector3(-2, 1, -3)), Vector3.UnitX, Vector3.UnitY, Vector3.UnitZ })
            for (int degree = -360; degree <= 360; degree += 3)
                Pair("arbitrary_axis_rotations", $"axis={axis},degrees={degree}", Quaternion.CreateFromAxisAngle(axis, Radians(degree)));

        Console.WriteLine(JsonSerializer.Serialize(new {
            schema = "p05c-orientation-selftest.v1", status = failed == 0 ? "PASS" : "FAIL",
            cases, assertions, failed, groups = Groups, basis_component_absolute_tolerance = BasisTolerance,
            maximum_basis_component_error = maximumBasisError, worst_case = worstCase, failures = Failures,
            oracle = "System.Numerics.Vector3.Transform(unit axis, actual quaternion); independent RyRxRz reconstruction",
            production_helper = "MapDrive.BodyOrientation.ToYawPitchRoll",
            native_wire_tested = false, Jolt_physics_tested = false, historical_physics_claim = false
        }));
        return failed == 0 ? 0 : 1;
    }
}
