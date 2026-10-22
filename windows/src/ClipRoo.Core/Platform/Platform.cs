namespace ClipRoo.Core.Platform;

// What the core needs from Windows. The Windows app implements these; the tests use stand-ins.

/// <summary>What's copied on the PC.</summary>
public abstract record ClipContent;

public sealed record ClipText(string Text) : ClipContent;

/// <summary>A copied picture, already turned into PNG (or another type the iPhone shows).</summary>
public sealed record ClipPicture(byte[] Data, string Type, int Width, int Height) : ClipContent;

/// <summary>Files copied in File Explorer.</summary>
public sealed record ClipFiles(IReadOnlyList<string> Paths) : ClipContent;

public interface IClipboard
{
    /// <summary>Changes whenever anything is copied (Windows' clipboard sequence number).</summary>
    long Sequence { get; }

    /// <summary>What's copied now, or null when it's nothing ClipRoo can send. Throws
    /// <see cref="ClipboardBusyException"/> when another program holds the clipboard.</summary>
    ClipContent? Read();

    void WriteText(string text);

    /// <summary>The picture as a bitmap, as PNG (when there is one) and as the saved file.</summary>
    void WritePicture(PreparedPicture picture, string savedPath);

    /// <summary>Files, as File Explorer puts them on the clipboard.</summary>
    void WriteFiles(IReadOnlyList<string> paths);
}

public sealed class ClipboardBusyException : Exception
{
    public ClipboardBusyException() : base("Another program is using the clipboard.") { }
}

/// <summary>A picture from the phone, ready for the clipboard.</summary>
/// <param name="Dib">A Windows bitmap (CF_DIB): the right way up, transparency on white.</param>
/// <param name="Png">PNG bytes, for PNG pictures only (null for photos).</param>
public sealed record PreparedPicture(byte[] Dib, byte[]? Png, int Width, int Height);

public interface IPictures
{
    /// <summary>Opens a picture the phone sent (JPEG, PNG, GIF, WebP or BMP) for the clipboard.
    /// Throws <see cref="UnsupportedPictureException"/> when it can't.</summary>
    PreparedPicture Prepare(string path, PictureFormat format);
}

public sealed class UnsupportedPictureException(string message) : Exception(message);

public interface INotifier
{
    void Notify(string title, string message);
}

public interface IFolders
{
    /// <summary>ClipRoo's own settings and history.</summary>
    string Data { get; }

    /// <summary>Where pictures from the phone go (Pictures\ClipRoo).</summary>
    string Pictures { get; }

    /// <summary>Where files from the phone go (Downloads\ClipRoo).</summary>
    string Downloads { get; }
}

/// <summary>Keeps secrets on disk readable only by this Windows user (DPAPI on Windows).</summary>
public interface ISecretProtector
{
    byte[] Protect(byte[] data);
    byte[] Unprotect(byte[] data);
}
