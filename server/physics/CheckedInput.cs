using System.Buffers.Binary;
using System.Numerics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using JoltPhysicsSharp;

namespace MapDrive;

// Own local IPC and imported assets only. No native protocol IDs or client poses.
internal static class CheckedInput
{
    // One source-pinned object only. These are domain/export identities, not
    // native area/item IDs and not a claim about historical damage rules.
    public sealed record RemovalSpec(string DescriptorHash, uint ObjectId, int InstanceId, int FirstTriangle,
        int TriangleCount, string Revision);
    public const string PhysicsManifestHash = "ea6ef22aed0fdd4e4826500c280a616737f8990ce7ab7cd808b9382227ec5ffd";
    public const string ProjectileManifestHash = "ccd28d8e3320d041e569e217a8c20e0285db0459bc2ef447c5bd95dd97d80cea";
    public const string ObjectRevision = "karelia-instance1513-v1";
    // IPC3/catalog-v2 remains the accepted legacy profile.  Contact-capable
    // worker catalogs are deliberately a separate version and carry larger,
    // still bounded limits so a malformed map cannot turn this process into an
    // unbounded object/body allocator.
    public const int MaxCatalogObjects = 64, MaxRemovedObjects = 40;
    public const int MaxContactCatalogObjects = 1024, MaxContactRemovedObjects = 1024;
    public const int MaxExtendedCatalogObjects = 2048, MaxExtendedRemovedObjects = 2048;
    public const int MaxLegacyCatalogBytes = 128 * 1024;
    public sealed record CatalogEntry(uint ObjectId, int InstanceId, int FirstTriangle, int TriangleCount,
        string Revision, string Kind, int RamEnergyJ, string? RamResponse = null);
    // MAPS-02: a catalog9 file keeps catalog8 semantics (Version == 8) for every
    // fracture/tree entry and adds non-blocking falling atom sensor entries in
    // Columns, whose spans index the separate pinned trigger mesh.
    public sealed record TriggerMesh(Vector3[] Vertices, uint[] Indices) { public int TriangleCount => Indices.Length / 3; }
    public const int MaxTriggerTriangles = 262_144, MaxTriggerTrianglesPerObject = 256;
    public const string FallingAtomResponse = "sensor_trigger";
    public sealed record CatalogSpec(string Hash, string Map, CatalogEntry[] Entries, bool Contacts, int Version,
        CatalogEntry[]? ColumnEntries = null, TriggerMesh? Triggers = null)
    {
        public CatalogEntry[] Columns => ColumnEntries ?? [];
        public bool Known(uint id) => Entries.Any(e => e.ObjectId == id) || Columns.Any(e => e.ObjectId == id);
        public int MaxObjects => Version >= 4 ? MaxExtendedCatalogObjects : Contacts ? MaxContactCatalogObjects : MaxCatalogObjects;
        public int MaxRemoved => Version >= 4 ? MaxExtendedRemovedObjects : Contacts ? MaxContactRemovedObjects : MaxRemovedObjects;
        public bool Fractures => Version is 5 or 6 or 7 or 8;
        public int IpcVersion => Version == 8 ? 6 : Fractures ? 5 : Contacts ? 4 : 3;
    }
    public sealed record Scene(uint[] Ids, string Hash) { public uint Version => (uint)Ids.Length; }
    private sealed record CatalogSource(string PhysicsHash, string ProjectileHash, int InstanceCount, int TriangleCount);
    // Only source-audited initial geometry is admitted. These are map identities,
    // not per-object allowlists; the catalog still supplies exact full spans.
    // Identities come from the compiled-in server/contracts/map_registry.json
    // (the gateway reads the same file); the accepted maps must keep their pins.
    private static readonly Lazy<Dictionary<string, CatalogSource>> Registry = new(LoadRegistry);
    private static Dictionary<string, CatalogSource> LoadRegistry()
    {
        using var stream = typeof(CheckedInput).Assembly.GetManifestResourceStream("MapDrive.MapRegistry")
            ?? throw new InvalidDataException("map registry resource missing");
        if (stream.Length > 1024 * 1024) throw new InvalidDataException("map registry size");
        using var doc = JsonDocument.Parse(stream, new JsonDocumentOptions { MaxDepth = 8 });
        var root = doc.RootElement;
        Fields(root, "version", "kind", "maps");
        if (root.GetProperty("version").GetInt32() != 1 || root.GetProperty("kind").GetString() != "wot091_server_map_registry")
            throw new InvalidDataException("map registry identity");
        var result = new Dictionary<string, CatalogSource>(StringComparer.Ordinal);
        foreach (var row in root.GetProperty("maps").EnumerateArray())
        {
            string asset = row.GetProperty("asset").GetString()!;
            if (asset.Length is < 4 or > 43 || !char.IsAsciiDigit(asset[0]) || !char.IsAsciiDigit(asset[1]) || asset[2] != '_' ||
                asset.Skip(3).Any(c => !(char.IsAsciiLetterLower(c) || char.IsAsciiDigit(c) || c == '_')))
                throw new InvalidDataException("map registry asset");
            var physics = row.GetProperty("physics");
            string physicsHash = physics.GetProperty("manifest_sha256").GetString()!;
            string projectileHash = row.GetProperty("projectile").GetProperty("manifest_sha256").GetString()!;
            Sha256(physicsHash); Sha256(projectileHash);
            int instances = physics.GetProperty("instance_count").GetInt32(), triangles = physics.GetProperty("triangle_count").GetInt32();
            if (instances < 1 || triangles < 1 || !result.TryAdd(asset, new(physicsHash, projectileHash, instances, triangles)))
                throw new InvalidDataException("map registry entry");
        }
        if (!result.TryGetValue("01_karelia", out var karelia) || karelia != new CatalogSource(PhysicsManifestHash, ProjectileManifestHash, 2918, 335551) ||
            !result.TryGetValue("05_prohorovka", out var prohorovka) || prohorovka != new CatalogSource(
                "9d358a48da303abaf15572f478dddc16971864960d9341943cc6d207b32b3265",
                "3db1ad3859ae2f5fed678ac5f148005cff38a3c915bb33dde3303de22e22bef7", 3904, 428597))
            throw new InvalidDataException("accepted map registry pins changed");
        return result;
    }
    public static bool IsRegisteredMap(string map) => Registry.Value.ContainsKey(map);
    private static CatalogSource CatalogProfile(string map) =>
        Registry.Value.TryGetValue(map, out var source) ? source : throw new InvalidDataException("catalog map outside checked profiles");

