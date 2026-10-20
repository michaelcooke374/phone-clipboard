"""This computer's addresses on your network, and the Windows settings that decide whether
an iPhone can reach it (is the network "private"? is the firewall rule there?)."""

from __future__ import annotations

import base64
import ipaddress
import json
import re
import socket
import subprocess
import sys

FIREWALL_RULE = "Phone Clipboard"       # the name windows-setup.ps1 gives its firewall rules


def computer_name() -> str:
    """This computer's name, like "DESKTOP-7GH2K1L"."""
    return socket.gethostname()


def local_name() -> str | None:
    """The name iPhones can use instead of the number address ("desktop-7gh2k1l.local"),
    or None when the computer's name can't be used that way."""
    name = computer_name().split(".")[0].lower()
    return f"{name}.local" if re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", name) else None


def lan_addresses() -> list[str]:
    """This computer's IPv4 addresses that other devices could reach, best guess first: the
    one Windows uses for the internet (normally the Wi-Fi or cable), then other home-network
    ones."""
    found: list[str] = []
    try:
        # Asks Windows which address it would send from. Nothing is actually sent.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))
            found.append(s.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.append(str(info[4][0]))
    except OSError:
        pass
    out: list[str] = []
    for ip in found:
        try:
            a = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if a.is_loopback or a.is_link_local or a.is_unspecified or ip in out:
            continue
        out.append(ip)
    out.sort(key=lambda ip: not ipaddress.ip_address(ip).is_private)     # stable: keeps the order otherwise
    return out


_STATUS_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
$profiles = @(Get-NetConnectionProfile | ForEach-Object {
    [pscustomobject]@{ name = [string]$_.Name; adapter = [string]$_.InterfaceAlias;
                       index = [int]$_.InterfaceIndex; category = [string]$_.NetworkCategory } })
$addresses = @(Get-NetIPAddress -AddressFamily IPv4 | ForEach-Object {
    [pscustomobject]@{ ip = [string]$_.IPAddress; index = [int]$_.InterfaceIndex } })
$rules = @(Get-NetFirewallRule -DisplayName '%RULE%' | Where-Object {
    [string]$_.Enabled -eq 'True' -and [string]$_.Action -eq 'Allow' -and [string]$_.Direction -eq 'Inbound' }).Count
$json = [pscustomobject]@{ profiles = $profiles; addresses = $addresses; rules = $rules } | ConvertTo-Json -Depth 3 -Compress
[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($json))
"""


def windows_status() -> dict | None:
    """What Windows says about the networks and the firewall rule:
    {"networks": {ip: {"name", "adapter", "category"}}, "rule": bool}.
    None when it couldn't be asked (not Windows, or PowerShell failed)."""
    if sys.platform != "win32":
        return None
    try:
        out = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand",
             base64.b64encode(_STATUS_SCRIPT.replace("%RULE%", FIREWALL_RULE).encode("utf-16-le")).decode("ascii")],
            capture_output=True, text=True, timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        # Sent as base64 so network names in any language arrive intact.
        data = json.loads(base64.b64decode(out.stdout.strip().splitlines()[-1]).decode("utf-8"))
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None
    profiles = data.get("profiles") or []
    addresses = data.get("addresses") or []
    # ConvertTo-Json turns a list of one into a single object.
    profiles = [profiles] if isinstance(profiles, dict) else profiles
    addresses = [addresses] if isinstance(addresses, dict) else addresses
    by_index = {p.get("index"): p for p in profiles if isinstance(p, dict)}
    networks = {}
    for a in addresses:
        if isinstance(a, dict) and a.get("index") in by_index:
            p = by_index[a["index"]]
            networks[a.get("ip")] = {"name": p.get("name") or "", "adapter": p.get("adapter") or "",
                                     "category": p.get("category") or ""}
    return {"networks": networks, "rule": bool(data.get("rules"))}


def is_private(category: str) -> bool:
    return category in ("Private", "DomainAuthenticated")


def best_address(addresses: list[str], status: dict | None) -> str | None:
    """The address to give the iPhone: one on a network Windows calls private, if any."""
    if status:
        nets = status.get("networks", {})
        for ip in addresses:
            if is_private(nets.get(ip, {}).get("category", "")):
                return ip
        for ip in addresses:
            if ip in nets:
                return ip
    return addresses[0] if addresses else None
