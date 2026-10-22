using System.Net;
using System.Net.Http.Json;
using ClipRoo.Core.Pairing;
using ClipRoo.Core.Protocol;
using Xunit;

namespace ClipRoo.Core.Tests;

public class PairingTests
{
    [Fact]
    public async Task Hello_needs_no_token()
    {
        await using var t = await TestBridge.StartAsync();
        using var http = t.Client();
        var hello = await http.GetFromJsonAsync<Hello>(t.Url("/v1/hello"), Json.Options);
        Assert.Equal("cliproo", hello!.App);
        Assert.Equal([1], hello.Protocol);
        Assert.Equal(t.Identity.PcId, hello.PcId);
        Assert.Equal("TEST-PC", hello.Name);
    }

    [Fact]
    public async Task Pairing_gives_a_token_and_a_fresh_code()
    {
        await using var t = await TestBridge.StartAsync();
        var code = t.Codes.Current;
        var token = await t.PairAsync();
        Assert.Equal(43, token.Length);
        Assert.NotEqual(code, t.Codes.Current);
        Assert.Contains(t.Notifier.Shown, n => n.Title == "Test iPhone is paired");
        using var http = t.Client(token);
        Assert.Equal(HttpStatusCode.NoContent, (await http.GetAsync(t.Url("/v1/clipboard"))).StatusCode);
        Assert.DoesNotContain(token, File.ReadAllText(Path.Combine(t.Folders.Data, "devices.json")));
    }

    [Fact]
    public async Task Used_wrong_or_expired_codes_are_refused()
    {
        await using var t = await TestBridge.StartAsync();
        using var http = t.Client();
        async Task<HttpStatusCode> Try(string code) =>
            (await http.PostAsJsonAsync(t.Url("/v1/pair"), new PairRequest(code, "p", "n", "ios", "1"), Json.Options)).StatusCode;

        var code = t.Codes.Current;
        Assert.Equal(HttpStatusCode.OK, await Try(code));
        Assert.Equal(HttpStatusCode.Forbidden, await Try(code));
        Assert.Equal(HttpStatusCode.Forbidden, await Try("not-the-code"));
        var late = t.Codes.Current;
        t.Time.Advance(PairingCodes.Lifetime + TimeSpan.FromSeconds(1));
        Assert.Equal(HttpStatusCode.Forbidden, await Try(late));
    }

    [Fact]
    public async Task Too_many_pairing_tries_wait_a_minute()
    {
        await using var t = await TestBridge.StartAsync();
        using var http = t.Client();
        for (var i = 0; i < 10; i++)
            await http.PostAsJsonAsync(t.Url("/v1/pair"), new PairRequest("wrong", "p", "n", "ios", "1"), Json.Options);
        var blocked = await http.PostAsJsonAsync(t.Url("/v1/pair"), new PairRequest(t.Codes.Current, "p", "n", "ios", "1"), Json.Options);
        Assert.Equal(HttpStatusCode.TooManyRequests, blocked.StatusCode);
        t.Time.Advance(TimeSpan.FromMinutes(1));
        var later = await http.PostAsJsonAsync(t.Url("/v1/pair"), new PairRequest(t.Codes.Current, "p", "n", "ios", "1"), Json.Options);
        Assert.Equal(HttpStatusCode.OK, later.StatusCode);
    }

    [Fact]
    public async Task Requests_need_a_paired_token()
    {
        await using var t = await TestBridge.StartAsync();
        foreach (var token in new string?[] { null, "made-up-token" })
        {
            using var http = t.Client(token);
            var response = await http.GetAsync(t.Url("/v1/clipboard"));
            Assert.Equal(HttpStatusCode.Unauthorized, response.StatusCode);
            var error = await response.Content.ReadFromJsonAsync<ErrorBody>(Json.Options);
            Assert.Equal("unauthorized", error!.Error);
        }
    }

    [Fact]
    public async Task Too_many_wrong_tokens_wait_a_minute()
    {
        await using var t = await TestBridge.StartAsync();
        var good = await t.PairAsync();
        using var bad = t.Client("made-up-token");
        for (var i = 0; i < 30; i++) await bad.GetAsync(t.Url("/v1/clipboard"));
        using var http = t.Client(good);
        Assert.Equal(HttpStatusCode.TooManyRequests, (await http.GetAsync(t.Url("/v1/clipboard"))).StatusCode);
    }

    [Fact]
    public async Task Pairing_again_replaces_the_old_token()
    {
        await using var t = await TestBridge.StartAsync();
        var first = await t.PairAsync("same-phone");
        var second = await t.PairAsync("same-phone");
        using var old = t.Client(first);
        using var current = t.Client(second);
        Assert.Equal(HttpStatusCode.Unauthorized, (await old.GetAsync(t.Url("/v1/clipboard"))).StatusCode);
        Assert.Equal(HttpStatusCode.NoContent, (await current.GetAsync(t.Url("/v1/clipboard"))).StatusCode);
        Assert.Single(t.Devices.All);
    }

    [Fact]
    public async Task A_phone_can_unpair_itself_and_be_removed()
    {
        await using var t = await TestBridge.StartAsync();
        var token = await t.PairAsync();
        using var http = t.Client(token);
        Assert.Equal(HttpStatusCode.OK, (await http.DeleteAsync(t.Url("/v1/devices/me"))).StatusCode);
        Assert.Equal(HttpStatusCode.Unauthorized, (await http.GetAsync(t.Url("/v1/clipboard"))).StatusCode);

        var other = await t.PairAsync("phone-2");
        Assert.True(t.Devices.Remove("phone-2"));
        using var removed = t.Client(other);
        Assert.Equal(HttpStatusCode.Unauthorized, (await removed.GetAsync(t.Url("/v1/clipboard"))).StatusCode);
    }

    [Fact]
    public async Task A_different_certificate_is_refused_by_the_phone()
    {
        await using var t = await TestBridge.StartAsync();
        using var http = t.Client(pin: "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA");
        await Assert.ThrowsAsync<HttpRequestException>(() => http.GetAsync(t.Url("/v1/hello")));
    }

    [Fact]
    public async Task Identity_and_pairings_survive_a_restart()
    {
        await using var t = await TestBridge.StartAsync();
        var fingerprint = t.Identity.Fingerprint;
        var pcId = t.Identity.PcId;
        var token = await t.PairAsync();
        await t.RestartAsync();
        Assert.Equal(fingerprint, t.Identity.Fingerprint);
        Assert.Equal(pcId, t.Identity.PcId);
        using var http = t.Client(token);
        Assert.Equal(HttpStatusCode.NoContent, (await http.GetAsync(t.Url("/v1/clipboard"))).StatusCode);
    }

    [Fact]
    public void Pairing_link_has_every_field()
    {
        var link = PairingLink.Build("PCID", "Mike's PC & more", ["192.168.1.5:47820", "desk.local:47820"], "FP", "CODE");
        Assert.Equal("https://cliproo.app/pair#v=1&id=PCID&n=Mike%27s%20PC%20%26%20more&a=192.168.1.5%3A47820%2Cdesk.local%3A47820&f=FP&c=CODE", link);
    }
}
