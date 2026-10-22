using System.Collections.Concurrent;
using System.Net;
using System.Security.Authentication;
using System.Text;
using System.Text.Json;
using ClipRoo.Core.Devices;
using ClipRoo.Core.Items;
using ClipRoo.Core.Pairing;
using ClipRoo.Core.Platform;
using ClipRoo.Core.Protocol;
using ClipRoo.Core.Security;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Hosting.Server.Features;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Server.Kestrel.Core;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace ClipRoo.Core.Server;

public sealed class BridgeOptions
{
    public long MaxTextBytes { get; init; } = 16L * 1024 * 1024;
    public long MaxPictureBytes { get; init; } = 200L * 1024 * 1024;
    public long MaxFileBytes { get; init; } = 4L * 1024 * 1024 * 1024;

    /// <summary>A fixed port (0: any free one, for tests). Null: the first free of 47820 to 47829.</summary>
    public int? Port { get; init; }
}

/// <summary>The bridge: ClipRoo's HTTPS server on the PC (docs/PROTOCOL.md).</summary>
public sealed class Bridge : IAsyncDisposable
{
    private const int PairTriesPerMinute = 10;
    private const int FailedTokensPerMinute = 30;
    private static readonly TimeSpan GroupWait = TimeSpan.FromMinutes(10);

    private readonly BridgeOptions _options;
    private readonly Identity _identity;
    private readonly DeviceStore _devices;
    private readonly ItemStore _items;
    private readonly PairingCodes _codes;
    private readonly IClipboard _clipboard;
    private readonly IPictures _pictures;
    private readonly INotifier _notifier;
    private readonly IFolders _folders;
    private readonly ILogger _log;
    private readonly RateLimiter _pairLimit;
    private readonly RateLimiter _tokenLimit;
    private readonly Lock _clipLock = new();
    private (long Sequence, StoredItem? Item, bool InHistory)? _clip;
    private readonly ConcurrentDictionary<string, Group> _groups = new();
    private WebApplication? _app;

    public Bridge(BridgeOptions options, Identity identity, DeviceStore devices, ItemStore items, PairingCodes codes,
        IClipboard clipboard, IPictures pictures, INotifier notifier, IFolders folders, TimeProvider time,
        ILogger? log = null)
    {
        _options = options;
        _identity = identity;
        _devices = devices;
        _items = items;
        _codes = codes;
        _clipboard = clipboard;
        _pictures = pictures;
        _notifier = notifier;
        _folders = folders;
        _log = log ?? NullLogger.Instance;
        _pairLimit = new RateLimiter(PairTriesPerMinute, time);
        _tokenLimit = new RateLimiter(FailedTokensPerMinute, time);
    }

    /// <summary>The name phones see. The Windows app sets it from its settings.</summary>
    public string PcName { get; set; } = Environment.MachineName;

    /// <summary>The port in use, once started.</summary>
    public int Port { get; private set; }

    public async Task StartAsync(CancellationToken cancel = default)
    {
        if (_options.Port is { } fixedPort)
        {
            await StartOnAsync(fixedPort, cancel);
            return;
        }
        for (var port = Product.FirstPort; ; port++)
        {
            try
            {
                await StartOnAsync(port, cancel);
                return;
            }
            catch (IOException) when (port < Product.LastPort)
            {
                _log.LogInformation("Port {Port} is in use; trying the next", port);
            }
        }
    }

