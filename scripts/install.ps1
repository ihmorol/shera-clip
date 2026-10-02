# Shera Clip one-command installer (D34). Run via install.bat, or directly:
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install.ps1 [-AddPath]
# Sets up Python, the virtualenv, the desktop extra, FFmpeg (with your consent),
# Start-menu shortcuts for the desktop and web surfaces, then runs `shera doctor`.
# ASCII only on purpose: Windows PowerShell 5.1 reads BOM-less files as ANSI.
#Requires -Version 5.1
param([switch]$AddPath)
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
Write-Host "== Shera Clip installer ==" -ForegroundColor Cyan

function Need-Winget {
    if (Get-Command winget -ErrorAction SilentlyContinue) { return $true }
    Write-Host "winget is not available. Install 'App Installer' from the Microsoft Store, then re-run this installer." -ForegroundColor Yellow
    return $false
}

function Refresh-Path {
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
}

# 1) Python 3.12+
$py = Get-Command python -ErrorAction SilentlyContinue
$ok = $false
if ($py) {
    # a Store stub or old python prints to stderr; under EAP=Stop that throws even when redirected
    try { $v = (& python --version) 2>$null } catch { $v = $null }
    if ($v -match "Python 3\.(\d+)\." -and [int]$Matches[1] -ge 12) { $ok = $true; Write-Host "Python: $v" }
}
if (-not $ok) {
    Write-Host "Python 3.12+ not found."
    if (Need-Winget) {
        try { winget install --id Python.Python.3.13 -e --accept-source-agreements --accept-package-agreements } catch {}
        if ($LASTEXITCODE -ne 0) { Write-Host "winget could not install Python ($LASTEXITCODE). Install Python 3.12+ from python.org, then re-run." -ForegroundColor Yellow; exit 1 }
        Refresh-Path
        $py = Get-Command python -ErrorAction SilentlyContinue
        if (-not $py) { Write-Host "Python installed but not on PATH yet. Reopen the terminal and re-run this installer." -ForegroundColor Yellow; exit 1 }
    } else { exit 1 }
}

# 2) virtualenv (prefer the py launcher pinned to a known-good 3.13) + package
$created = $false
$pylauncher = Get-Command py -ErrorAction SilentlyContinue
if ($pylauncher) {
    try { & py -3.13 --version 2>$null; $py313 = ($LASTEXITCODE -eq 0) } catch { $py313 = $false }
    if ($py313) {
        if (-not (Test-Path "$root\.venv")) {
            py -3.13 -m venv "$root\.venv"
            if ($LASTEXITCODE -ne 0) { Write-Host "py -3.13 venv failed; falling back to python." -ForegroundColor Yellow } else { $created = $true }
        }
    }
}
if (-not (Test-Path "$root\.venv")) {
    python -m venv "$root\.venv"; $created = $true
    if ($LASTEXITCODE -ne 0) { throw "Creating the virtualenv failed ($LASTEXITCODE). Reopen the terminal and re-run this installer." }
}
if ($created) { Write-Host "Virtualenv created at $root\.venv" }
$vpip = "$root\.venv\Scripts\python.exe"
& $vpip -m pip install --quiet --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Upgrading pip failed ($LASTEXITCODE)." }
& $vpip -m pip install --quiet -e ".[desktop]"
if ($LASTEXITCODE -ne 0) { throw "Installing Shera Clip failed ($LASTEXITCODE). Scroll up for the error." }
Write-Host "Package installed (with the desktop extra)."

# 3) FFmpeg (ask first; it is a system-wide install; default is No)
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Host "FFmpeg was not found (needed to cut and caption the clips)."
    if (Need-Winget) {
        $answer = Read-Host "Install FFmpeg now with winget? [y/N]"
        if ($answer -match "^[Yy]") {
            try { winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements } catch {}
            if ($LASTEXITCODE -ne 0) { Write-Host "winget could not install FFmpeg ($LASTEXITCODE). Install it from ffmpeg.org, then run .venv\Scripts\shera.exe doctor." -ForegroundColor Yellow }
            else { Refresh-Path; Write-Host "FFmpeg installed (the doctor below re-checks it)." -ForegroundColor Yellow }
        } else {
            Write-Host "Skipped. Install FFmpeg later, then run .venv\Scripts\shera.exe doctor." -ForegroundColor Yellow
        }
    }
} else { Write-Host "FFmpeg: found." }

# 4) Start-menu shortcuts (pythonw: no console window behind the app)
$sheraExe = "$root\.venv\Scripts\shera.exe"
if (Test-Path $sheraExe) {
    $progs = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs"
    $ws = New-Object -ComObject WScript.Shell
    $pythonw = "$root\.venv\Scripts\pythonw.exe"
    $items = @(
        @{ name = "Shera Clip";       args = "-m shera desktop" },
        @{ name = "Shera Clip (Web)"; args = "-m shera" }
    )
    foreach ($item in $items) {
        $lnk = $ws.CreateShortcut("$progs\$($item.name).lnk")
        $lnk.TargetPath = $pythonw
        $lnk.Arguments = $item.args
        $lnk.WorkingDirectory = $root
        $lnk.Description = "Shera Clip - $($item.name)"
        $lnk.Save()
    }
    Write-Host "Start-menu shortcuts created: 'Shera Clip' (desktop window) and 'Shera Clip (Web)'."
} else {
    Write-Host "shera.exe was not built; skipping shortcuts." -ForegroundColor Yellow
}

# 5) optional: put shera on the user PATH so any terminal can run it
if ($AddPath) {
    $dir = "$root\.venv\Scripts"
    # reg.exe preserves REG_EXPAND_SZ (SetEnvironmentVariable would freeze %VAR% entries)
    try { $query = & reg.exe query "HKCU\Environment" /v Path 2>$null } catch { $query = $null }
    $line = ($query | Select-String "REG_") | Select-Object -First 1
    $type = "REG_SZ"; $val = ""
    if ($line) {
        if ($line -match "REG_EXPAND_SZ") { $type = "REG_EXPAND_SZ" }
        $val = ($line -split "REG_(?:EXPAND_)?SZ\s+", 2)[1].Trim()
    }
    $has = $val -and ($val.IndexOf($dir, [System.StringComparison]::OrdinalIgnoreCase) -ge 0)
    if (-not $has) {
        $new = if ($val) { "$val;$dir" } else { $dir }
        & reg.exe add "HKCU\Environment" /v Path /t $type /d "$new" /f | Out-Null
        Write-Host "Added $dir to your user PATH (new terminals only)."
    }
}

# 6) the doctor has the final word; its exit code is the installer's
& $sheraExe doctor
$doctor = $LASTEXITCODE
Write-Host ""
Write-Host "Done. Everything (web, CLI, desktop) drives the same local server and data." -ForegroundColor Cyan
Write-Host "Open a fresh terminal in $root so 'shera --help' works there too."
exit $doctor
