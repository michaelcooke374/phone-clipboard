namespace ClipRoo.Core.Items;

/// <summary>Safe file names for what the phone sends.</summary>
public static class FileNames
{
    private const int MaxLength = 150;
    private static readonly char[] NotAllowed = ['<', '>', ':', '"', '/', '\\', '|', '?', '*'];
    private static readonly HashSet<string> Reserved = new(StringComparer.OrdinalIgnoreCase)
    {
        "CON", "PRN", "AUX", "NUL",
        "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
        "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
    };

    /// <summary>A name Windows accepts, without any folder part, or <paramref name="fallback"/>.</summary>
    public static string Clean(string? name, string fallback)
    {
        if (string.IsNullOrWhiteSpace(name)) return fallback;
        // Only the last part: "../../evil.exe" and "C:\x\y.txt" can't reach other folders.
        var last = name.Replace('\\', '/').Split('/').Last();
        var chars = last.Where(c => c >= 32 && Array.IndexOf(NotAllowed, c) < 0).ToArray();
        var clean = new string(chars).Trim().TrimEnd('.', ' ');
        if (clean.Length == 0 || clean.All(c => c == '.')) return fallback;
        var stem = Path.GetFileNameWithoutExtension(clean);
        var ext = Path.GetExtension(clean);
        if (Reserved.Contains(stem)) stem = "_" + stem;
        if (ext.Length > 20) ext = "";                  // not really an extension
        if (stem.Length + ext.Length > MaxLength) stem = stem[..Math.Max(1, MaxLength - ext.Length)].TrimEnd('.', ' ');
        return stem + ext;
    }

    /// <summary>A path in <paramref name="folder"/> that doesn't exist yet: "name.ext", "name (2).ext", ...</summary>
    public static string Unique(string folder, string name)
    {
        var path = Path.Combine(folder, name);
        if (!File.Exists(path)) return path;
        var stem = Path.GetFileNameWithoutExtension(name);
        var ext = Path.GetExtension(name);
        for (var n = 2; ; n++)
        {
            path = Path.Combine(folder, $"{stem} ({n}){ext}");
            if (!File.Exists(path)) return path;
        }
    }

    private static readonly Dictionary<string, string> Types = new(StringComparer.OrdinalIgnoreCase)
    {
        [".txt"] = "text/plain", [".pdf"] = "application/pdf", [".jpg"] = "image/jpeg", [".jpeg"] = "image/jpeg",
        [".png"] = "image/png", [".gif"] = "image/gif", [".webp"] = "image/webp", [".heic"] = "image/heic",
        [".heif"] = "image/heif", [".bmp"] = "image/bmp", [".mp4"] = "video/mp4", [".mov"] = "video/quicktime",
        [".mp3"] = "audio/mpeg", [".m4a"] = "audio/mp4", [".wav"] = "audio/wav", [".zip"] = "application/zip",
        [".doc"] = "application/msword",
        [".docx"] = "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        [".xls"] = "application/vnd.ms-excel",
        [".xlsx"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        [".ppt"] = "application/vnd.ms-powerpoint",
        [".pptx"] = "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        [".csv"] = "text/csv", [".html"] = "text/html", [".json"] = "application/json", [".rtf"] = "application/rtf",
    };

    public static string TypeOf(string path) =>
        Types.TryGetValue(Path.GetExtension(path), out var type) ? type : "application/octet-stream";
}