    private async Task StartOnAsync(int port, CancellationToken cancel)
    {
        var builder = WebApplication.CreateSlimBuilder();
        builder.Logging.ClearProviders();
        builder.WebHost.ConfigureKestrel(k =>
        {
            k.AddServerHeader = false;
            k.Limits.MaxRequestBodySize = _options.MaxFileBytes + 1024 * 1024;
            // Every network of the PC, IPv6 and IPv4 (IPv4 alone where IPv6 is switched off).
            k.ListenAnyIP(port, listen =>
            {
                listen.Protocols = HttpProtocols.Http1AndHttp2;
                listen.UseHttps(https =>
                {
                    https.ServerCertificate = _identity.Certificate;
                    https.SslProtocols = SslProtocols.Tls12 | SslProtocols.Tls13;
                });
            });
        });
        var app = builder.Build();
        Map(app);
        try
        {
            await app.StartAsync(cancel);
        }
        catch
        {
            await app.DisposeAsync();
            throw;
        }
        _app = app;
        var address = app.Services.GetRequiredService<IServer>().Features.Get<IServerAddressesFeature>()!.Addresses.First();
        Port = new Uri(address.Replace("[::]", "localhost").Replace("0.0.0.0", "localhost")).Port;
        _log.LogInformation("Listening on port {Port}", Port);
    }

    public async ValueTask DisposeAsync()
    {
        if (_app is not null)
        {
            await _app.StopAsync();
            await _app.DisposeAsync();
            _app = null;
        }
    }

    // ---- the requests --------------------------------------------------------------------------

    private void Map(WebApplication app)
    {
        app.MapGet("/v1/hello", () => Ok(new Hello(Product.AppId, [Product.ProtocolVersion], _identity.PcId, PcName)));
        app.MapPost("/v1/pair", (Func<HttpContext, Task<IResult>>)Pair);
        app.MapGet("/v1/clipboard", (HttpContext c) => Authed(c, _ => GetClipboard()));
        app.MapGet("/v1/items/{id}/content", (HttpContext c, string id) => Authed(c, _ => GetContent(id)));
        app.MapGet("/v1/items/{id}/files/{index:int}", (HttpContext c, string id, int index) => Authed(c, _ => GetFile(id, index)));
        app.MapPost("/v1/items", (Func<HttpContext, Task<IResult>>)(c => AuthedAsync(c, device => Receive(c, device))));
        app.MapGet("/v1/outbox", (HttpContext c) => Authed(c, _ => Ok(_items.Outbox().Select(i => i.Item).ToList())));
        app.MapPost("/v1/outbox/{id}/done", (HttpContext c, string id) =>
            Authed(c, _ => _items.Done(id) ? Ok(new { ok = true }) : Error(404, "not_found", "That isn't waiting any more.")));
        app.MapGet("/v1/history", (HttpContext c, string? before, int? limit) =>
            Authed(c, _ => Ok(_items.History(before, limit ?? 50).Select(i => i.Item).ToList())));
        app.MapDelete("/v1/devices/me", (HttpContext c) => Authed(c, device =>
        {
            _devices.Remove(device.PhoneId);
            _log.LogInformation("{Phone} unpaired itself", device.Name);
            return Ok(new { ok = true });
        }));
        app.MapFallback(() => Error(404, "not_found", "There's nothing at that address."));
    }

    private async Task<IResult> Pair(HttpContext c)
    {
        var address = AddressOf(c);
        if (_pairLimit.IsBlocked(address))
            return Error(429, "too_many_requests", "Too many tries. Wait a minute, then scan the code again.");
        _pairLimit.Count(address);
        var body = await ReadJsonAsync<PairRequest>(c, 16 * 1024);
        if (body is null || string.IsNullOrWhiteSpace(body.PhoneId) || string.IsNullOrWhiteSpace(body.Code))
            return Error(400, "bad_request", "The pairing request is incomplete.");
        if (!_codes.TryUse(body.Code))
        {
            _log.LogInformation("Refused a pairing code from {Address}", address);
            return Error(403, "pairing_code_invalid", "That code is old or wrong. Show the code on the PC again and scan it.");
        }
        var name = Shorten(string.IsNullOrWhiteSpace(body.PhoneName) ? "iPhone" : body.PhoneName.Trim(), 64);
        var token = _devices.Pair(Shorten(body.PhoneId.Trim(), 64), name, Shorten(body.Platform ?? "ios", 16), Shorten(body.AppVersion ?? "", 32));
        _log.LogInformation("Paired {Phone} from {Address}", name, address);
        _notifier.Notify($"{name} is paired", $"It can now copy and paste with {PcName}.");
        return Ok(new PairResponse(token, _identity.PcId, PcName, Product.ProtocolVersion));
    }

