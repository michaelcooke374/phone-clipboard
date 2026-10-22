using System.Net;
using System.Net.Http.Json;
using ClipRoo.Core.Protocol;
using ClipRoo.Core.Server;
using Xunit;

namespace ClipRoo.Core.Tests;

/// <summary>What the phone sends to the PC.</summary>
public class ReceiveTests
{
    private static async Task<(TestBridge Bridge, HttpClient Http)> Ready(BridgeOptions? options = null)
    {
        var t = await TestBridge.StartAsync(options);
        return (t, t.Client(await t.PairAsync()));
    }

    private static HttpRequestMessage Upload(TestBridge t, byte[] body, string kind, string? name, string type = "application/octet-stream",
        string? group = null, int count = 0)
    {
        var request = new HttpRequestMessage(HttpMethod.Post, t.Url("/v1/items")) { Content = new ByteArrayContent(body) };
        request.Content.Headers.ContentType = new(type);
        request.Headers.Add("X-CR-Kind", kind);
        if (name is not null) request.Headers.Add("X-CR-Name", Uri.EscapeDataString(name));
        if (group is not null)
        {
            request.Headers.Add("X-CR-Group", group);
            request.Headers.Add("X-CR-Group-Count", count.ToString());
        }
        return request;
    }

    private static readonly byte[] Jpeg = [0xFF, 0xD8, 0xFF, 0xE0, 1, 2, 3, 4];

    [Fact]
    public async Task Text_goes_onto_the_clipboard_with_windows_line_endings()
    {
        var (t, http) = await Ready();
        await using var _ = t;
        var response = await http.PostAsJsonAsync(t.Url("/v1/items"), new TextToSend("text", "Hello\nfrom the iPhone \U0001F600"), Json.Options);
        Assert.Equal(HttpStatusCode.Created, response.StatusCode);
        var item = await response.Content.ReadFromJsonAsync<Item>(Json.Options);
        Assert.Equal((Kinds.Text, Origins.Phone), (item!.Kind, item.Origin));
        Assert.Equal("Sent to TEST-PC. Paste with Ctrl+V.", item.Message);
        Assert.Equal("Hello\r\nfrom the iPhone \U0001F600", t.Clipboard.Text);
        Assert.Equal(item.Id, t.Items.History()[0].Item.Id);
        Assert.Contains(t.Notifier.Shown, n => n.Title == "Text from Test iPhone");
    }

    [Fact]
    public async Task Empty_or_too_long_text()
    {
        var (t, http) = await Ready(new BridgeOptions { Port = 0, MaxTextBytes = 10 });
        await using var _ = t;
        Assert.Equal(HttpStatusCode.Conflict, (await http.PostAsJsonAsync(t.Url("/v1/items"), new TextToSend("text", ""), Json.Options)).StatusCode);
        Assert.Equal(HttpStatusCode.RequestEntityTooLarge,
            (await http.PostAsJsonAsync(t.Url("/v1/items"), new TextToSend("text", "eleven char"), Json.Options)).StatusCode);
        Assert.Null(t.Clipboard.Text);
    }

    [Fact]
    public async Task A_picture_is_saved_and_put_on_the_clipboard()
    {
        var (t, http) = await Ready();
        await using var _ = t;
        var response = await http.SendAsync(Upload(t, Jpeg, "image", "IMG_0042.heic", "image/jpeg"));
        Assert.Equal(HttpStatusCode.Created, response.StatusCode);
        var item = await response.Content.ReadFromJsonAsync<Item>(Json.Options);
        Assert.Equal((Kinds.Image, "image/jpeg", 640, 480), (item!.Kind, item.Type, item.Width, item.Height));
        var saved = Path.Combine(t.Folders.Pictures, "ClipRoo", "IMG_0042.jpg");       // named for what it really is
        Assert.Equal(Jpeg, await File.ReadAllBytesAsync(saved));
        Assert.Equal(saved, t.Clipboard.Picture!.Value.Path);
        Assert.Contains(t.Notifier.Shown, n => n.Title == "Picture from Test iPhone");
        Assert.Empty(Directory.GetFiles(Path.Combine(t.Folders.Pictures, "ClipRoo"), "*.part"));

        await http.SendAsync(Upload(t, Jpeg, "image", "IMG_0042.jpg", "image/jpeg"));
        Assert.True(File.Exists(Path.Combine(t.Folders.Pictures, "ClipRoo", "IMG_0042 (2).jpg")));
    }