    public static void Sha256(string? value)
    {
        if (value == null || value.Length != 64 || value.Any(c => !"0123456789abcdef".Contains(c)))
            throw new InvalidDataException("lowercase SHA256 required");
    }

    public static CatalogSpec LoadCatalog(string root, string path, string hash, string map, JsonElement obstacles)
    {
        // A contact catalog is an explicit worker-side projection of the
        // bounded domain manifest. Explicit catalog-v4 admits 2048 whole
        // objects, while v3 retains 1024; both keep the one MiB file cap.
        string catalogPath = Owned(root, path);
        var catalogBytes = FileBytes(catalogPath, 1024 * 1024, hash);
        using var doc = Json(catalogBytes);
        var d = doc.RootElement;
        var source = CatalogProfile(map);
        int version = d.GetProperty("version").GetInt32();
        bool falling = version == 9;
        TriggerMesh? triggers = null;
        if (falling)
        {
            Fields(d, "version", "profile", "map", "physics_manifest_sha256", "projectile_manifest_sha256", "contacts", "objects", "ram_policy", "falling_atom_triggers");
            triggers = LoadTriggers(Path.GetDirectoryName(catalogPath)!, d.GetProperty("falling_atom_triggers"));
            version = 8;
        }
        bool contacts = version is 3 or 4 or 5 or 6 or 7 or 8;
        if (version == 2 && catalogBytes.Length > MaxLegacyCatalogBytes)
            throw new InvalidDataException("legacy catalog exceeds 128 KiB");
        if (falling) { }
        else if (version is 5 or 6 or 7 or 8)
            Fields(d, "version", "profile", "map", "physics_manifest_sha256", "projectile_manifest_sha256", "contacts", "objects", "ram_policy");
        else if (contacts)
            Fields(d, "version", "profile", "map", "physics_manifest_sha256", "projectile_manifest_sha256", "contacts", "objects");
        else
            Fields(d, "version", "profile", "map", "physics_manifest_sha256", "projectile_manifest_sha256", "objects");
        if ((version != 2 && version != 3 && version != 4 && version != 5 && version != 6 && version != 7 && version != 8) || (contacts && d.GetProperty("contacts").ValueKind != JsonValueKind.True) ||
            (version == 5 && d.GetProperty("ram_policy").GetString() != FractureResponse.Policy) ||
            (version == 6 && d.GetProperty("ram_policy").GetString() != FractureResponse.WholeObjectPolicy) ||
            (version == 7 && d.GetProperty("ram_policy").GetString() != FractureResponse.FenceTotalPolicy) ||
            (version == 8 && d.GetProperty("ram_policy").GetString() != FractureResponse.FenceAngularPolicy) ||
            d.GetProperty("profile").GetString() != "test_lab" ||
            d.GetProperty("map").GetString() != map ||
            d.GetProperty("physics_manifest_sha256").GetString() != source.PhysicsHash ||
            d.GetProperty("projectile_manifest_sha256").GetString() != source.ProjectileHash ||
            obstacles.GetProperty("sha256").GetString() != source.PhysicsHash)
            throw new InvalidDataException("catalog profile mismatch");
        var rows = d.GetProperty("objects");
        int maximum = version >= 4 ? MaxExtendedCatalogObjects : contacts ? MaxContactCatalogObjects : MaxCatalogObjects;
        if (rows.ValueKind != JsonValueKind.Array || rows.GetArrayLength() < 1 || rows.GetArrayLength() > maximum)
            throw new InvalidDataException("catalog count outside bound");
        var entries = new List<CatalogEntry>();
        var columns = new List<CatalogEntry>();
        var instances = new HashSet<int>();
        uint previous = 0;
        foreach (var row in rows.EnumerateArray())
        {
            if (falling && row.GetProperty("kind").GetString() == "falling_atom")
            {
                Fields(row, "object_id", "instance_id", "first_triangle", "triangle_count", "object_revision", "kind", "ram_energy_j", "ram_response");
                uint cid = row.GetProperty("object_id").GetUInt32();
                int cinstance = row.GetProperty("instance_id").GetInt32(), cfirst = row.GetProperty("first_triangle").GetInt32();
                int ccount = row.GetProperty("triangle_count").GetInt32();
                var crevision = row.GetProperty("object_revision").GetString()!; Sha256(crevision);
                if (row.GetProperty("ram_energy_j").GetInt32() != 0 || row.GetProperty("ram_response").GetString() != FallingAtomResponse ||
                    cid <= previous || cinstance < 0 || cinstance >= source.InstanceCount || !instances.Add(cinstance) ||
                    cfirst < 0 || ccount < 1 || ccount > MaxTriggerTrianglesPerObject || (long)cfirst + ccount > triggers!.TriangleCount)
                    throw new InvalidDataException("falling atom identity/trigger span bound");
                previous = cid; columns.Add(new(cid, cinstance, cfirst, ccount, crevision, "falling_atom", 0, FallingAtomResponse));
                continue;
            }
            if (version is 7 or 8) Fields(row, "object_id", "instance_id", "first_triangle", "triangle_count", "object_revision", "kind", "ram_energy_j", "ram_response");
            else if (version is 5 or 6) Fields(row, "object_id", "instance_id", "first_triangle", "triangle_count", "object_revision", "kind", "ram_energy_j");
            else if (contacts) Fields(row, "object_id", "instance_id", "first_triangle", "triangle_count", "object_revision", "kind");
            else Fields(row, "object_id", "instance_id", "first_triangle", "triangle_count", "object_revision");
            uint id = row.GetProperty("object_id").GetUInt32();
            int instance = row.GetProperty("instance_id").GetInt32(), first = row.GetProperty("first_triangle").GetInt32();
            int count = row.GetProperty("triangle_count").GetInt32();
            var revision = row.GetProperty("object_revision").GetString()!; Sha256(revision);
            string kind = contacts ? row.GetProperty("kind").GetString()! : "fragile";
            if (kind is not ("tree" or "fragile")) throw new InvalidDataException("catalog object kind");
            int energy = version is 5 or 6 or 7 or 8 ? row.GetProperty("ram_energy_j").GetInt32() : 0;
            string? response = version is 7 or 8 ? row.GetProperty("ram_response").GetString() : null;
            if (version == 7 && (response is not ("normal_linear" or "total_linear") ||
                (response == "total_linear" && kind != "fragile")))
                throw new InvalidDataException("catalog fracture response/kind mismatch");
            if (version == 8 && (response is not ("normal_linear" or "total_linear_angular_fallback") ||
                (response == "total_linear_angular_fallback" && kind != "fragile")))
                throw new InvalidDataException("catalog angular response/kind mismatch");
            // Catalog6 extends the same bounded normal-energy response to all
            // source-joined whole objects. Catalog5 keeps its fence-only
            // projection, including zero-energy trees and ordinary fragiles.
            if (version is 6 or 7 or 8 ? energy != FractureResponse.EnergyJ :
                energy is not (0 or FractureResponse.EnergyJ) || (energy > 0 && kind != "fragile"))
                throw new InvalidDataException("catalog fracture energy/kind mismatch");
            if (id <= previous || instance < 0 || instance >= source.InstanceCount || !instances.Add(instance) ||
                first < 0 || count < 1 || count > 4096 || (long)first + count > source.TriangleCount)
                throw new InvalidDataException("catalog identity/span bound");
            previous = id; entries.Add(new(id, instance, first, count, revision, kind, energy, response));
        }
        var spans = entries.OrderBy(e => e.FirstTriangle).ToArray();
        for (int i = 1; i < spans.Length; i++)
            if (spans[i].FirstTriangle < spans[i - 1].FirstTriangle + spans[i - 1].TriangleCount)
                throw new InvalidDataException("overlapping catalog spans");
        var triggerSpans = columns.OrderBy(e => e.FirstTriangle).ToArray();
        for (int i = 1; i < triggerSpans.Length; i++)
            if (triggerSpans[i].FirstTriangle < triggerSpans[i - 1].FirstTriangle + triggerSpans[i - 1].TriangleCount)
                throw new InvalidDataException("overlapping trigger spans");
        if (falling && columns.Count == 0) throw new InvalidDataException("catalog9 without falling atoms");
        return new(hash, map, entries.ToArray(), contacts, version, columns.ToArray(), triggers);
    }

