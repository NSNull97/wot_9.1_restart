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

    public static byte[]? ReadLine(Stream stream)
    {
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
            if (line.Length >= 1024 || value == 0 || value > 127) throw new InvalidDataException("IPC line outside bound");
            line.WriteByte((byte)value);
        }
    }

    public static MeshShape LoadMesh(string root, JsonElement reference, string map)
    {
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
        using var settings = new MeshShapeSettings(vertices.AsSpan(), triangles.AsSpan());
        return new MeshShape(settings);
    }
}
