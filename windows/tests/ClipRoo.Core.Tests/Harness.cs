using System.Net.Http.Headers;
using System.Net.Http.Json;
using ClipRoo.Core;
using ClipRoo.Core.Devices;
using ClipRoo.Core.Items;
using ClipRoo.Core.Pairing;
using ClipRoo.Core.Platform;
using ClipRoo.Core.Protocol;
using ClipRoo.Core.Security;
using ClipRoo.Core.Server;

namespace ClipRoo.Core.Tests;

// Stand-ins for Windows, and a real bridge (HTTPS, pinned certificate) on a free port.

sealed class FakeClipboard : IClipboard
{
    private ClipContent? _content;
    public long Sequence { get; private set; } = 1;
    public bool Busy { get; set; }
    public string? Text { get; private set; }
    public (PreparedPicture Picture, string Path)? Picture { get; private set; }
    public IReadOnlyList<string>? Files { get; private set; }

    public void Set(ClipContent? content)
    {
        _content = content;
        Sequence++;
    }

    public ClipContent? Read() => Busy ? throw new ClipboardBusyException() : _content;

    public void WriteText(string text)
    {
        if (Busy) throw new ClipboardBusyException();
        (Text, Picture, Files) = (text, null, null);
        Set(new ClipText(text));
    }

    public void WritePicture(PreparedPicture picture, string savedPath)
    {
        if (Busy) throw new ClipboardBusyException();
        (Text, Picture, Files) = (null, (picture, savedPath), null);
        Set(new ClipFiles([savedPath]));
    }

    public void WriteFiles(IReadOnlyList<string> paths)
    {
        if (Busy) throw new ClipboardBusyException();
        (Text, Picture, Files) = (null, null, paths);
        Set(new ClipFiles(paths));
    }
}

sealed class FakePictures : IPictures
{
    public string? Refuse { get; set; }

    public PreparedPicture Prepare(string path, PictureFormat format) =>
        Refuse is { } why ? throw new UnsupportedPictureException(why) : new PreparedPicture([1, 2, 3], format == PictureFormat.Png ? [9] : null, 640, 480);
}

sealed class FakeNotifier : INotifier
{
    public List<(string Title, string Message)> Shown { get; } = [];
    public void Notify(string title, string message) { lock (Shown) Shown.Add((title, message)); }
}

sealed class NoProtection : ISecretProtector
{
    public byte[] Protect(byte[] data) => [.. data.Reverse()];       // reversible, and not the plain bytes
    public byte[] Unprotect(byte[] data) => [.. data.Reverse()];
}

sealed class ManualTime : TimeProvider
{
    private DateTimeOffset _now = new(2026, 10, 22, 12, 0, 0, TimeSpan.Zero);
    public override DateTimeOffset GetUtcNow() => _now;
    public void Advance(TimeSpan by) => _now += by;
}

sealed class TempFolders : IFolders, IDisposable
{
    public string Root { get; } = Directory.CreateTempSubdirectory("cliproo-test-").FullName;
    public string Data => Path.Combine(Root, "data");
    public string Pictures => Path.Combine(Root, "Pictures");
    public string Downloads => Path.Combine(Root, "Downloads");
    public void Dispose() { try { Directory.Delete(Root, true); } catch (IOException) { } }
}

sealed class TestBridge : IAsyncDisposable
{
    public required TempFolders Folders { get; init; }
    public required ManualTime Time { get; init; }
    public required FakeClipboard Clipboard { get; init; }
    public required FakePictures Pictures { get; init; }
    public required FakeNotifier Notifier { get; init; }
    public required BridgeOptions Options { get; init; }
    public Identity Identity { get; private set; } = null!;
    public DeviceStore Devices { get; private set; } = null!;
    public ItemStore Items { get; private set; } = null!;
    public PairingCodes Codes { get; private set; } = null!;
    public Bridge Bridge { get; private set; } = null!;

    public static async Task<TestBridge> StartAsync(BridgeOptions? options = null)
    {
        var t = new TestBridge
        {
            Folders = new TempFolders(), Time = new ManualTime(), Clipboard = new FakeClipboard(),
            Pictures = new FakePictures(), Notifier = new FakeNotifier(), Options = options ?? new BridgeOptions { Port = 0 },
        };
        await t.OpenAsync();
        return t;
    }

    private async Task OpenAsync()
    {
        Identity = Identity.LoadOrCreate(Folders.Data, new NoProtection());
        Devices = new DeviceStore(Folders.Data, Time);
        Items = new ItemStore(Folders.Data, Time);
        Codes = new PairingCodes(Time);
        Bridge = new Bridge(Options, Identity, Devices, Items, Codes, Clipboard, Pictures, Notifier, Folders, Time) { PcName = "TEST-PC" };
        await Bridge.StartAsync();
    }

    /// <summary>Stops and starts again from the saved files (like restarting the PC).</summary>
    public async Task RestartAsync()
    {
        await Bridge.DisposeAsync();
        await OpenAsync();
    }

    public string Url(string path) => $"https://127.0.0.1:{Bridge.Port}{path}";

    public HttpClient Client(string? token = null, string? pin = null)
    {
        var expected = pin ?? Identity.Fingerprint;
        var handler = new HttpClientHandler
        {
            UseProxy = false,
            ServerCertificateCustomValidationCallback = (_, cert, _, _) => cert is not null && Identity.FingerprintOf(cert) == expected,
        };
        var http = new HttpClient(handler) { Timeout = TimeSpan.FromSeconds(20) };
        if (token is not null) http.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", token);
        return http;
    }

    public async Task<string> PairAsync(string phoneId = "phone-1", string name = "Test iPhone")
    {
        using var http = Client();
        var response = await http.PostAsJsonAsync(Url("/v1/pair"), new PairRequest(Codes.Current, phoneId, name, "ios", "1.0"), Json.Options);
        response.EnsureSuccessStatusCode();
        return (await response.Content.ReadFromJsonAsync<PairResponse>(Json.Options))!.Token;
    }

    public async ValueTask DisposeAsync()
    {
        await Bridge.DisposeAsync();
        Folders.Dispose();
    }
}