    // MAPS-02 trigger mesh: two hash-pinned buffers beside the catalog, the
    // same float32/uint32 layout and bounds as LoadMeshCore. Never collision.
    static TriggerMesh LoadTriggers(string directory, JsonElement reference)
    {
        Fields(reference, "vertices", "triangles");
        byte[] Part(string name, string format, string expectedFile, int maxCount)
        {
            var part = reference.GetProperty(name);
            Fields(part, "file", "format", "stride", "count", "bytes", "sha256");
            int count = part.GetProperty("count").GetInt32();
            if (part.GetProperty("file").GetString() != expectedFile || part.GetProperty("format").GetString() != format ||
                part.GetProperty("stride").GetInt32() != 12 || count < 1 || count > maxCount || part.GetProperty("bytes").GetInt32() != checked(count * 12))
                throw new InvalidDataException("trigger part shape mismatch");
            var bytes = FileBytes(Owned(directory, Path.Combine(directory, expectedFile)), checked(maxCount * 12), part.GetProperty("sha256").GetString());
            if (bytes.Length != count * 12) throw new InvalidDataException("trigger part truncated");
            return bytes;
        }
        var rawVertices = Part("vertices", "float32_xyz", "falling-atom-triggers.vertices.f32", MaxTriggerTriangles * 3);
        var rawTriangles = Part("triangles", "uint32_abc", "falling-atom-triggers.triangles.u32", MaxTriggerTriangles);
        var vertices = new Vector3[rawVertices.Length / 12];
        for (int i = 0; i < vertices.Length; i++)
        {
            float Read(int axis) => BinaryPrimitives.ReadSingleLittleEndian(rawVertices.AsSpan(i * 12 + axis * 4, 4));
            var v = new Vector3(Read(0), Read(1), Read(2));
            if (!float.IsFinite(v.X) || !float.IsFinite(v.Y) || !float.IsFinite(v.Z) || Math.Abs(v.X) > 2000 || Math.Abs(v.Y) > 2000 || Math.Abs(v.Z) > 2000)
                throw new InvalidDataException("trigger vertex outside bound");
            vertices[i] = v;
        }
        var indices = new uint[rawTriangles.Length / 4];
        for (int i = 0; i < indices.Length / 3; i++)
        {
            uint Read(int axis) => BinaryPrimitives.ReadUInt32LittleEndian(rawTriangles.AsSpan(i * 12 + axis * 4, 4));
            uint a = Read(0), b = Read(1), c = Read(2);
            if (a >= vertices.Length || b >= vertices.Length || c >= vertices.Length || a == b || b == c || a == c)
                throw new InvalidDataException("trigger triangle index outside bound");
            var cross = Vector3.Cross(vertices[b] - vertices[a], vertices[c] - vertices[a]);
            if (!float.IsFinite(cross.LengthSquared()) || cross.LengthSquared() <= 1e-16f)
                throw new InvalidDataException("degenerate float32 trigger triangle");
            indices[i * 3] = a; indices[i * 3 + 1] = b; indices[i * 3 + 2] = c;
        }
        return new(vertices, indices);
    }

