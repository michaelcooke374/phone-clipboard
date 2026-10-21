# Phone Clipboard set-up. start.bat runs it the first time; setup.bat runs it again whenever
# you like (it's safe to run as often as you want). uninstall.bat runs it with -Remove.
#
# 1. Checks the folder is a good place (not still inside the zip, not Program Files or OneDrive).
# 2. Gets Python for Phone Clipboard's own use, into the .python folder here (with uv, the
#    tool that also sets up Python for Ashera Clips; it's installed with winget if missing),
#    and Pillow for pictures into the .packages folder (the exact version in
#    app\requirements.txt, checked against its fingerprints).
# 3. Makes Phone Clipboard start by itself when you sign in to Windows, and puts it in the
#    Start menu.
# 4. With administrator permission (Windows asks once): lets iPhones on your own network reach
#    it through Windows Firewall, and offers to mark your network as private if Windows
#    treats it as public.
#
#   -Remove   stop Phone Clipboard and undo 3 and 4 (the folder stays: delete it afterwards)
#   -Admin    the part that needs administrator permission (the script starts itself again
#             with it, in its own window)
#   -AppDir   the Phone Clipboard folder (normally the folder above this one)
#
# Exit codes: 0 = done, 2 = stopped (the reason and what to do are shown).

param(
    [switch]$Remove,
    [switch]$Admin,
    [string]$AppDir = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = "Stop"
$AppDir = [System.IO.Path]::GetFullPath($AppDir).TrimEnd('\')
$RuleName = "Phone Clipboard"                   # netinfo.py looks for rules with this name
$PythonVersion = "3.12"
$PythonDir = Join-Path $AppDir ".python"
$PackagesDir = Join-Path $AppDir ".packages"
$Requirements = Join-Path $AppDir "app\requirements.txt"
$DataDir = Join-Path $AppDir "data"
$DoneFile = Join-Path $DataDir "setup-done.txt"
$Program = Join-Path $AppDir "app\phone_clipboard.py"
$Icon = Join-Path $AppDir "app\pages\icon.ico"
$Startup = Join-Path ([Environment]::GetFolderPath("Startup")) "Phone Clipboard.lnk"
$StartMenu = Join-Path ([Environment]::GetFolderPath("Programs")) "Phone Clipboard.lnk"

function Say([string]$text = "") { Write-Host "  $text" }
function Problem([string]$what, [string[]]$todo) {
    Write-Host ""
    Write-Host "  [PROBLEM] $what" -ForegroundColor Yellow
    Write-Host ""
    foreach ($line in $todo) { Write-Host "  $line" }
    Write-Host ""
    exit 2
}
function Under([string]$folder) {
    if (-not $folder) { return $false }
    $f = [System.IO.Path]::GetFullPath($folder).TrimEnd('\')
    return $AppDir.Equals($f, [StringComparison]::OrdinalIgnoreCase) -or
           $AppDir.StartsWith($f + '\', [StringComparison]::OrdinalIgnoreCase)
}

# The port in data\settings.json (8799 unless it was changed there).
function Get-Port {
    $port = 8799
    $file = Join-Path $DataDir "settings.json"
    if (Test-Path $file) {
        try {
            $value = (Get-Content $file -Raw -Encoding UTF8 | ConvertFrom-Json).port
            $n = 0
            if ([int]::TryParse([string]$value, [ref]$n) -and $n -ge 1 -and $n -le 65535) { $port = $n }
        } catch { }
    }
    return $port
}

# python.exe and pythonw.exe of Phone Clipboard's own Python.
function Find-Pythons {
    if (-not (Test-Path $PythonDir)) { return @() }
    $found = @()
    foreach ($dir in Get-ChildItem $PythonDir -Directory -Filter "cpython-$PythonVersion*" -ErrorAction SilentlyContinue) {
        foreach ($name in @("python.exe", "pythonw.exe")) {
            $exe = Join-Path $dir.FullName $name
            if (Test-Path $exe) { $found += $exe }
        }
    }
    return $found
}

function Stop-PhoneClipboard {
    $port = Get-Port
    try {
        Invoke-WebRequest -Uri "http://127.0.0.1:$port/pc/stop" -Method Post -UseBasicParsing -TimeoutSec 5 | Out-Null
        Start-Sleep -Milliseconds 800
    } catch { }
    # In case it didn't answer: end any Python that is running this folder's Phone Clipboard.
    Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe' OR Name = 'python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine.IndexOf($Program, [StringComparison]::OrdinalIgnoreCase) -ge 0 } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

# ---- The administrator part (its own window) --------------------------------------------------
if ($Admin) {
    try {
        $port = Get-Port
        Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
        if ($Remove) {
            Say "Removed Phone Clipboard's Windows Firewall rule."
            exit 0
        }
        Say "Windows Firewall: letting iPhones on your own network reach Phone Clipboard (port $port)..."
        $pythons = Find-Pythons
        # If someone once clicked Cancel when Windows asked whether this Python may use the network,
        # Windows made rules that block it, and those win over any rule that allows it. Remove them.
        foreach ($exe in $pythons) {
            Get-NetFirewallApplicationFilter -Program $exe -ErrorAction SilentlyContinue |
                Get-NetFirewallRule -ErrorAction SilentlyContinue |
                Where-Object { [string]$_.Action -eq "Block" -and [string]$_.Direction -eq "Inbound" } |
                Remove-NetFirewallRule
        }
        $about = "Lets iPhones on your own (private) network use Phone Clipboard. Made by $AppDir\setup.bat; removed by uninstall.bat."
        # Private and work networks only: on public Wi-Fi (cafes, hotels) nobody can reach it.
        New-NetFirewallRule -DisplayName $RuleName -Description $about -Direction Inbound -Action Allow `
            -Protocol TCP -LocalPort $port -Profile Private,Domain | Out-Null
        foreach ($exe in $pythons) {
            # Rules naming the program itself, so Windows doesn't ask about it when it starts.
            New-NetFirewallRule -DisplayName $RuleName -Description $about -Direction Inbound -Action Allow `
                -Program $exe -Protocol TCP -LocalPort $port -Profile Private,Domain | Out-Null
        }
        Say "Done."

        # Only real connections (with a router), not virtual networks that other programs make.
        $routed = @(Get-NetIPConfiguration -ErrorAction SilentlyContinue | Where-Object { $_.IPv4DefaultGateway } |
                    ForEach-Object { $_.InterfaceIndex })
        $public = @(Get-NetConnectionProfile -ErrorAction SilentlyContinue |
                    Where-Object { [string]$_.NetworkCategory -eq "Public" -and $routed -contains $_.InterfaceIndex })
        foreach ($net in $public) {
            Say ""
            Say ("Windows treats your network ""{0}"" ({1}) as PUBLIC." -f $net.Name, $net.InterfaceAlias)
            Say "On a public network Windows keeps other devices out, so your iPhone can't reach this computer."
            Say "Your own home, church or office network should be PRIVATE. (Public Wi-Fi in a cafe or hotel"
            Say "should stay public.)"
            $answer = Read-Host "  Is this your own network? Type Y and press Enter to make it private (or just press Enter)"
            if ($answer -match '^\s*[yY]') {
                Set-NetConnectionProfile -InterfaceIndex $net.InterfaceIndex -NetworkCategory Private
                Say "Done: Windows now treats it as a private network."
            } else {
                Say "Left as it is. Phone Clipboard works only on private networks."
            }
        }
        exit 0
    } catch {
        Write-Host ""
        Write-Host "  [PROBLEM] Windows Firewall couldn't be set up for Phone Clipboard." -ForegroundColor Yellow
        Write-Host "  $($_.Exception.Message)"
        Write-Host ""
        Write-Host "  If another security program (like Norton, McAfee or Bitdefender) runs your firewall,"
        Write-Host "  allow incoming connections on port $(Get-Port) for your private network in it."
        Write-Host ""
        [void](Read-Host "  Press Enter to close this window")
        exit 3
    }
}

# Runs this script again with administrator permission (Windows asks), in its own window.
function Invoke-AdminPart([switch]$Removing) {
    $arguments = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$PSCommandPath`"", "-Admin",
                   "-AppDir", "`"$AppDir`"")
    if ($Removing) { $arguments += "-Remove" }
    try {
        $p = Start-Process -FilePath "powershell.exe" -Verb RunAs -Wait -PassThru -ArgumentList $arguments
        return ($p.ExitCode -eq 0)
    } catch {
        return $false                           # "No" was clicked
    }
}

# ---- Removing ----------------------------------------------------------------------------------
if ($Remove) {
    Say "Removing Phone Clipboard..."
    Stop-PhoneClipboard
    foreach ($lnk in @($Startup, $StartMenu)) { Remove-Item $lnk -Force -ErrorAction SilentlyContinue }
    Say "Stopped it, and removed it from the Start menu and from starting with Windows."
    Say "Windows now asks for permission to remove the firewall rule. Click Yes."
    if (Invoke-AdminPart -Removing) {
        Say "Removed the firewall rule."
    } else {
        Say "The firewall rule wasn't removed. It's harmless on its own (nothing answers on that port"
        Say "any more); to remove it, double-click uninstall.bat again and click Yes."
    }
    Remove-Item $DoneFile -Force -ErrorAction SilentlyContinue
    Say ""
    Say "Phone Clipboard is removed. You can delete this folder now:"
    Say "   $AppDir"
    Say "On the iPhone, delete the Get from PC and Send to PC shortcuts (and Back Tap, if you set it)."
    exit 0
}

# ---- Setting up --------------------------------------------------------------------------------
Say "Setting up Phone Clipboard in $AppDir"
Say ""

# 1. Is the folder a good place?
if ($AppDir -match '\\AppData\\Local\\Temp\\' -or $AppDir -match '\.zip\\') {
    Problem "Phone Clipboard is still inside the zip file." @(
        "What to do: close this window. Right-click the zip file and choose 'Extract All...'.",
        "Type C:\ as the place to extract to and click Extract. Then open the new folder in C:\",
        "and double-click start.bat there.")
}
foreach ($pf in @($env:ProgramFiles, ${env:ProgramFiles(x86)})) {
    if (Under $pf) {
        Problem "Phone Clipboard is in the Program Files folder, where it can't save its settings." @(
            "What to do: move the folder to C:\ and double-click start.bat there.")
    }
}
foreach ($od in @($env:OneDrive, $env:OneDriveConsumer, $env:OneDriveCommercial)) {
    if (Under $od) {
        Problem "Phone Clipboard is in a OneDrive folder." @(
            "OneDrive would copy its private settings (with its key) to the cloud and to your other computers.",
            "What to do: move the folder to C:\ and double-click start.bat there.")
    }
}

# Stop a copy that's already running (after an update it would still run the old program).
Stop-PhoneClipboard

# 2. uv, and Python for Phone Clipboard's own use.
$links = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links"
if ((Test-Path $links) -and -not (($env:PATH -split ';') -contains $links)) { $env:PATH = "$links;$env:PATH" }
function Has-Uv { return [bool](Get-Command "uv" -ErrorAction SilentlyContinue) }

if (-not (Find-Pythons | Where-Object { $_ -like "*\pythonw.exe" })) {
    if (-not (Has-Uv)) {
        if (-not (Get-Command "winget" -ErrorAction SilentlyContinue)) {
            Problem "Windows' app installer (winget) is missing, so Python can't be installed for you." @(
                "What to do: open the Microsoft Store, search for 'App Installer', and click Get or Update.",
                "Then double-click start.bat again.")
        }
        Say "Phone Clipboard needs a free tool called uv, which installs Python for it."
        Say "Press Enter to install it now (a minute), or close this window to stop."
        [void](Read-Host)
        $ErrorActionPreference = "Continue"
        & winget install --id astral-sh.uv --exact --silent --accept-source-agreements --accept-package-agreements --disable-interactivity | Out-Host
        $ErrorActionPreference = "Stop"
        if ((Test-Path $links) -and -not (($env:PATH -split ';') -contains $links)) { $env:PATH = "$links;$env:PATH" }
        if (-not (Has-Uv)) {
            $env:PATH = [Environment]::GetEnvironmentVariable("PATH", "User") + ";" + [Environment]::GetEnvironmentVariable("PATH", "Machine") + ";$env:PATH"
        }
        if (-not (Has-Uv)) {
            Problem "uv couldn't be installed." @(
                "This is usually an internet hiccup, or Windows needing a restart after installing.",
                "What to do: restart the computer, then double-click start.bat again.",
                "If it keeps happening, open PowerShell and type:  winget install astral-sh.uv")
        }
    }
    Say "Getting Python for Phone Clipboard's own use (about 30 MB, one time only)..."
    $env:UV_PYTHON_INSTALL_DIR = $PythonDir
    $ErrorActionPreference = "Continue"
    # --no-bin and --no-registry: keep this Python to itself (not on the PATH, not in the registry).
    & uv python install $PythonVersion --no-bin --no-registry | Out-Host
    if ($LASTEXITCODE -ne 0) { & uv python install $PythonVersion | Out-Host }     # an older uv without those options
    $ErrorActionPreference = "Stop"
}
$pythonw = Find-Pythons | Where-Object { $_ -like "*\pythonw.exe" } | Select-Object -Last 1
$python = Find-Pythons | Where-Object { $_ -like "*\python.exe" } | Select-Object -Last 1
if (-not $pythonw -or -not $python) {
    Problem "Python couldn't be installed for Phone Clipboard." @(
        "This is usually an internet hiccup.",
        "What to do: check your internet connection, then double-click start.bat again.")
}
$ErrorActionPreference = "Continue"
$check = & $python -c "import ctypes, http.server, json; print('ok')"
$ErrorActionPreference = "Stop"
if ($check -ne "ok") {
    Problem "Phone Clipboard's copy of Python doesn't start." @(
        "What to do: delete the .python folder inside $AppDir, then double-click start.bat again.")
}
Say "Python is ready."

# Pillow, for pictures. Without it text still works, so a problem here doesn't stop the set-up.
$pillowVersion = ([regex]::Match((Get-Content $Requirements -Raw), 'pillow==([0-9.]+)')).Groups[1].Value
function Get-PillowVersion {
    $ErrorActionPreference = "Continue"
    $v = & $python -c "import sys; sys.path.append(sys.argv[1]); import PIL; print(PIL.__version__)" $PackagesDir 2>$null
    $ErrorActionPreference = "Stop"
    return [string]$v
}
if ((Get-PillowVersion) -ne $pillowVersion) {
    if (-not (Has-Uv)) {
        Say "Pictures need uv, which isn't here. Text works; to add pictures, install uv"
        Say "(open PowerShell and type: winget install astral-sh.uv), then double-click setup.bat."
    } else {
        Say "Getting the part that handles pictures (about 7 MB, one time only)..."
        $ErrorActionPreference = "Continue"
        & uv pip install --python $python --target $PackagesDir --no-deps --require-hashes --upgrade -r $Requirements | Out-Host
        $ErrorActionPreference = "Stop"
    }
}
if ((Get-PillowVersion) -eq $pillowVersion) {
    Say "Pictures are ready."
} else {
    Write-Host "  [NOTE] The part that handles pictures couldn't be installed. Text works; for pictures," -ForegroundColor Yellow
    Say "check your internet connection and double-click setup.bat again."
}

# 3. Start with Windows, and the Start menu.
$shell = New-Object -ComObject WScript.Shell
foreach ($item in @(@{ Path = $Startup; Arguments = "`"$Program`"" },
                    @{ Path = $StartMenu; Arguments = "`"$Program`" --open" })) {
    $s = $shell.CreateShortcut($item.Path)
    $s.TargetPath = $pythonw
    $s.Arguments = $item.Arguments
    $s.WorkingDirectory = $AppDir
    $s.Description = "Copy and paste between this computer and your iPhone"
    if (Test-Path $Icon) { $s.IconLocation = "$Icon,0" }
    $s.Save()
}
Say "Phone Clipboard now starts by itself when you sign in to Windows, and it's in the Start menu."

# 4. Windows Firewall and the network type (administrator permission).
Say ""
Say "Next, Windows asks for permission to let your iPhone through the firewall. Click Yes."
$adminDone = Invoke-AdminPart
if ($adminDone) {
    Say "The firewall lets iPhones on your own network reach Phone Clipboard."
} else {
    Say ""
    Write-Host "  [NOTE] The firewall wasn't changed, so your iPhone may not be able to connect." -ForegroundColor Yellow
    Say "To try again, double-click setup.bat and click Yes when Windows asks."
}

if ($adminDone) {
    New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
    Set-Content -Path $DoneFile -Value ("Set up on {0:yyyy-MM-dd HH:mm} in {1}" -f (Get-Date), $AppDir) -Encoding UTF8
}
Say ""
Say "All set. The Phone Clipboard page opens in your browser now."
exit 0