    private IResult GetClipboard()
    {
        StoredItem? item;
        try
        {
            item = CurrentClipboard(recordInHistory: true);
        }
        catch (ClipboardBusyException)
        {
            return Busy();
        }
        return item is null ? Results.NoContent() : Ok(item.Item);
    }

    private IResult GetContent(string id)
    {
        var item = Lookup(id);
        if (item is null) return Error(404, "not_found", "That item isn't here any more.");
        switch (item.Item.Kind)
        {
            case Kinds.Text:
                var text = item.FullText ?? item.Item.Text ?? "";
                return Results.Bytes(Encoding.UTF8.GetBytes(text), "text/plain; charset=utf-8");
            case Kinds.Image when item.Data is not null:
                return Results.Bytes(item.Data, item.Item.Type ?? "image/png");
            case Kinds.Image when item.Paths.Count > 0 && File.Exists(item.Paths[0]):
                return Results.File(item.Paths[0], item.Item.Type ?? "application/octet-stream", enableRangeProcessing: true);
            default:
                return Error(404, "not_found", "That item's content isn't here any more.");
        }
    }

    private IResult GetFile(string id, int index)
    {
        var item = Lookup(id);
        if (item is null || item.Item.Files is not { } files || index < 0 || index >= files.Count
            || index >= item.Paths.Count || !File.Exists(item.Paths[index]))
            return Error(404, "not_found", "That file isn't here any more.");
        return Results.File(item.Paths[index], files[index].Type, fileDownloadName: files[index].Name, enableRangeProcessing: true);
    }

    private StoredItem? Lookup(string id)
    {
        lock (_clipLock)
        {
            if (_clip is { Item: { } current } && current.Item.Id == id) return current;
        }
        return _items.Find(id);
    }

    /// <summary>What's copied on the PC, as an item. The same item (same id) until something else is copied.</summary>
    internal StoredItem? CurrentClipboard(bool recordInHistory)
    {
        StoredItem? item;
        lock (_clipLock)
        {
            var sequence = _clipboard.Sequence;
            if (_clip is not { } cached || cached.Sequence != sequence)
            {
                _clip = (sequence, ToItem(_clipboard.Read()), false);
            }
            item = _clip.Value.Item;
            if (!recordInHistory || item is null || _clip.Value.InHistory) return item;
            _clip = _clip.Value with { InHistory = true };
        }
        _items.AddHistory(item);
        return item;
    }

    private StoredItem? ToItem(ClipContent? content)
    {
        var now = _items.Now();
        switch (content)
        {
            case ClipText { Text.Length: > 0 } t:
                return ItemStore.TextItem(Ids.New(), Origins.Pc, t.Text.ReplaceLineEndings("\n"), now);
            case ClipPicture p:
                return new StoredItem
                {
                    Item = new Item
                    {
                        Id = Ids.New(), Origin = Origins.Pc, Kind = Kinds.Image, Created = now, Size = p.Data.Length,
                        Type = p.Type, Width = p.Width, Height = p.Height,
                    },
                    Data = p.Data,
                };
            case ClipFiles f:
                var paths = f.Paths.Where(File.Exists).ToList();      // folders aren't sent (yet)
                if (paths.Count == 0) return null;
                if (paths.Count == 1 && PictureFormats.FromExtension(paths[0]) != PictureFormat.Unknown)
                {
                    var format = PictureFormats.FromExtension(paths[0]);
                    return new StoredItem
                    {
                        Item = new Item
                        {
                            Id = Ids.New(), Origin = Origins.Pc, Kind = Kinds.Image, Created = now,
                            Size = new FileInfo(paths[0]).Length, Type = PictureFormats.MimeType(format),
                        },
                        Paths = paths,
                    };
                }
                return FilesItem(Ids.New(), Origins.Pc, paths, now);
            default:
                return null;
        }
    }

