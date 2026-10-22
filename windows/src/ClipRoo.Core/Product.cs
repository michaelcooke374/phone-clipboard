namespace ClipRoo.Core;

/// <summary>Names and numbers that identify ClipRoo on the network (docs/PROTOCOL.md).</summary>
public static class Product
{
    public const string Name = "ClipRoo";

    /// <summary>The "app" value in hello answers.</summary>
    public const string AppId = "cliproo";

    /// <summary>The DNS-SD service type the bridge announces.</summary>
    public const string ServiceType = "_cliproo._tcp";

    public const int ProtocolVersion = 1;

    /// <summary>The bridge listens on the first free port of these.</summary>
    public const int FirstPort = 47820;
    public const int LastPort = 47829;

    /// <summary>Pairing links: the details follow after "#", so they never reach the website.</summary>
    public const string PairLinkBase = "https://cliproo.app/pair";

    /// <summary>The folder name inside Pictures and Downloads.</summary>
    public const string FolderName = "ClipRoo";
}
