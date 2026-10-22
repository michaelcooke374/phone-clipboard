namespace ClipRoo.Core.Platform;

public enum PictureFormat { Unknown, Jpeg, Png, Gif, WebP, Bmp, Heic }

/// <summary>Recognises picture files by their first bytes or their extension.</summary>
public static class PictureFormats
{
    public static PictureFormat Detect(ReadOnlySpan<byte> head)
    {
        if (head.StartsWith((byte[])[0xFF, 0xD8, 0xFF])) return PictureFormat.Jpeg;
        if (head.StartsWith((byte[])[0x89, (byte)'P', (byte)'N', (byte)'G', 0x0D, 0x0A, 0x1A, 0x0A])) return PictureFormat.Png;
        if (head.StartsWith("GIF87a"u8) || head.StartsWith("GIF89a"u8)) return PictureFormat.Gif;
        if (head.Length >= 12 && head[..4].SequenceEqual("RIFF"u8) && head[8..12].SequenceEqual("WEBP"u8)) return PictureFormat.WebP;
        if (head.Length >= 18 && head.StartsWith("BM"u8))
        {
            var headerSize = BitConverter.ToInt32(head[14..18]);
            if (headerSize is 12 or 40 or 52 or 56 or 108 or 124) return PictureFormat.Bmp;
        }
        if (head.Length >= 12 && head[4..8].SequenceEqual("ftyp"u8))
        {
            var brand = head[8..12];
            if (brand.SequenceEqual("heic"u8) || brand.SequenceEqual("heix"u8) || brand.SequenceEqual("hevc"u8)
                || brand.SequenceEqual("mif1"u8) || brand.SequenceEqual("msf1"u8))
                return PictureFormat.Heic;
        }
        return PictureFormat.Unknown;
    }

    public static PictureFormat FromExtension(string path) => Path.GetExtension(path).ToLowerInvariant() switch
    {
        ".jpg" or ".jpeg" => PictureFormat.Jpeg,
        ".png" => PictureFormat.Png,
        ".gif" => PictureFormat.Gif,
        ".webp" => PictureFormat.WebP,
        ".bmp" => PictureFormat.Bmp,
        ".heic" or ".heif" => PictureFormat.Heic,
        _ => PictureFormat.Unknown,
    };

    public static string Extension(PictureFormat format) => format switch
    {
        PictureFormat.Jpeg => ".jpg",
        PictureFormat.Png => ".png",
        PictureFormat.Gif => ".gif",
        PictureFormat.WebP => ".webp",
        PictureFormat.Bmp => ".bmp",
        PictureFormat.Heic => ".heic",
        _ => "",
    };

    public static string MimeType(PictureFormat format) => format switch
    {
        PictureFormat.Jpeg => "image/jpeg",
        PictureFormat.Png => "image/png",
        PictureFormat.Gif => "image/gif",
        PictureFormat.WebP => "image/webp",
        PictureFormat.Bmp => "image/bmp",
        PictureFormat.Heic => "image/heic",
        _ => "application/octet-stream",
    };
}
