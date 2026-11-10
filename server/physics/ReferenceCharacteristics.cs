using System.Reflection;
using System.Text.Json;

namespace MapDrive;

// PHYS-01: 0.9.1 movement characteristics per vehicle kind (tools/phys01_characteristics.py, a projection of
// the battle profile tables): chassis terrainResistance for hard/medium/soft ground and rotationIsAroundCenter.
// How the native WGVehiclePhysics applies them is UNKNOWN; each use below states its reading.
internal static class ReferenceCharacteristics
{
    public const float ForwardFriction = .07f; // FORWARD_FRICTION
    // The imported maps carry no ground kind yet, so every map counts as hard ground: on it the hull traverse
    // equals the chassis rotationSpeed shown by the client. 0 hard, 1 medium, 2 soft.
    public const int GroundKind = 0;
    // Owner decision 2026-11-10: every vehicle pivots around its centre for now; whether vehicles with
    // rotationIsAroundCenter=false must turn around a held track is decided after a check in the modern game.
    public const bool HonourRotationIsAroundCenter = false;
    public sealed record Row(float[] TerrainResistance, bool RotationIsAroundCenter)
    {
        // rotationSpeedLimit = power / (rotationEnergy * terrainResistance): the traverse falls with the ground.
        public float YawScale => TerrainResistance[0] / TerrainResistance[GroundKind];
        public float Resistance => ForwardFriction * TerrainResistance[GroundKind];
    }
    static readonly Lazy<Dictionary<string, Row>> Rows = new(Read);
    static Dictionary<string, Row> Read()
    {
        using var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("MapDrive.ReferenceCharacteristics")
            ?? throw new InvalidDataException("reference characteristics absent");
        using var bytes = new MemoryStream(); stream.CopyTo(bytes);
        if (bytes.Length is < 1 or > 1024 * 1024) throw new InvalidDataException("reference characteristics size");
        using var doc = CheckedInput.Json(bytes.ToArray()); var r = doc.RootElement;
        CheckedInput.Fields(r, "version", "policy", "source", "vehicles");
        if (r.GetProperty("version").GetInt32() != 1 || r.GetProperty("policy").GetString() != "phys01-reference-characteristics-v1")
            throw new InvalidDataException("reference characteristics policy");
        var result = new Dictionary<string, Row>(StringComparer.Ordinal);
        foreach (var v in r.GetProperty("vehicles").EnumerateArray())
        {
            CheckedInput.Fields(v, "kind", "vehicle", "terrain_resistance", "rotation_is_around_center");
            var t = v.GetProperty("terrain_resistance");
            if (t.ValueKind != JsonValueKind.Array || t.GetArrayLength() != 3) throw new InvalidDataException("terrain resistance length");
            var resistance = t.EnumerateArray().Select(x => CheckedInput.Number(x, .3f, 10)).ToArray();
            result.Add(v.GetProperty("kind").GetString()!, new(resistance, v.GetProperty("rotation_is_around_center").GetBoolean()));
        }
        if (result.Count is < 1 or > 2048) throw new InvalidDataException("reference characteristics count");
        return result;
    }
    public static Row For(string kind) => Rows.Value.TryGetValue(kind, out var row) ? row
        : throw new InvalidDataException("reference characteristics missing for " + kind);
}
