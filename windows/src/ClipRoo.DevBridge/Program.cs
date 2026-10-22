using ClipRoo.Core;
using ClipRoo.Core.Devices;
using ClipRoo.Core.Items;
using ClipRoo.Core.Pairing;
using ClipRoo.Core.Platform;
using ClipRoo.Core.Security;
using ClipRoo.Core.Server;

// A stand-in PC for developing the iPhone app (on a Mac or anywhere .NET runs): the real
// bridge, with a pretend clipboard you type into. Run:  dotnet run --project src/ClipRoo.DevBridge
// Data goes in ~/.cliproo-dev (delete it to start over: new identity, phones pair again).

var home = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".cliproo-dev");
var folders = new DevFolders(home);
var clipboard = new DevClipboard();
var time = TimeProvider.System;
var identity = Identity.LoadOrCreate(folders.Data, new NoProtection());
var devices = new DeviceStore(folders.Data, time);
var items = new ItemStore(folders.Data, time);
var codes = new PairingCodes(time);
await using var bridge = new Bridge(new BridgeOptions(), identity, devices, items, codes, clipboard, new DevPictures(),
    new DevNotifier(), folders, time) { PcName = Environment.MachineName + " (dev)" };
await bridge.StartAsync();

void ShowPairing()
{
    Console.WriteLine();
    Console.WriteLine("Pairing link (valid 10 minutes, once):");
    Console.WriteLine("  " + PairingLink.Build(identity.PcId, bridge.PcName, Addresses.Candidates(bridge.Port, Environment.MachineName),
        identity.Fingerprint, codes.Current));
}

Console.WriteLine($"ClipRoo dev bridge on port {bridge.Port}. Fingerprint {identity.Fingerprint}");
Console.WriteLine("Type text and press Enter to 'copy' it on this pretend PC. Commands:");
Console.WriteLine("  /file <path>   copy a file     /pair   new pairing link     /phones   paired phones     /quit");
ShowPairing();
while (Console.ReadLine() is { } line)
{
    if (line == "/quit") break;
    if (line == "/pair") { ShowPairing(); continue; }
    if (line == "/phones") { foreach (var d in devices.All) Console.WriteLine($"  {d.Name} ({d.PhoneId}), last seen {d.LastSeen}"); continue; }
    if (line.StartsWith("/file ")) { clipboard.Set(new ClipFiles([line[6..].Trim()])); Console.WriteLine("  (copied a file)"); continue; }
    clipboard.Set(new ClipText(line));
    Console.WriteLine("  (copied)");
}

sealed class DevClipboard : IClipboard
{
    private ClipContent? _content;
    public long Sequence { get; private set; }
    public void Set(ClipContent content) { _content = content; Sequence++; }
    public ClipContent? Read() => _content;
    public void WriteText(string text) { Set(new ClipText(text)); Console.WriteLine($"[from phone] text: {text}"); }
    public void WritePicture(PreparedPicture picture, string savedPath) { Set(new ClipFiles([savedPath])); Console.WriteLine($"[from phone] picture: {savedPath}"); }
    public void WriteFiles(IReadOnlyList<string> paths) { Set(new ClipFiles(paths)); Console.WriteLine($"[from phone] files: {string.Join(", ", paths)}"); }
}

// Pictures aren't decoded here (that's the Windows app's job): anything recognised is accepted.
sealed class DevPictures : IPictures
{
    public PreparedPicture Prepare(string path, PictureFormat format) => new([], null, 0, 0);
}

sealed class DevNotifier : INotifier
{
    public void Notify(string title, string message) => Console.WriteLine($"[notification] {title}: {message}");
}

sealed class DevFolders(string home) : IFolders
{
    public string Data => Path.Combine(home, "data");
    public string Pictures => Path.Combine(home, "Pictures");
    public string Downloads => Path.Combine(home, "Downloads");
}

// Development only: the identity is stored unprotected in ~/.cliproo-dev.
sealed class NoProtection : ISecretProtector
{
    public byte[] Protect(byte[] data) => data;
    public byte[] Unprotect(byte[] data) => data;
}
