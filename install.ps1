# ==============================================================================
# crawly: the literature assistant — One-Line PowerShell Installer for Windows
# https://github.com/lokeshsk/crawly
# Usage: irm https://lokeshsk.github.io/crawly/install.ps1 | iex
# ==============================================================================
$ErrorActionPreference = "Stop"

$Repo = "lokeshsk/crawly"
$InstallDir = Join-Path $env:LOCALAPPDATA "crawly"
$ZipUrl = "https://github.com/$Repo/releases/latest/download/crawly-universal-windows-linux.zip"
$FallbackZipUrl = "https://github.com/$Repo/raw/main/dist/crawly-universal-windows-linux.zip"

Write-Host "🕷️  Installing crawly: the literature assistant on Windows..." -ForegroundColor Cyan

if (-not (Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
}

$TempZip = Join-Path $env:TEMP "crawly_install.zip"

try {
    Write-Host "Downloading release bundle from GitHub..." -ForegroundColor Gray
    Invoke-WebRequest -Uri $ZipUrl -OutFile $TempZip -UseBasicParsing
    Write-Host "✓ Downloaded latest release bundle" -ForegroundColor Green
} catch {
    Write-Host "Retrying via fallback mirror..." -ForegroundColor Yellow
    Invoke-WebRequest -Uri $FallbackZipUrl -OutFile $TempZip -UseBasicParsing
    Write-Host "✓ Downloaded release bundle" -ForegroundColor Green
}

Expand-Archive -Path $TempZip -DestinationPath $InstallDir -Force
Remove-Item -Path $TempZip -Force -ErrorAction SilentlyContinue

# Create crawly.cmd wrapper inside $InstallDir
$CmdWrapper = Join-Path $InstallDir "crawly.cmd"
"@echo off`r`n`"%~dp0crawly.bat`" %*" | Out-File -FilePath $CmdWrapper -Encoding ascii -Force

# Add to User PATH if not already present
$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($UserPath -notlike "*$InstallDir*") {
    $NewPath = "$UserPath;$InstallDir"
    [Environment]::SetEnvironmentVariable("Path", $NewPath, "User")
    $env:Path = "$env:Path;$InstallDir"
    Write-Host "✓ Added $InstallDir to user PATH" -ForegroundColor Green
}

Write-Host ""
Write-Host "🎉 Installation complete! Open a new PowerShell / Command Prompt and run:" -ForegroundColor Green
Write-Host "   crawly                     # Interactive Literature Dashboard" -ForegroundColor Cyan
Write-Host "   crawly search `"radar`"      # Search across 8+ open scholarly databases" -ForegroundColor Cyan
Write-Host "   crawly snowball `"<DOI>`"    # Trace citation network forward & backward" -ForegroundColor Cyan
Write-Host "   crawly doctor              # Health check for APIs & AI models" -ForegroundColor Cyan
Write-Host ""