    public static MeshShape TriggerShape(TriggerMesh mesh, CatalogEntry entry)
    {
        var selectedVertices = new Vector3[entry.TriangleCount * 3];
        var selectedTriangles = new IndexedTriangle[entry.TriangleCount];
        for (int i = 0; i < entry.TriangleCount; i++)
        {
            for (int axis = 0; axis < 3; axis++)
                selectedVertices[i * 3 + axis] = mesh.Vertices[mesh.Indices[(entry.FirstTriangle + i) * 3 + axis]];
            selectedTriangles[i] = new((uint)i * 3, (uint)i * 3 + 1, (uint)i * 3 + 2);
        }
        using var settings = new MeshShapeSettings(selectedVertices.AsSpan(), selectedTriangles.AsSpan());
        return new MeshShape(settings);
    }

    public static Scene MakeScene(CatalogSpec catalog, uint[] ids)
    {
        if (ids.Length > catalog.MaxRemoved) throw new InvalidDataException("scene count bound");
        uint previous = 0;
        foreach (uint id in ids)
        {
            if (id <= previous || !catalog.Known(id)) throw new InvalidDataException("unknown or unordered scene ID");
            previous = id;
        }
        using var bytes = new MemoryStream();
        bytes.Write(Encoding.ASCII.GetBytes("wot091-fragile-scene-v3\0"));
        bytes.Write(Convert.FromHexString(catalog.Hash));
        Span<byte> word = stackalloc byte[4];
        BinaryPrimitives.WriteUInt32LittleEndian(word, (uint)ids.Length); bytes.Write(word);
        foreach (uint id in ids) { BinaryPrimitives.WriteUInt32LittleEndian(word, id); bytes.Write(word); }
        return new(ids.ToArray(), Hash(bytes.ToArray()));
    }