    private static StoredItem FilesItem(string id, string origin, IReadOnlyList<string> paths, DateTime created)
    {
        var files = paths.Select(p => new ItemFile(Path.GetFileName(p), new FileInfo(p).Length, FileNames.TypeOf(p))).ToList();
        return new StoredItem
        {
            Item = new Item
            {
                Id = id, Origin = origin, Kind = Kinds.Files, Created = created, Size = files.Sum(f => f.Size), Files = files,
            },
            Paths = paths,
        };
    }

    // ---- receiving from the phone ----------------------------------------------------------------

    private async Task<IResult> Receive(HttpContext c, Device device)
    {
        var contentType = c.Request.ContentType ?? "";
        if (contentType.StartsWith("application/json", StringComparison.OrdinalIgnoreCase))
            return await ReceiveText(c, device);
        var kind = c.Request.Headers["X-CR-Kind"].ToString();
        if (kind is not ("image" or "file"))
            return Error(400, "bad_request", "Say what's being sent: X-CR-Kind is image or file.");
        if (c.Request.ContentLength is not { } length)
            return Error(400, "bad_request", "Content-Length is required.");
        var limit = kind == "image" ? _options.MaxPictureBytes : _options.MaxFileBytes;
        if (length > limit)
            return Error(413, "too_large", kind == "image" ? "That picture is too big to send." : "That file is too big to send.");
        var name = Uri.UnescapeDataString(c.Request.Headers["X-CR-Name"].ToString());
        return kind == "image"
            ? await ReceivePicture(c, device, name, length)
            : await ReceiveFile(c, device, name, length);
    }

    private async Task<IResult> ReceiveText(HttpContext c, Device device)
    {
        var body = await ReadJsonAsync<TextToSend>(c, _options.MaxTextBytes + 64 * 1024);
        if (body is null) return Error(413, "too_large", "That text is too long to send, or it couldn't be read.");
        if (body.Kind is not (null or Kinds.Text)) return Error(400, "bad_request", "JSON is only used for text.");
        if (string.IsNullOrEmpty(body.Text)) return Error(409, "nothing_to_send", "There's no text to send.");
        if (Encoding.UTF8.GetByteCount(body.Text) > _options.MaxTextBytes) return Error(413, "too_large", "That text is too long to send.");
        var text = body.Text.ReplaceLineEndings("\n");
        try
        {
            _clipboard.WriteText(text.Replace("\n", "\r\n"));
        }
        catch (ClipboardBusyException)
        {
            return Busy();
        }
        var item = ItemStore.TextItem(Ids.New(), Origins.Phone, text, _items.Now());
        _items.AddHistory(item);
        _log.LogInformation("Text ({Count} characters) from {Phone}", text.Length, device.Name);
        _notifier.Notify($"Text from {device.Name}", "Press Ctrl+V to paste it.");
        return Created(item.Item with { Message = $"Sent to {PcName}. Paste with Ctrl+V." });
    }

    private async Task<IResult> ReceivePicture(HttpContext c, Device device, string name, long length)
    {
        var folder = Path.Combine(_folders.Pictures, Product.FolderName);
        var part = await SaveBodyAsync(c, folder, length);
        if (part is null) return Error(400, "bad_request", "The picture didn't arrive completely. Try again.");
        var format = Detect(part);
        if (format is PictureFormat.Heic or PictureFormat.Unknown)
        {
            File.Delete(part);
            return Error(415, "unsupported", format == PictureFormat.Heic
                ? "This photo is in Apple's HEIC format, which Windows can't paste. Send it as JPEG."
                : "That isn't a picture the computer can open (JPEG, PNG, GIF, WebP or BMP).");
        }
        var stem = Path.GetFileNameWithoutExtension(FileNames.Clean(name, ""));
        if (stem.Length == 0) stem = $"{device.Name} {DateTime.Now:yyyy-MM-dd HH.mm.ss}";
        var path = MoveToUnique(part, folder, FileNames.Clean(stem + PictureFormats.Extension(format), "Picture" + PictureFormats.Extension(format)));
        PreparedPicture prepared;
        try
        {
            prepared = _pictures.Prepare(path, format);
        }
        catch (UnsupportedPictureException e)
        {
            File.Delete(path);
            return Error(415, "unsupported", e.Message);
        }
        try
        {
            _clipboard.WritePicture(prepared, path);
        }
        catch (ClipboardBusyException)
        {
            return Error(503, "clipboard_busy", $"Another program is using the clipboard. The picture is saved in Pictures > {Product.FolderName}.");
        }
        var item = new StoredItem
        {
            Item = new Item
            {
                Id = Ids.New(), Origin = Origins.Phone, Kind = Kinds.Image, Created = _items.Now(), Size = length,
                Type = PictureFormats.MimeType(format), Width = prepared.Width, Height = prepared.Height,
            },
            Paths = [path],
        };
        _items.AddHistory(item);
        _log.LogInformation("A picture ({Width} x {Height}, {Kb} KB) from {Phone}", prepared.Width, prepared.Height, length / 1024, device.Name);
        _notifier.Notify($"Picture from {device.Name}", "Press Ctrl+V to paste it.");
        return Created(item.Item with { Message = $"Sent to {PcName}. Paste with Ctrl+V." });
    }