    [Fact]
    public async Task HEIC_unknown_and_unreadable_pictures_are_refused()
    {
        var (t, http) = await Ready();
        await using var _ = t;
        byte[] heic = [0, 0, 0, 0x18, (byte)'f', (byte)'t', (byte)'y', (byte)'p', (byte)'h', (byte)'e', (byte)'i', (byte)'c', 0, 0];
        var response = await http.SendAsync(Upload(t, heic, "image", "a.heic", "image/heic"));
        Assert.Equal(HttpStatusCode.UnsupportedMediaType, response.StatusCode);
        Assert.Contains("HEIC", (await response.Content.ReadFromJsonAsync<ErrorBody>(Json.Options))!.Message);
        Assert.Equal(HttpStatusCode.UnsupportedMediaType, (await http.SendAsync(Upload(t, "not a picture"u8.ToArray(), "image", "a.jpg"))).StatusCode);
        t.Pictures.Refuse = "Damaged picture.";
        Assert.Equal(HttpStatusCode.UnsupportedMediaType, (await http.SendAsync(Upload(t, Jpeg, "image", "a.jpg"))).StatusCode);
        Assert.Empty(Directory.GetFiles(Path.Combine(t.Folders.Pictures, "ClipRoo")));
        Assert.Null(t.Clipboard.Picture);
    }

    [Fact]
    public async Task A_file_is_saved_under_a_safe_name()
    {
        var (t, http) = await Ready();
        await using var _ = t;
        var response = await http.SendAsync(Upload(t, "data"u8.ToArray(), "file", "../../evil:name?.txt"));
        Assert.Equal(HttpStatusCode.Created, response.StatusCode);
        var saved = Path.Combine(t.Folders.Downloads, "ClipRoo", "evilname.txt");
        Assert.Equal("data", await File.ReadAllTextAsync(saved));
        Assert.Equal([saved], t.Clipboard.Files!);
        var item = await response.Content.ReadFromJsonAsync<Item>(Json.Options);
        Assert.Equal([new ItemFile("evilname.txt", 4, "text/plain")], item!.Files!);
    }

    [Fact]
    public async Task Files_sent_together_go_onto_the_clipboard_together()
    {
        var (t, http) = await Ready();
        await using var _ = t;
        var first = await http.SendAsync(Upload(t, "one"u8.ToArray(), "file", "a.txt", group: "G", count: 2));
        Assert.Equal("Received 1 of 2 files.", (await first.Content.ReadFromJsonAsync<Item>(Json.Options))!.Message);
        Assert.Null(t.Clipboard.Files);
        var second = await http.SendAsync(Upload(t, "two"u8.ToArray(), "file", "b.txt", group: "G", count: 2));
        var item = await second.Content.ReadFromJsonAsync<Item>(Json.Options);
        Assert.Equal(2, t.Clipboard.Files!.Count);
        Assert.Equal(["a.txt", "b.txt"], item!.Files!.Select(f => f.Name));
        Assert.Single(t.Items.History(), h => h.Item.Kind == Kinds.Files);
    }

    [Fact]
    public async Task Bad_uploads()
    {
        var (t, http) = await Ready(new BridgeOptions { Port = 0, MaxFileBytes = 5, MaxPictureBytes = 5 });
        await using var _ = t;
        var noKind = new HttpRequestMessage(HttpMethod.Post, t.Url("/v1/items")) { Content = new ByteArrayContent([1, 2]) };
        Assert.Equal(HttpStatusCode.BadRequest, (await http.SendAsync(noKind)).StatusCode);
        Assert.Equal(HttpStatusCode.RequestEntityTooLarge, (await http.SendAsync(Upload(t, new byte[6], "file", "big.bin"))).StatusCode);
        var chunked = Upload(t, [1, 2], "file", "x.bin");
        chunked.Headers.TransferEncodingChunked = true;
        Assert.Equal(HttpStatusCode.BadRequest, (await http.SendAsync(chunked)).StatusCode);
    }

    [Fact]
    public async Task Outbox_and_history()
    {
        var (t, http) = await Ready();
        await using var _ = t;
        var sent = Items.ItemStore.TextItem("OUT1", Origins.Pc, "for the phone", t.Items.Now());
        t.Items.AddToOutbox(sent);
        var outbox = await http.GetFromJsonAsync<List<Item>>(t.Url("/v1/outbox"), Json.Options);
        Assert.Equal("OUT1", Assert.Single(outbox!).Id);
        Assert.Equal(HttpStatusCode.OK, (await http.PostAsync(t.Url("/v1/outbox/OUT1/done"), null)).StatusCode);
        Assert.Empty((await http.GetFromJsonAsync<List<Item>>(t.Url("/v1/outbox"), Json.Options))!);
        Assert.Equal(HttpStatusCode.NotFound, (await http.PostAsync(t.Url("/v1/outbox/OUT1/done"), null)).StatusCode);

        for (var i = 0; i < 4; i++)
            await http.PostAsJsonAsync(t.Url("/v1/items"), new TextToSend("text", $"text {i}"), Json.Options);
        var page = await http.GetFromJsonAsync<List<Item>>(t.Url("/v1/history?limit=2"), Json.Options);
        Assert.Equal(["text 3", "text 2"], page!.Select(i => i.Text));
        var next = (await http.GetFromJsonAsync<List<Item>>(t.Url($"/v1/history?limit=2&before={page![1].Id}"), Json.Options))!;
        Assert.Equal(["text 1", "text 0"], next.Select(i => i.Text));
        var last = await http.GetFromJsonAsync<List<Item>>(t.Url($"/v1/history?before={next[1].Id}"), Json.Options);
        Assert.Equal("OUT1", Assert.Single(last!).Id);
    }
}