    public static Scene SceneCommand(JsonElement request, string op, CatalogSpec catalog, uint generation, string configHash, long sequence)
    {
        if (catalog.Contacts)
            Fields(request, "version", "op", "generation", "config_sha256", "catalog_sha256", "advance_seq",
                "scene_version", "removed_object_ids", "scene_sha256", "contacts");
        else
            Fields(request, "version", "op", "generation", "config_sha256", "catalog_sha256", "advance_seq",
                "scene_version", "removed_object_ids", "scene_sha256");
        var values = request.GetProperty("removed_object_ids");
        if (values.ValueKind != JsonValueKind.Array || values.GetArrayLength() > catalog.MaxRemoved ||
            (catalog.Contacts && request.GetProperty("contacts").ValueKind != JsonValueKind.True))
            throw new InvalidDataException("scene count bound");
        var scene = MakeScene(catalog, values.EnumerateArray().Select(v => v.GetUInt32()).ToArray());
        if (request.GetProperty("version").GetInt32() != catalog.IpcVersion || request.GetProperty("op").GetString() != op ||
            request.GetProperty("generation").GetUInt32() != generation || request.GetProperty("config_sha256").GetString() != configHash ||
            request.GetProperty("catalog_sha256").GetString() != catalog.Hash || request.GetProperty("advance_seq").GetInt64() != sequence ||
            request.GetProperty("scene_version").GetUInt32() != scene.Version || request.GetProperty("scene_sha256").GetString() != scene.Hash)
            throw new InvalidDataException("catalog scene identity/version mismatch");
        return scene;
    }

    public static RemovalSpec LoadRemoval(string root, string path, string hash, string map, JsonElement obstacles)
    {
        using var doc = Json(FileBytes(Owned(root, path), 4096, hash));
        var d = doc.RootElement;
        Fields(d, "version", "profile", "map", "object_id", "instance_id", "physics_manifest_sha256",
            "projectile_manifest_sha256", "first_triangle", "triangle_count", "object_revision");
        if (d.GetProperty("version").GetInt32() != 1 || d.GetProperty("profile").GetString() != "test_lab" ||
            map != "01_karelia" || d.GetProperty("map").GetString() != map ||
            d.GetProperty("object_id").GetUInt32() != 1 || d.GetProperty("instance_id").GetInt32() != 1513 ||
            d.GetProperty("physics_manifest_sha256").GetString() != PhysicsManifestHash ||
            d.GetProperty("projectile_manifest_sha256").GetString() != ProjectileManifestHash ||
            d.GetProperty("first_triangle").GetInt32() != 171814 || d.GetProperty("triangle_count").GetInt32() != 42 ||
            d.GetProperty("object_revision").GetString() != ObjectRevision ||
            obstacles.GetProperty("sha256").GetString() != PhysicsManifestHash)
            throw new InvalidDataException("one-object descriptor profile mismatch");
        return new(hash, 1, 1513, 171814, 42, ObjectRevision);
    }
    public static void Fields(JsonElement value, params string[] names)
    {
        if (value.ValueKind != JsonValueKind.Object) throw new InvalidDataException("object required");
        var actual = value.EnumerateObject().Select(p => p.Name).ToArray();
        if (actual.Length != names.Length || actual.Distinct().Count() != actual.Length ||
            !actual.ToHashSet().SetEquals(names)) throw new InvalidDataException("unexpected or duplicate fields");
    }

