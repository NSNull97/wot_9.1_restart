using System.Numerics;
using System.Text.Json;

namespace MapDrive;

// Separate IPC7 entrypoint. All identities are server-owned private-pipe data.
internal static class BattleSceneInput
{
    public const int MaxActors = 30, MaxInputBytes = 32768, MaxOutputBytes = 512 * 1024;
    public const string Policy = "p05c-shared-scene-v1";
    public static readonly string EmptyCatalogHash = new('0', 64);
    public static readonly string EmptySceneHash = CheckedInput.Hash("wot091-empty-battle-scene-v1\0"u8.ToArray());
    public sealed record Control(int Throttle, int Steer, bool Brake, int SpeedPercent)
    {
        public static readonly Control Stop = new(0, 0, true, 100);
    }
    public sealed record Actor(int Slot, string Kind, string ConfigHash, JsonElement Config,
        AngularBodyBinding Binding, Vector3 Spawn, float Yaw);
    public sealed record Manifest(string Hash, string Map, Actor[] Actors, CheckedInput.CatalogSpec? Catalog);

    public static Manifest Load(string root, string path, string hash)
    {
        using var doc = CheckedInput.Json(CheckedInput.FileBytes(CheckedInput.Owned(root, path), 32768, hash));
        var m = doc.RootElement;
        CheckedInput.Fields(m, "version", "profile", "policy", "map", "catalog", "actors");
        string map = m.GetProperty("map").GetString()!;
        int version=m.GetProperty("version").GetInt32();
        if (version is not (1 or 2 or 3) || m.GetProperty("profile").GetString() != "test_lab" ||
            m.GetProperty("policy").GetString() != Policy || !CheckedInput.IsRegisteredMap(map))
            throw new InvalidDataException("battle scene policy/map");
        var rows = m.GetProperty("actors");
        if (rows.ValueKind != JsonValueKind.Array || rows.GetArrayLength() is < 1 or > MaxActors)
            throw new InvalidDataException("battle scene actor count");
        var actors = new List<Actor>();
        foreach (var row in rows.EnumerateArray())
        {
            if(version==1)CheckedInput.Fields(row, "slot", "kind", "config", "spawn_origin", "spawn_yaw");
            else CheckedInput.Fields(row,"slot","kind","config","source_profile","spawn_origin","spawn_yaw");
            if (row.GetProperty("slot").GetInt32() != actors.Count) throw new InvalidDataException("ordered contiguous actor slots");
            var reference = row.GetProperty("config"); CheckedInput.Fields(reference, "path", "sha256");
            string configHash = reference.GetProperty("sha256").GetString()!;
            using var config = CheckedInput.Json(CheckedInput.FileBytes(CheckedInput.Owned(root,
                reference.GetProperty("path").GetString()!), 16384, configHash));
            var c = config.RootElement;
            CheckedInput.Fields(c, "version", "profile", "map", "terrain", "obstacles", "spawn_origin", "spawn_yaw",
                "body_half_extents", "body_center_offset", "wheel_points", "mass_kg", "max_forward_mps", "max_reverse_mps",
                "engine_max_torque_nm", "wheel_radius", "suspension_min", "suspension_max", "track_max_brake_torque", "bounds_xz",
                "longitudinal_friction", "lateral_friction", "stationary_steering_ratio", "handling");
            string kind = row.GetProperty("kind").GetString()!;
            AngularBodyBinding binding;
            if(version>=2&&row.GetProperty("source_profile").ValueKind!=JsonValueKind.Null)
            {
                if(GeneratedVehicleProfiles.IsGenerated(kind))
                {
                    // Owned mixed scenes use manifest2 (generated kinds) or the extended lab manifest3.
                    ExtendedProfileQualification.Runtime();
                    binding=GeneratedVehicleProfiles.Select(root,row.GetProperty("source_profile"),c,kind);
                }
                else if(kind is "wt-e100-128" or "fv215b-183")
                {
                    if(version!=3)throw new InvalidDataException("extended kind requires manifest3");
                    ExtendedProfileQualification.Runtime();
                    binding=ExtendedVehicleProfiles.Select(root,row.GetProperty("source_profile"),c,kind);
                }
                else
                {
                    StockProfileQualification.Runtime();
                    binding=StockVehicleProfiles.Select(root,row.GetProperty("source_profile"),c,kind);
                }
            }
            else binding=AngularBodyBinding.Select(c); // Existing v1 projections are unchanged.
            if (c.GetProperty("map").GetString() != map || kind != binding.Kind)
                throw new InvalidDataException("battle actor kind/config map");
            foreach (string key in new[] { "terrain", "obstacles" })
            {
                CheckedInput.Fields(c.GetProperty(key), "path", "sha256");
                CheckedInput.Owned(root, c.GetProperty(key).GetProperty("path").GetString()!);
            }
            var b = c.GetProperty("bounds_xz");
            if (b.ValueKind != JsonValueKind.Array || b.GetArrayLength() != 4) throw new InvalidDataException("battle map bounds");
            float minX = CheckedInput.Number(b[0], -1000, 0), minZ = CheckedInput.Number(b[1], -1000, 0),
                maxX = CheckedInput.Number(b[2], 0, 1000), maxZ = CheckedInput.Number(b[3], 0, 1000);
            var spawn = CheckedInput.Vector(row.GetProperty("spawn_origin"), -1000, 1000);
            float yaw = CheckedInput.Number(row.GetProperty("spawn_yaw"), -MathF.PI, MathF.PI);
            if (maxX - minX < 100 || maxZ - minZ < 100 || spawn.X < minX + 5 || spawn.X > maxX - 5 ||
                spawn.Z < minZ + 5 || spawn.Z > maxZ - 5) throw new InvalidDataException("battle spawn outside map");
            if (actors.Count > 0)
            {
                foreach (string key in new[] { "terrain", "obstacles", "bounds_xz" })
                    if (c.GetProperty(key).GetRawText() != actors[0].Config.GetProperty(key).GetRawText())
                        throw new InvalidDataException("actors must share exact map geometry/bounds references");
            }
            // Reject initially overlapping horizontal hulls before creating any Jolt body.
            foreach (var previous in actors)
                if (HorizontalOverlap(spawn, yaw, binding.HalfExtents, previous.Spawn, previous.Yaw, previous.Binding.HalfExtents))
                    throw new InvalidDataException("initial battle hulls overlap");
            actors.Add(new(actors.Count, kind, configHash, c.Clone(), binding, spawn, yaw));
        }
        CheckedInput.CatalogSpec? catalog = null;
        if (m.GetProperty("catalog").ValueKind != JsonValueKind.Null)
        {
            var reference = m.GetProperty("catalog"); CheckedInput.Fields(reference, "path", "sha256");
            catalog = CheckedInput.LoadCatalog(root, reference.GetProperty("path").GetString()!,
                reference.GetProperty("sha256").GetString()!, map, actors[0].Config.GetProperty("obstacles"));
            if (catalog.Version != 8) throw new InvalidDataException("IPC7 requires existing angular catalog8");
        }
        return new(hash, map, actors.ToArray(), catalog);
    }

