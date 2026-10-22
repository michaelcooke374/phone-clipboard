using System.Security.Cryptography;
using System.Text;
using ClipRoo.Core.Protocol;

namespace ClipRoo.Core.Pairing;

/// <summary>The one-time code in the pairing QR: single use, 10 minutes (docs/PROTOCOL.md, section 4).</summary>
public sealed class PairingCodes(TimeProvider time)
{
    public static readonly TimeSpan Lifetime = TimeSpan.FromMinutes(10);
    private readonly Lock _lock = new();
    private string? _code;
    private DateTimeOffset _expires;

    /// <summary>The QR must be redrawn (the code was used or ran out).</summary>
    public event Action? Changed;

    public string Current
    {
        get
        {
            bool renewed;
            string code;
            lock (_lock)
            {
                renewed = _code is null || time.GetUtcNow() >= _expires;
                if (renewed) Renew();
                code = _code!;
            }
            if (renewed) Changed?.Invoke();
            return code;
        }
    }

    public DateTimeOffset Expires
    {
        get { lock (_lock) return _expires; }
    }

    /// <summary>True (and a new code is made) when <paramref name="code"/> is the current, unexpired code.</summary>
    public bool TryUse(string? code)
    {
        lock (_lock)
        {
            if (code is null || _code is null || time.GetUtcNow() >= _expires) return false;
            if (!CryptographicOperations.FixedTimeEquals(Encoding.UTF8.GetBytes(code), Encoding.UTF8.GetBytes(_code)))
                return false;
            Renew();
        }
        Changed?.Invoke();
        return true;
    }

    private void Renew()
    {
        _code = Ids.New();
        _expires = time.GetUtcNow() + Lifetime;
    }
}

public static class PairingLink
{
    /// <summary>The link in the QR code: https://cliproo.app/pair#v=1&amp;id=...&amp;n=...&amp;a=...&amp;f=...&amp;c=...</summary>
    /// <param name="addresses">"host:port" candidates, best first.</param>
    public static string Build(string pcId, string pcName, IEnumerable<string> addresses, string fingerprint, string code)
    {
        var name = pcName.Length > 64 ? pcName[..64] : pcName;
        var fields = new[]
        {
            ("v", Product.ProtocolVersion.ToString()),
            ("id", pcId),
            ("n", name),
            ("a", string.Join(",", addresses)),
            ("f", fingerprint),
            ("c", code),
        };
        return Product.PairLinkBase + "#" + string.Join("&", fields.Select(f => f.Item1 + "=" + Uri.EscapeDataString(f.Item2)));
    }
}
