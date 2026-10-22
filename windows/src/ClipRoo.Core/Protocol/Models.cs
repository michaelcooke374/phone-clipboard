using System.Buffers.Text;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace ClipRoo.Core.Protocol;

/// <summary>What the bridge and the phone send each other (docs/PROTOCOL.md, section 5).</summary>
public static class Kinds
{
    public const string Text = "text";
    public const string Image = "image";
    public const string Files = "files";
}

public static class Origins
{
    public const string Pc = "pc";
    public const string Phone = "phone";
}

public sealed record Hello(string App, int[] Protocol, string PcId, string Name);

public sealed record PairRequest(string? Code, string? PhoneId, string? PhoneName, string? Platform, string? AppVersion);

public sealed record PairResponse(string Token, string PcId, string PcName, int Protocol);

public sealed record ItemFile(string Name, long Size, string Type);

/// <summary>Everything that moves between the phone and the PC is an item.</summary>
public sealed record Item
{
    public required string Id { get; init; }
    public required string Origin { get; init; }
    public required string Kind { get; init; }
    public required DateTime Created { get; init; }

    /// <summary>The text itself, for text items of 64 KB or less (else fetch the content).</summary>
    public string? Text { get; init; }

    public long Size { get; init; }
    public string? Type { get; init; }
    public int? Width { get; init; }
    public int? Height { get; init; }
    public IReadOnlyList<ItemFile>? Files { get; init; }

    /// <summary>Only in answers to sending: one sentence for the phone to show.</summary>
    public string? Message { get; init; }
}

public sealed record TextToSend(string? Kind, string? Text);

public sealed record ErrorBody(string Error, string Message);

public static class Json
{
    /// <summary>snake_case names, no nulls, times as "2026-10-21T15:30:00Z".</summary>
    public static readonly JsonSerializerOptions Options = Make();

    private static JsonSerializerOptions Make()
    {
        var o = new JsonSerializerOptions(JsonSerializerDefaults.Web)
        {
            PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
            DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        };
        o.Converters.Add(new UtcSecondsConverter());
        return o;
    }

    private sealed class UtcSecondsConverter : JsonConverter<DateTime>
    {
        public override DateTime Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options) =>
            reader.GetDateTime().ToUniversalTime();

        public override void Write(Utf8JsonWriter writer, DateTime value, JsonSerializerOptions options) =>
            writer.WriteStringValue(value.ToUniversalTime().ToString("yyyy-MM-dd'T'HH:mm:ss'Z'"));
    }
}

public static class Ids
{
    /// <summary>A random identifier or secret: 16 bytes make 22 characters, 32 bytes 43.</summary>
    public static string New(int bytes = 16) => Base64Url.EncodeToString(RandomNumberGenerator.GetBytes(bytes));

    /// <summary>The SHA-256 of a secret, for keeping it without being able to give it out.</summary>
    public static string Hash(string secret) => Base64Url.EncodeToString(SHA256.HashData(Encoding.UTF8.GetBytes(secret)));
}
