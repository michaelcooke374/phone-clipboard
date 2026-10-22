using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using ClipRoo.Core.Platform;
using ClipRoo.Core.Protocol;
using Xunit;

namespace ClipRoo.Core.Tests;

/// <summary>The PC's clipboard, as the phone gets it.</summary>
public class ClipboardTests
{
    private static async Task<(TestBridge Bridge, HttpClient Http)> Ready()
    {
        var t = await TestBridge.StartAsync();
        return (t, t.Client(await t.PairAsync()));
    }

    [Fact]
    public async Task Text_with_phone_line_endings_and_a_steady_id()
    {
        var (t, http) = await Ready();
        await using var _ = t;
        t.Clipboard.Set(new ClipText("line 1\r\nline 2 \u2713"));
        var item = await http.GetFromJsonAsync<Item>(t.Url("/v1/clipboard"), Json.Options);
        Assert.Equal((Kinds.Text, Origins.Pc, "line 1\nline 2 \u2713"), (item!.Kind, item.Origin, item.Text));
        Assert.Equal("line 1\nline 2 \u2713", await http.GetStringAsync(t.Url($"/v1/items/{item.Id}/content")));
        var again = await http.GetFromJsonAsync<Item>(t.Url("/v1/clipboard"), Json.Options);
        Assert.Equal(item.Id, again!.Id);
        Assert.Single(t.Items.History(), h => h.Item.Id == item.Id);

        t.Clipboard.Set(new ClipText("something else"));
        var next = await http.GetFromJsonAsync<Item>(t.Url("/v1/clipboard"), Json.Options);
        Assert.NotEqual(item.Id, next!.Id);
        var raw = await http.GetStringAsync(t.Url("/v1/clipboard"));
        Assert.Matches("\"created\":\"\\d{4}-\\d\\d-\\d\\dT\\d\\d:\\d\\d:\\d\\dZ\"", raw);
    }

    [Fact]
    public async Task Long_text_comes_through_the_content_address()
    {
        var (t, http) = await Ready();
        await using var _ = t;
        var text = new string('x', 70_000);
        t.Clipboard.Set(new ClipText(text));
        var item = await http.GetFromJsonAsync<Item>(t.Url("/v1/clipboard"), Json.Options);
        Assert.Null(item!.Text);
        Assert.Equal(70_000, item.Size);
        Assert.Equal(text, await http.GetStringAsync(t.Url($"/v1/items/{item.Id}/content")));
    }

    [Fact]
    public async Task A_copied_picture()
    {
        var (t, http) = await Ready();
        await using var _ = t;
        byte[] png = [0x89, (byte)'P', (byte)'N', (byte)'G', 1, 2, 3];
        t.Clipboard.Set(new ClipPicture(png, "image/png", 1920, 1080));
        var item = await http.GetFromJsonAsync<Item>(t.Url("/v1/clipboard"), Json.Options);
        Assert.Equal((Kinds.Image, "image/png", 1920, 1080, 7L), (item!.Kind, item.Type, item.Width, item.Height, item.Size));
        var content = await http.GetAsync(t.Url($"/v1/items/{item.Id}/content"));
        Assert.Equal("image/png", content.Content.Headers.ContentType!.MediaType);
        Assert.Equal(png, await content.Content.ReadAsByteArrayAsync());
    }

    [Fact]
    public async Task One_copied_picture_file_is_sent_as_it_is()
    {
        var (t, http) = await Ready();
        await using var _ = t;
        var photo = Path.Combine(t.Folders.Root, "photo.JPG");
        await File.WriteAllBytesAsync(photo, [0xFF, 0xD8, 0xFF, 0xE0, 5, 6]);
        t.Clipboard.Set(new ClipFiles([photo]));
        var item = await http.GetFromJsonAsync<Item>(t.Url("/v1/clipboard"), Json.Options);
        Assert.Equal((Kinds.Image, "image/jpeg", 6L), (item!.Kind, item.Type, item.Size));
        Assert.Equal(await File.ReadAllBytesAsync(photo), await http.GetByteArrayAsync(t.Url($"/v1/items/{item.Id}/content")));
    }

    [Fact]
    public async Task Copied_files_with_names_and_resumable_downloads()
    {
        var (t, http) = await Ready();
        await using var _ = t;
        var a = Path.Combine(t.Folders.Root, "Report é.pdf");
        var b = Path.Combine(t.Folders.Root, "notes.txt");
        await File.WriteAllTextAsync(a, "0123456789");
        await File.WriteAllTextAsync(b, "hi");
        var folder = Directory.CreateDirectory(Path.Combine(t.Folders.Root, "a folder")).FullName;
        t.Clipboard.Set(new ClipFiles([a, folder, b]));
        var item = await http.GetFromJsonAsync<Item>(t.Url("/v1/clipboard"), Json.Options);
        Assert.Equal(Kinds.Files, item!.Kind);
        Assert.Equal([new ItemFile("Report é.pdf", 10, "application/pdf"), new ItemFile("notes.txt", 2, "text/plain")], item.Files!);

        var whole = await http.GetAsync(t.Url($"/v1/items/{item.Id}/files/0"));
        Assert.Equal("0123456789", await whole.Content.ReadAsStringAsync());
        Assert.Equal("Report é.pdf", whole.Content.Headers.ContentDisposition!.FileNameStar);

        var request = new HttpRequestMessage(HttpMethod.Get, t.Url($"/v1/items/{item.Id}/files/0"));
        request.Headers.Range = new RangeHeaderValue(4, null);
        var rest = await http.SendAsync(request);
        Assert.Equal(HttpStatusCode.PartialContent, rest.StatusCode);
        Assert.Equal("456789", await rest.Content.ReadAsStringAsync());

        Assert.Equal(HttpStatusCode.NotFound, (await http.GetAsync(t.Url($"/v1/items/{item.Id}/files/2"))).StatusCode);
    }

    [Fact]
    public async Task Nothing_usable_copied()
    {
        var (t, http) = await Ready();
        await using var _ = t;
        t.Clipboard.Set(new ClipText(""));
        Assert.Equal(HttpStatusCode.NoContent, (await http.GetAsync(t.Url("/v1/clipboard"))).StatusCode);
        t.Clipboard.Set(new ClipFiles([Path.Combine(t.Folders.Root, "gone.txt")]));
        Assert.Equal(HttpStatusCode.NoContent, (await http.GetAsync(t.Url("/v1/clipboard"))).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await http.GetAsync(t.Url("/v1/items/nope/content"))).StatusCode);
    }

    [Fact]
    public async Task A_busy_clipboard_says_so()
    {
        var (t, http) = await Ready();
        await using var _ = t;
        t.Clipboard.Busy = true;
        t.Clipboard.Set(new ClipText("x"));
        var response = await http.GetAsync(t.Url("/v1/clipboard"));
        Assert.Equal(HttpStatusCode.ServiceUnavailable, response.StatusCode);
        Assert.Equal("clipboard_busy", (await response.Content.ReadFromJsonAsync<ErrorBody>(Json.Options))!.Error);
    }
}
