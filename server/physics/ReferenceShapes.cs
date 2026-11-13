using System.Numerics;
using System.Reflection;
using System.Text.Json;

namespace MapDrive;

// TURPHYS-01: hull and turret boxes per generated vehicle kind (tools/turphys01_shapes.py, a projection of the
// geometry bundles the battle profile tables pin). The turret box only shapes collisions: mass and inertia stay
// the qualified box tensor. Vehicles outside the table keep the single hull box.
internal static class ReferenceShapes
{
    public sealed record Row(Vector3 TurretCenter, Vector3 TurretHalf);
    static readonly Lazy<Dictionary<string, Row?>> Rows = new(Read);
    static Vector3 V(JsonElement e) => CheckedInput.Vector(e, -20, 20);
    static (Vector3 Min, Vector3 Max) Bounds(JsonElement e)
    {
        CheckedInput.Fields(e, "min", "max");
        var lo = V(e.GetProperty("min")); var hi = V(e.GetProperty("max"));
        if (hi.X <= lo.X || hi.Y <= lo.Y || hi.Z <= lo.Z) throw new InvalidDataException("reference shape bounds");
        return (lo, hi);
    }
    static Dictionary<string, Row?> Read()
    {
        using var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("MapDrive.TurretShapes")
            ?? throw new InvalidDataException("turret shapes absent");
        using var bytes = new MemoryStream(); stream.CopyTo(bytes);
        if (bytes.Length is < 1 or > 8 * 1024 * 1024) throw new InvalidDataException("turret shapes size");
        using var doc = CheckedInput.Json(bytes.ToArray()); var r = doc.RootElement;
        CheckedInput.Fields(r, "version", "policy", "source", "vehicles");
        if (r.GetProperty("version").GetInt32() != 1 || r.GetProperty("policy").GetString() != "turphys01-hull-turret-boxes-v1")
            throw new InvalidDataException("turret shapes policy");
        var result = new Dictionary<string, Row?>(StringComparer.Ordinal);
        foreach (var v in r.GetProperty("vehicles").EnumerateArray())
        {
            CheckedInput.Fields(v, "kind", "bundle_sha256", "hull_position", "turret_position", "hull_bounds", "turret_bounds");
            var hullPosition = V(v.GetProperty("hull_position"));
            var hull = Bounds(v.GetProperty("hull_bounds"));
            var t = v.GetProperty("turret_bounds");
            Row? row = null;
            if (t.ValueKind != JsonValueKind.Null)
            {
                var turret = Bounds(t);
                // In the body frame: the body box is centred on the hull bounds, the turret hangs at its pivot.
                var bodyCenter = (hull.Min + hull.Max) / 2 + hullPosition;
                var center = hullPosition + V(v.GetProperty("turret_position")) + (turret.Min + turret.Max) / 2 - bodyCenter;
                row = new(center, (turret.Max - turret.Min) / 2);
            }
            result.Add(v.GetProperty("kind").GetString()!, row);
        }
        // CONTENT-0 3.3/4: stock kinds plus every generated build (tools/turphys01_shapes.py MAX_ROWS).
        if (result.Count is < 1 or > 16384) throw new InvalidDataException("turret shapes count");
        return result;
    }
    public static Row? For(string kind) => Rows.Value.TryGetValue(kind, out var row) ? row : null;
}
