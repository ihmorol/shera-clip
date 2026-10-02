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

# 1) Python 3.12+
$py = Get-Command python -ErrorAction SilentlyContinue
$ok = $false
if ($py) {
    $v = (& python --version) 2>$null
    if ($v -match "Python 3\.(\d+)\." -and [int]$Matches[1] -ge 12) { $ok = $true; Write-Host "Python: $v" }
}
if (-not $ok) {
    Write-Host "Python 3.12+ not found."
    if (Need-Winget) {
        winget install --id Python.Python.3.13 -e --accept-source-agreements --accept-package-agreements
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
        $py = Get-Command python -ErrorAction SilentlyContinue
        if (-not $py) { Write-Host "Python installed but not on PATH yet. Reopen the terminal and re-run this installer." -ForegroundColor Yellow; exit 1 }
    } else { exit 1 }
}

# 2) virtualenv + package with the desktop extra
if (-not (Test-Path "$root\.venv")) { python -m venv "$root\.venv" }
& "$root\.venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
& "$root\.venv\Scripts\python.exe" -m pip install --quiet -e ".[desktop]"
Write-Host "Package installed (with the desktop extra)."

# 3) FFmpeg (ask first; it is a system-wide install)
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Host "FFmpeg was not found (needed to cut and caption the clips)."
    if (Need-Winget) {
        $answer = Read-Host "Install FFmpeg now with winget? [Y/n]"
        if ($answer -notmatch "^n") {
            winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
            Write-Host "FFmpeg installed. Reopen the terminal so it lands on PATH." -ForegroundColor Yellow
        }
    }
} else { Write-Host "FFmpeg: found." }

# 4) Start-menu shortcuts for the desktop and web surfaces
$progs = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs"
$ws = New-Object -ComObject WScript.Shell
$items = @(
    @{ name = "Shera Clip";       args = "desktop" },
    @{ name = "Shera Clip (Web)"; args = "" }
)
foreach ($item in $items) {
    $lnk = $ws.CreateShortcut("$progs\$($item.name).lnk")
    $lnk.TargetPath = "$root\.venv\Scripts\shera.exe"
    $lnk.Arguments = $item.args
    $lnk.WorkingDirectory = $root
    $lnk.Description = "Shera Clip - $($item.name)"
    $lnk.Save()
}
Write-Host "Start-menu shortcuts created: 'Shera Clip' (desktop window) and 'Shera Clip (Web)'."

# 5) optional: put shera on the user PATH so any terminal can run it
if ($AddPath) {
    $dir = "$root\.venv\Scripts"
    $userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
    if ($userPath -notlike "*$dir*") {
        [System.Environment]::SetEnvironmentVariable("Path", "$userPath;$dir", "User")
        Write-Host "Added $dir to your user PATH (new terminals only)."
    }
}

# 6) the doctor has the final word
& "$root\.venv\Scripts\shera.exe" doctor
Write-Host ""
Write-Host "Done. Everything (web, CLI, desktop) drives the same local server and data." -ForegroundColor Cyan
Write-Host "Open a fresh terminal in $root so 'shera --help' works there too."