    private async Task<IResult> ReceiveFile(HttpContext c, Device device, string name, long length)
    {
        var folder = Path.Combine(_folders.Downloads, Product.FolderName);
        var groupId = c.Request.Headers["X-CR-Group"].ToString();
        int.TryParse(c.Request.Headers["X-CR-Group-Count"].ToString(), out var groupCount);
        var part = await SaveBodyAsync(c, folder, length);
        if (part is null) return Error(400, "bad_request", "The file didn't arrive completely. Try again.");
        var path = MoveToUnique(part, folder, FileNames.Clean(name, "File"));

        IReadOnlyList<string> paths = [path];
        var complete = true;
        string itemId;
        if (groupId.Length > 0 && groupCount > 1)
        {
            DropOldGroups();
            var group = _groups.GetOrAdd(groupId, _ => new Group(Ids.New(), DateTimeOffset.UtcNow));
            lock (group)
            {
                group.Paths.Add(path);
                paths = group.Paths.ToList();
            }
            itemId = group.ItemId;
            complete = paths.Count >= groupCount;
            if (complete) _groups.TryRemove(groupId, out _);
        }
        else
        {
            itemId = Ids.New();
        }
        var item = FilesItem(itemId, Origins.Phone, paths, _items.Now());
        if (!complete)
            return Created(item.Item with { Message = $"Received {paths.Count} of {groupCount} files." });
        try
        {
            _clipboard.WriteFiles(paths);
        }
        catch (ClipboardBusyException)
        {
            return Error(503, "clipboard_busy", $"Another program is using the clipboard. The files are saved in Downloads > {Product.FolderName}.");
        }
        _items.AddHistory(item);
        var what = paths.Count == 1 ? "A file" : $"{paths.Count} files";
        _log.LogInformation("{What} from {Phone}", what, device.Name);
        _notifier.Notify($"{what} from {device.Name}", "Press Ctrl+V to paste in a folder, an email or a chat.");
        return Created(item.Item with { Message = $"Sent to {PcName}. Paste with Ctrl+V." });
    }

    /// <summary>Saves the request body to a temporary file in <paramref name="folder"/>. Null if it ended early.</summary>
    private static async Task<string?> SaveBodyAsync(HttpContext c, string folder, long length)
    {
        Directory.CreateDirectory(folder);
        var part = Path.Combine(folder, $".{Ids.New()}.part");
        long total = 0;
        try
        {
            await using (var file = new FileStream(part, FileMode.CreateNew, FileAccess.Write, FileShare.None, 1 << 16, useAsync: true))
            {
                var buffer = new byte[1 << 16];
                int read;
                while ((read = await c.Request.Body.ReadAsync(buffer, c.RequestAborted)) > 0)
                {
                    total += read;
                    if (total > length) break;
                    await file.WriteAsync(buffer.AsMemory(0, read), c.RequestAborted);
                }
            }
        }
        catch (Exception e) when (e is IOException or OperationCanceledException or Microsoft.AspNetCore.Http.BadHttpRequestException)
        {
            total = -1;
        }
        if (total == length) return part;
        File.Delete(part);
        return null;
    }