    public static float Number(JsonElement value, float low, float high)
    {
        if (!value.TryGetSingle(out var result) || !float.IsFinite(result) || result < low || result > high)
            throw new InvalidDataException("number outside bound");
        return result;
    }

    public static Vector3 Vector(JsonElement value, float low, float high)
    {
        if (value.ValueKind != JsonValueKind.Array || value.GetArrayLength() != 3)
            throw new InvalidDataException("three coordinates required");
        return new(Number(value[0], low, high), Number(value[1], low, high), Number(value[2], low, high));
    }

    public static string Owned(string root, string path)
    {
        var full = Path.GetFullPath(path, root);
        var prefix = Path.TrimEndingDirectorySeparator(Path.GetFullPath(root)) + Path.DirectorySeparatorChar;
        if (!full.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("asset outside local root");
        for (string? item = full; item != null; item = Path.GetDirectoryName(item))
            if ((File.GetAttributes(item) & FileAttributes.ReparsePoint) != 0)
                throw new InvalidDataException("asset reparse point refused");
        return full;
    }

    public static byte[] FileBytes(string path, int maximum, string? expectedHash)
    {
        if (expectedHash == null || expectedHash.Length != 64 || expectedHash.Any(c => !"0123456789abcdef".Contains(c)))
            throw new InvalidDataException("lowercase SHA256 required");
        using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read);
        if (stream.Length <= 0 || stream.Length > maximum) throw new InvalidDataException("asset size outside bound");
        var data = new byte[checked((int)stream.Length)];
        stream.ReadExactly(data);
        if (Hash(data) != expectedHash) throw new InvalidDataException("asset SHA256 mismatch");
        return data;
    }

    public static string Hash(byte[] bytes) => Convert.ToHexStringLower(SHA256.HashData(bytes));

    public static JsonDocument Json(byte[] data) => JsonDocument.Parse(data,
        new JsonDocumentOptions { MaxDepth = 12, AllowTrailingCommas = false, CommentHandling = JsonCommentHandling.Disallow });

    public static JsonDocument IpcJson(byte[] data, bool angular)
    {
        var document = Json(data);
        if (!angular) return document;
        try
        {
            int count = 0;
            void Visit(JsonElement value)
            {
                if (++count > 4096) throw new InvalidDataException("angular IPC node bound");
                if (value.ValueKind == JsonValueKind.Array)
                    foreach (var child in value.EnumerateArray()) Visit(child);
                else if (value.ValueKind == JsonValueKind.Object)
                    foreach (var child in value.EnumerateObject()) Visit(child.Value);
            }
            Visit(document.RootElement); return document;
        }
        catch { document.Dispose(); throw; }
    }

    public const int MaxIpcLineBytes = 32 * 1024;
    public const int MaxAngularIpcLineBytes = 64 * 1024;
    public static byte[] AngularLine(object frame)
    {
        byte[] payload = JsonSerializer.SerializeToUtf8Bytes(frame);
        if (payload.Length > MaxAngularIpcLineBytes) throw new InvalidDataException("angular IPC output bound");
        byte[] line = new byte[payload.Length + 1];
        payload.CopyTo(line, 0); line[^1] = 10;
        return line; // IPC6 is explicitly JSON + LF, never platform CRLF.
    }
    public static byte[]? ReadLine(Stream stream, int maximum = MaxIpcLineBytes)
    {
        if (maximum is not (MaxIpcLineBytes or MaxAngularIpcLineBytes)) throw new ArgumentOutOfRangeException(nameof(maximum));
        using var line = new MemoryStream();
        while (true)
        {
            int value = stream.ReadByte();
            if (value < 0)
            {
                if (line.Length != 0) throw new InvalidDataException("partial IPC line at EOF");
                return null;
            }
            if (value == 10) return line.ToArray();
            if (line.Length >= maximum || value == 0 || value > 127) throw new InvalidDataException("IPC line outside bound");
            line.WriteByte((byte)value);
        }
    }

