using System.Net;
using System.Net.NetworkInformation;
using System.Net.Sockets;
using System.Text.RegularExpressions;

namespace ClipRoo.Core.Server;

/// <summary>Where phones can reach this PC, for the pairing link (docs/PROTOCOL.md, section 4).</summary>
public static partial class Addresses
{
    /// <summary>"host:port" candidates: private IPv4 addresses (networks with a router first),
    /// then "&lt;computer name&gt;.local".</summary>
    public static IReadOnlyList<string> Candidates(int port, string computerName)
    {
        var found = new List<(IPAddress Address, bool Routed)>();
        foreach (var nic in NetworkInterface.GetAllNetworkInterfaces())
        {
            if (nic.OperationalStatus != OperationalStatus.Up
                || nic.NetworkInterfaceType is NetworkInterfaceType.Loopback or NetworkInterfaceType.Tunnel)
                continue;
            IPInterfaceProperties props;
            try { props = nic.GetIPProperties(); }
            catch (NetworkInformationException) { continue; }
            var routed = props.GatewayAddresses.Any(g => g.Address.AddressFamily == AddressFamily.InterNetwork
                                                         && !g.Address.Equals(IPAddress.Any));
            foreach (var unicast in props.UnicastAddresses)
                if (unicast.Address.AddressFamily == AddressFamily.InterNetwork && IsPrivate(unicast.Address))
                    found.Add((unicast.Address, routed));
        }
        var list = found.OrderByDescending(f => f.Routed).Select(f => $"{f.Address}:{port}").Distinct().ToList();
        if (LocalName(computerName) is { } name) list.Add($"{name}:{port}");
        return list;
    }

    /// <summary>"desktop-7gh2k1l.local", or null when the computer's name can't be used that way.</summary>
    public static string? LocalName(string computerName)
    {
        var label = computerName.Split('.')[0].ToLowerInvariant();
        return DnsLabel().IsMatch(label) ? label + ".local" : null;
    }

    public static bool IsPrivate(IPAddress address)
    {
        var b = address.GetAddressBytes();
        return b.Length == 4 && (b[0] == 10
                                 || (b[0] == 172 && b[1] is >= 16 and <= 31)
                                 || (b[0] == 192 && b[1] == 168)
                                 || (b[0] == 100 && b[1] is >= 64 and <= 127));   // also Tailscale-style addresses
    }

    [GeneratedRegex("^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")]
    private static partial Regex DnsLabel();
}
