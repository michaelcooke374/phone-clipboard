using System.Text.Json;
using ClipRoo.Core.Protocol;

namespace ClipRoo.Core;

/// <summary>Small JSON files in ClipRoo's data folder, written whole or not at all.</summary>
internal static class JsonFile
{
    public static T? Read<T>(string path) where T : class
    {
        if (!File.Exists(path)) return null;
        try
        {
            return JsonSerializer.Deserialize<T>(File.ReadAllBytes(path), Json.Options);
        }
        catch (Exception e) when (e is JsonException or IOException or NotSupportedException)
        {
            // Damaged (a crash mid-write on an old version, a hand edit): kept aside, started afresh.
            TryMove(path, path + ".damaged");
            return null;
        }
    }

    public static void Write<T>(string path, T value)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        var part = path + ".part";
        File.WriteAllBytes(part, JsonSerializer.SerializeToUtf8Bytes(value, Json.Options));
        File.Move(part, path, overwrite: true);
    }

    private static void TryMove(string from, string to)
    {
        try { File.Move(from, to, overwrite: true); } catch (IOException) { } catch (UnauthorizedAccessException) { }
    }
}
