using System.Buffers.Text;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using ClipRoo.Core.Platform;
using ClipRoo.Core.Protocol;

namespace ClipRoo.Core.Security;

/// <summary>Who this PC is: its id and its certificate (docs/PROTOCOL.md, section 2). Made on the
/// first start and kept for good, so paired phones keep recognising it.</summary>
public sealed class Identity
{
    private const string FileName = "identity.json";

    public string PcId { get; }
    public X509Certificate2 Certificate { get; }

    /// <summary>SHA-256 of the certificate, base64url: what phones pin.</summary>
    public string Fingerprint { get; }

    private Identity(string pcId, X509Certificate2 certificate)
    {
        PcId = pcId;
        Certificate = certificate;
        Fingerprint = FingerprintOf(certificate);
    }

    public static string FingerprintOf(X509Certificate certificate) =>
        Base64Url.EncodeToString(SHA256.HashData(certificate.GetRawCertData()));

    public static Identity LoadOrCreate(string dataFolder, ISecretProtector protector)
    {
        var path = Path.Combine(dataFolder, FileName);
        var saved = JsonFile.Read<Saved>(path);
        if (saved is not null)
        {
            try
            {
                var pfx = protector.Unprotect(Convert.FromBase64String(saved.Certificate));
                return new Identity(saved.PcId, Load(pfx));
            }
            catch (Exception e) when (e is CryptographicException or FormatException)
            {
                // Unreadable (copied from another Windows user, say): a new identity, and phones
                // pair again. Kept aside rather than deleted.
                File.Move(path, path + ".unreadable", overwrite: true);
            }
        }
        var pcId = Ids.New();
        var made = Create(pcId);
        var bytes = made.Export(X509ContentType.Pfx);
        JsonFile.Write(path, new Saved(pcId, Convert.ToBase64String(protector.Protect(bytes))));
        return new Identity(pcId, Load(bytes));
    }

    private static X509Certificate2 Create(string pcId)
    {
        using var key = ECDsa.Create(ECCurve.NamedCurves.nistP256);
        var request = new CertificateRequest($"CN={Product.Name} {pcId}", key, HashAlgorithmName.SHA256);
        request.CertificateExtensions.Add(new X509BasicConstraintsExtension(false, false, 0, true));
        request.CertificateExtensions.Add(new X509KeyUsageExtension(X509KeyUsageFlags.DigitalSignature, true));
        request.CertificateExtensions.Add(new X509EnhancedKeyUsageExtension([new Oid("1.3.6.1.5.5.7.3.1")], false));
        var now = DateTimeOffset.UtcNow;
        return request.CreateSelfSigned(now.AddDays(-1), now.AddYears(20));
    }

    // Loaded from PFX bytes, so Windows' TLS (SChannel) can use the private key.
    private static X509Certificate2 Load(byte[] pfx) => X509CertificateLoader.LoadPkcs12(pfx, null);

    private sealed record Saved(string PcId, string Certificate);
}