    public static MeshShape LoadMesh(string root, JsonElement reference, string map) => LoadMesh(root, reference, map, null, out _);

    public static MeshShape LoadMesh(string root, JsonElement reference, string map, RemovalSpec? removal, out MeshShape? selected)
    {
        var result = LoadMeshCore(root, reference, map, removal, null, out var shapes);
        selected = shapes.Count == 0 ? null : shapes.Single().Value;
        return result;
    }

    public static MeshShape LoadCatalogMesh(string root, JsonElement reference, string map, CatalogSpec catalog, out Dictionary<uint, MeshShape> selected)
        => LoadMeshCore(root, reference, map, null, catalog, out selected);

    private static MeshShape LoadMeshCore(string root, JsonElement reference, string map, RemovalSpec? removal, CatalogSpec? catalog, out Dictionary<uint, MeshShape> selected)
    {
        selected = new();
        Fields(reference, "path", "sha256");
        var path = Owned(root, reference.GetProperty("path").GetString()!);
        using var doc = Json(FileBytes(path, 8 * 1024 * 1024, reference.GetProperty("sha256").GetString()));
        var value = doc.RootElement;
        if (value.GetProperty("version").GetInt32() != 1 || value.GetProperty("map").GetString() != map ||
            value.GetProperty("kind").GetString() != "original_091_static_triangle_mesh")
            throw new InvalidDataException("mesh version or map mismatch");
        var coords = value.GetProperty("coordinates");
        if (coords.GetProperty("unit").GetString() != "metre" || coords.GetProperty("up_axis").GetString() != "Y" ||
            coords.GetProperty("order").GetString() != "XYZ" || coords.GetProperty("endianness").GetString() != "little" ||
            coords.GetProperty("space").GetString() != "original world")
            throw new InvalidDataException("mesh coordinate system mismatch");
        byte[] ReadPart(string name, string format, int maxCount)
        {
            var part = value.GetProperty(name);
            int count = part.GetProperty("count").GetInt32();
            var file = part.GetProperty("file").GetString()!;
            if (count < 1 || count > maxCount || Path.GetFileName(file) != file ||
                part.GetProperty("stride").GetInt32() != 12 || part.GetProperty("format").GetString() != format ||
                part.GetProperty("bytes").GetInt32() != checked(count * 12)) throw new InvalidDataException("mesh part shape mismatch");
            var bytes = FileBytes(Owned(root, Path.Combine(Path.GetDirectoryName(path)!, file)),
                checked(maxCount * 12), part.GetProperty("sha256").GetString());
            if (bytes.Length != count * 12) throw new InvalidDataException("mesh part truncated");
            return bytes;
        }
        var rawVertices = ReadPart("vertices", "float32_xyz", 2_000_000);
        var rawTriangles = ReadPart("triangles", "uint32_abc", 1_500_000);
        var vertices = new Vector3[rawVertices.Length / 12];
        for (int i = 0; i < vertices.Length; i++)
        {
            float Read(int axis) => BinaryPrimitives.ReadSingleLittleEndian(rawVertices.AsSpan(i * 12 + axis * 4, 4));
            var v = new Vector3(Read(0), Read(1), Read(2));
            if (!float.IsFinite(v.X) || !float.IsFinite(v.Y) || !float.IsFinite(v.Z) ||
                Math.Abs(v.X) > 2000 || Math.Abs(v.Y) > 2000 || Math.Abs(v.Z) > 2000)
                throw new InvalidDataException("mesh vertex outside bound");
            vertices[i] = v;
        }
        var triangles = new IndexedTriangle[rawTriangles.Length / 12];
        for (int i = 0; i < triangles.Length; i++)
        {
            uint Read(int axis) => BinaryPrimitives.ReadUInt32LittleEndian(rawTriangles.AsSpan(i * 12 + axis * 4, 4));
            uint a = Read(0), b = Read(1), c = Read(2);
            if (a >= vertices.Length || b >= vertices.Length || c >= vertices.Length || a == b || b == c || a == c)
                throw new InvalidDataException("mesh triangle index outside bound");
            // Float32 transforms may collapse a formerly nonzero source face.
            // Refuse it explicitly instead of relying on a native assertion.
            var cross = Vector3.Cross(vertices[b] - vertices[a], vertices[c] - vertices[a]);
            if (!float.IsFinite(cross.LengthSquared()) || cross.LengthSquared() <= 1e-16f)
                throw new InvalidDataException("degenerate float32 mesh triangle");
            triangles[i] = new(a, b, c);
        }
        if (removal == null && catalog == null)
        {
            using var settings = new MeshShapeSettings(vertices.AsSpan(), triangles.AsSpan());
            return new MeshShape(settings);
        }
        var source = CatalogProfile(map);
        if ((catalog != null && catalog.Map != map) || reference.GetProperty("sha256").GetString() != source.PhysicsHash ||
            triangles.Length != source.TriangleCount)
            throw new InvalidDataException("removal geometry source mismatch");
        var instances = value.GetProperty("instances");
        if (instances.GetArrayLength() != source.InstanceCount) throw new InvalidDataException("removal source instance count");
        if (removal != null)
        {
        if (map != "01_karelia") throw new InvalidDataException("legacy removal requires Karelia");
        var item = instances[removal.InstanceId];
        if (item.GetProperty("kind").GetString() != "model" || item.GetProperty("instance").GetString() != "/model[2]" ||
            item.GetProperty("resource").GetString() != "content/MilitaryEnvironment/mle009_BoxCamouflage/normal/lod0/mle009_BoxCamouflage.model" ||
            item.GetProperty("chunk").GetArrayLength() != 2 || item.GetProperty("chunk")[0].GetInt32() != -5 || item.GetProperty("chunk")[1].GetInt32() != -5 ||
            item.GetProperty("first_triangle").GetInt32() != removal.FirstTriangle || item.GetProperty("triangles").GetInt32() != removal.TriangleCount ||
            removal.FirstTriangle < 0 || removal.TriangleCount != 42 || removal.FirstTriangle + removal.TriangleCount > triangles.Length)
            throw new InvalidDataException("one-object source identity/span mismatch");
        }
        var entries = catalog?.Entries ?? [new CatalogEntry(removal!.ObjectId, removal.InstanceId, removal.FirstTriangle, removal.TriangleCount, removal.Revision, "fragile", 0)];
        foreach (var entry in entries)
        {
            var item = instances[entry.InstanceId];
            string? resource = item.GetProperty("resource").GetString();
            string expectedSourceKind = entry.Kind == "tree" ? "speedtree" : "model";
            if (item.GetProperty("kind").GetString() != expectedSourceKind || string.IsNullOrEmpty(resource) || resource.Length > 1024 ||
                item.GetProperty("first_triangle").GetInt32() != entry.FirstTriangle || item.GetProperty("triangles").GetInt32() != entry.TriangleCount ||
                (long)entry.FirstTriangle + entry.TriangleCount > triangles.Length)
                throw new InvalidDataException("catalog source identity/full-span mismatch");
        }
        // Preserve every base triangle/index/coordinate exactly. The selected
        // shape gets its own compact vertices; no new hull or AABB substitute.
        var baseTriangles = new IndexedTriangle[triangles.Length - entries.Sum(e => e.TriangleCount)];
        int sourceIndex = 0, destIndex = 0;
        foreach (var entry in entries.OrderBy(e => e.FirstTriangle))
        {
            int count = entry.FirstTriangle - sourceIndex;
            Array.Copy(triangles, sourceIndex, baseTriangles, destIndex, count);
            destIndex += count; sourceIndex = entry.FirstTriangle + entry.TriangleCount;
        }
        Array.Copy(triangles, sourceIndex, baseTriangles, destIndex, triangles.Length - sourceIndex);
        using var baseSettings = new MeshShapeSettings(vertices.AsSpan(), baseTriangles.AsSpan());
        var baseShape = new MeshShape(baseSettings);
        try
        {
            foreach (var entry in entries)
            {
                var selectedVertices = new Vector3[entry.TriangleCount * 3];
                var selectedTriangles = new IndexedTriangle[entry.TriangleCount];
                for (int i = 0; i < entry.TriangleCount; i++)
                {
                    for (int axis = 0; axis < 3; axis++)
                        selectedVertices[i * 3 + axis] = vertices[BinaryPrimitives.ReadUInt32LittleEndian(rawTriangles.AsSpan((entry.FirstTriangle + i) * 12 + axis * 4, 4))];
                    selectedTriangles[i] = new((uint)i * 3, (uint)i * 3 + 1, (uint)i * 3 + 2);
                }
                using var selectedSettings = new MeshShapeSettings(selectedVertices.AsSpan(), selectedTriangles.AsSpan());
                selected.Add(entry.ObjectId, new MeshShape(selectedSettings));
            }
            return baseShape;
        }
        catch { foreach (var shape in selected.Values) shape.Dispose(); baseShape.Dispose(); throw; }
    }
}
