using System.Buffers.Binary;
using System.Text;
using System.Text.Json;

namespace MapDrive;

// #717 authored ground-type grid extracted independently of the collision mesh.
internal sealed class GroundStrengthMap
{
    const int HeaderSize = 86, TileHeaderSize = 6, ChunkSize = 100;
    public const int MaxBytes = 8 * 1024 * 1024;
    readonly record struct Tile(int Size, int Offset);
    readonly Dictionary<(int X, int Z), Tile> tiles;
    readonly byte[] bytes;

    GroundStrengthMap(Dictionary<(int, int), Tile> tiles, byte[] bytes)
    {
        this.tiles = tiles;
        this.bytes = bytes;
    }

    public static GroundStrengthMap Load(string root, JsonElement reference, string map, string terrainHash)
    {
        CheckedInput.Fields(reference, "path", "sha256");
        CheckedInput.Sha256(terrainHash);
        var bytes = CheckedInput.FileBytes(CheckedInput.Owned(root, reference.GetProperty("path").GetString()!),
            MaxBytes, reference.GetProperty("sha256").GetString()!);
        if (bytes.Length < HeaderSize || !bytes.AsSpan(0, 8).SequenceEqual("WOTGND1\0"u8) ||
            Encoding.ASCII.GetString(bytes, 8, 44).TrimEnd('\0') != map ||
            !bytes.AsSpan(52, 32).SequenceEqual(Convert.FromHexString(terrainHash)))
            throw new InvalidDataException("ground strength map or terrain binding");
        int count = BinaryPrimitives.ReadUInt16LittleEndian(bytes.AsSpan(84));
        if (count is < 1 or > 1024) throw new InvalidDataException("ground strength tile count");
        var tiles = new Dictionary<(int, int), Tile>(count);
        int offset = HeaderSize;
        for (int i = 0; i < count; i++)
        {
            if (bytes.Length - offset < TileHeaderSize) throw new InvalidDataException("ground strength tile header");
            int x = BinaryPrimitives.ReadInt16LittleEndian(bytes.AsSpan(offset));
            int z = BinaryPrimitives.ReadInt16LittleEndian(bytes.AsSpan(offset + 2));
            int size = BinaryPrimitives.ReadUInt16LittleEndian(bytes.AsSpan(offset + 4));
            offset += TileHeaderSize;
            if (x is < -64 or > 64 || z is < -64 or > 64 || size is not (16 or 32 or 64 or 128) ||
                bytes.Length - offset < size * size || !tiles.TryAdd((x, z), new(size, offset)))
                throw new InvalidDataException("ground strength tile bounds or duplicate");
            for (int end = offset + size * size; offset < end; offset++)
                if (bytes[offset] > 5) throw new InvalidDataException("unknown #717 ground strength");
        }
        if (offset != bytes.Length) throw new InvalidDataException("trailing ground strength bytes");
        return new(tiles, bytes);
    }

    // The map grid uses local X/Z, nearest sample and [0,size-1] endpoints.
    public int ResistanceIndex(float x, float z)
    {
        int tileX = (int)MathF.Floor(x / ChunkSize), tileZ = (int)MathF.Floor(z / ChunkSize);
        if (!tiles.TryGetValue((tileX, tileZ), out var tile)) return 0;
        int Texel(float coordinate, int chunk) => Math.Clamp(
            (int)(((coordinate - chunk * ChunkSize) / ChunkSize) * (tile.Size - 1) + .5f), 0, tile.Size - 1);
        return bytes[tile.Offset + Texel(z, tileZ) * tile.Size + Texel(x, tileX)] switch
        {
            2 => 1,
            3 => 2,
            // Firm, unset and special ground types retain the hard profile.
            _ => 0
        };
    }
}