    static bool HorizontalOverlap(Vector3 a, float ay, Vector3 ah, Vector3 b, float by, Vector3 bh)
    {
        Vector2 Axis(float yaw) => new(MathF.Cos(yaw), -MathF.Sin(yaw));
        var ax = Axis(ay); var az = new Vector2(-ax.Y, ax.X); var bx = Axis(by); var bz = new Vector2(-bx.Y, bx.X);
        var d = new Vector2(a.X - b.X, a.Z - b.Z);
        foreach (var axis in new[] { ax, az, bx, bz })
            if (MathF.Abs(Vector2.Dot(d, axis)) >= MathF.Abs(Vector2.Dot(ax, axis)) * ah.X + MathF.Abs(Vector2.Dot(az, axis)) * ah.Z +
                MathF.Abs(Vector2.Dot(bx, axis)) * bh.X + MathF.Abs(Vector2.Dot(bz, axis)) * bh.Z + .05f) return false;
        return true;
    }

    public static byte[]? ReadLine(Stream stream)
    {
        using var line = new MemoryStream();
        while (true)
        {
            int value = stream.ReadByte();
            if (value < 0) { if (line.Length > 0) throw new InvalidDataException("partial IPC7 EOF"); return null; }
            if (value == 10) return line.ToArray();
            if (line.Length >= MaxInputBytes || value < 32 || value > 126) throw new InvalidDataException("IPC7 ASCII/line bound");
            line.WriteByte((byte)value);
        }
    }
    public static void Header(JsonElement request, Manifest manifest, uint generation)
    {
        if (request.GetProperty("version").GetInt32() != 7 || request.GetProperty("generation").GetUInt32() != generation ||
            request.GetProperty("manifest_sha256").GetString() != manifest.Hash ||
            request.GetProperty("catalog_sha256").GetString() != (manifest.Catalog?.Hash ?? EmptyCatalogHash))
            throw new InvalidDataException("IPC7 scene identity");
    }
    public static CheckedInput.Scene Scene(JsonElement request, Manifest manifest, uint generation, long seq, string operation)
    {
        CheckedInput.Fields(request, "version", "op", "generation", "manifest_sha256", "catalog_sha256", "advance_seq",
            "scene_version", "removed_object_ids", "scene_sha256");
        Header(request, manifest, generation);
        if (request.GetProperty("op").GetString() != operation || request.GetProperty("advance_seq").GetInt64() != seq)
            throw new InvalidDataException("IPC7 scene operation/sequence");
        var rows = request.GetProperty("removed_object_ids");
        if (rows.ValueKind != JsonValueKind.Array || rows.GetArrayLength() > (manifest.Catalog?.MaxRemoved ?? 0))
            throw new InvalidDataException("IPC7 scene removals bound");
        var ids = rows.EnumerateArray().Select(v => v.GetUInt32()).ToArray();
        var scene = manifest.Catalog == null ? new CheckedInput.Scene([], EmptySceneHash) : CheckedInput.MakeScene(manifest.Catalog, ids);
        if (request.GetProperty("scene_version").GetUInt32() != scene.Version || request.GetProperty("scene_sha256").GetString() != scene.Hash)
            throw new InvalidDataException("IPC7 cumulative scene hash/version");
        return scene;
    }
    public static Control[] Advance(JsonElement request, Manifest manifest, uint generation, long sequence, CheckedInput.Scene scene)
    {
        CheckedInput.Fields(request, "version", "op", "generation", "manifest_sha256", "catalog_sha256", "seq", "ticks",
            "scene_version", "scene_sha256", "inputs");
        Header(request, manifest, generation);
        if (request.GetProperty("op").GetString() != "advance" || request.GetProperty("seq").GetInt64() != sequence + 1 ||
            sequence >= 36000 || request.GetProperty("ticks").GetInt32() != 6 || request.GetProperty("scene_version").GetUInt32() != scene.Version ||
            request.GetProperty("scene_sha256").GetString() != scene.Hash) throw new InvalidDataException("IPC7 advance cadence/scene");
        var rows = request.GetProperty("inputs");
        if (rows.ValueKind != JsonValueKind.Array || rows.GetArrayLength() != manifest.Actors.Length)
            throw new InvalidDataException("IPC7 complete actor inputs required");
        var controls = new List<Control>();
        foreach (var row in rows.EnumerateArray())
        {
            CheckedInput.Fields(row, "slot", "throttle", "steer", "brake", "speed_percent");
            int throttle = row.GetProperty("throttle").GetInt32(), steer = row.GetProperty("steer").GetInt32(), speed = row.GetProperty("speed_percent").GetInt32();
            bool brake = row.GetProperty("brake").GetBoolean();
            if (row.GetProperty("slot").GetInt32() != controls.Count || throttle is < -1 or > 1 || steer is < -1 or > 1 ||
                brake && (throttle != 0 || steer != 0) || !(speed == 100 || speed == 50 && !brake && throttle != 0 || speed == 25 && !brake && throttle == 1))
                throw new InvalidDataException("IPC7 bounded actor control");
            controls.Add(new(throttle, steer, brake, speed));
        }
        return controls.ToArray();
    }
}