    /// <summary>Gives the received file its name, never overwriting (two arrivals can pick the same name).</summary>
    private static string MoveToUnique(string part, string folder, string name)
    {
        for (var tries = 0; ; tries++)
        {
            var path = FileNames.Unique(folder, name);
            try
            {
                File.Move(part, path);
                return path;
            }
            catch (IOException) when (tries < 20 && File.Exists(path))
            {
            }
        }
    }

    private static PictureFormat Detect(string path)
    {
        var head = new byte[32];
        using var file = File.OpenRead(path);
        var read = file.Read(head);
        return PictureFormats.Detect(head.AsSpan(0, read));
    }

    private void DropOldGroups()
    {
        foreach (var (id, group) in _groups)
            if (DateTimeOffset.UtcNow - group.Started > GroupWait) _groups.TryRemove(id, out _);
    }

    private sealed record Group(string ItemId, DateTimeOffset Started)
    {
        public List<string> Paths { get; } = [];
    }

    // ---- helpers -------------------------------------------------------------------------------------

    private IResult Authed(HttpContext c, Func<Device, IResult> handle) =>
        Authenticate(c, out var failure) is { } device ? handle(device) : failure!;

    private async Task<IResult> AuthedAsync(HttpContext c, Func<Device, Task<IResult>> handle) =>
        Authenticate(c, out var failure) is { } device ? await handle(device) : failure!;

    private Device? Authenticate(HttpContext c, out IResult? failure)
    {
        var address = AddressOf(c);
        if (_tokenLimit.IsBlocked(address))
        {
            failure = Error(429, "too_many_requests", "Too many tries. Wait a minute.");
            return null;
        }
        var header = c.Request.Headers.Authorization.ToString();
        var token = header.StartsWith("Bearer ", StringComparison.Ordinal) ? header[7..].Trim() : null;
        var device = _devices.Verify(token);
        if (device is null)
        {
            _tokenLimit.Count(address);
            _log.LogInformation("Refused a request without a valid token from {Address}", address);
            failure = Error(401, "unauthorized", $"This iPhone isn't paired with {PcName} any more. Pair it again from the PC.");
            return null;
        }
        failure = null;
        return device;
    }

    private static string AddressOf(HttpContext c)
    {
        var ip = c.Connection.RemoteIpAddress;
        if (ip is null) return "?";
        return (ip.IsIPv4MappedToIPv6 ? ip.MapToIPv4() : ip).ToString();
    }

    private static async Task<T?> ReadJsonAsync<T>(HttpContext c, long maxBytes) where T : class
    {
        if (c.Request.ContentLength > maxBytes) return null;
        using var buffer = new MemoryStream();
        var chunk = new byte[16 * 1024];
        int read;
        try
        {
            while ((read = await c.Request.Body.ReadAsync(chunk, c.RequestAborted)) > 0)
            {
                if (buffer.Length + read > maxBytes) return null;
                buffer.Write(chunk, 0, read);
            }
            return JsonSerializer.Deserialize<T>(buffer.GetBuffer().AsSpan(0, (int)buffer.Length), Json.Options);
        }
        catch (Exception e) when (e is JsonException or IOException or Microsoft.AspNetCore.Http.BadHttpRequestException)
        {
            return null;
        }
    }

    private static string Shorten(string text, int max) => text.Length > max ? text[..max] : text;

    private static IResult Ok<T>(T value) => Results.Json(value, Json.Options);

    private static IResult Created(Item item) => Results.Json(item, Json.Options, statusCode: 201);

    private static IResult Busy() => Error(503, "clipboard_busy", "Another program is using the clipboard. Try again in a moment.");

    private static IResult Error(int status, string code, string message) =>
        Results.Json(new ErrorBody(code, message), Json.Options, statusCode: status);
}
