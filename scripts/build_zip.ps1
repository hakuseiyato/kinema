# Build the distribution ZIP for kinema.
#
# Preserves the Blender Extensions structure (src/kinema/ at the top of the
# ZIP). Excludes __pycache__ and *.pyc / *.pyo.
#
# Usage:
#   .\build_zip.ps1                    # Use manifest version for filename
#   .\build_zip.ps1 -Suffix "rc1"      # Append suffix

[CmdletBinding()]
param(
    [string]$Suffix = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$srcAddon = Join-Path $repoRoot "src\kinema"
$manifestPath = Join-Path $srcAddon "blender_manifest.toml"
$distDir = Join-Path $repoRoot "dist"

if (-not (Test-Path $srcAddon)) {
    throw "source not found: $srcAddon"
}
if (-not (Test-Path $manifestPath)) {
    throw "manifest not found: $manifestPath"
}

# Read version from manifest
$manifestText = Get-Content $manifestPath -Raw
$verMatch = [regex]::Match($manifestText, '(?m)^version\s*=\s*"([^"]+)"')
if (-not $verMatch.Success) {
    throw "version not found in manifest"
}
$version = $verMatch.Groups[1].Value

# Build ZIP name
$zipName = "kinema-v$version"
if ($Suffix) { $zipName = "$zipName-$Suffix" }
$zipName = "$zipName.zip"

if (-not (Test-Path $distDir)) {
    New-Item -ItemType Directory -Path $distDir -Force | Out-Null
}
$zipPath = Join-Path $distDir $zipName

if (Test-Path $zipPath) {
    Write-Host "[info] removing existing ZIP: $zipPath"
    Remove-Item $zipPath -Force
}

# Staging copy (exclude __pycache__ / *.pyc)
$staging = Join-Path $env:TEMP "kinema_build_$([guid]::NewGuid().ToString('N'))"
$stagingAddon = Join-Path $staging "kinema"
New-Item -ItemType Directory -Path $stagingAddon -Force | Out-Null

Write-Host "[info] staging at: $stagingAddon"
robocopy $srcAddon $stagingAddon /E /XD __pycache__ .venv /XF *.pyc *.pyo /NFL /NDL /NJH /NJS /NP > $null

# Compress
Write-Host "[info] compressing..."
Compress-Archive -Path $stagingAddon -DestinationPath $zipPath -CompressionLevel Optimal

# Cleanup
Remove-Item $staging -Recurse -Force

$size = (Get-Item $zipPath).Length
Write-Host ""
Write-Host "[done] generated: $zipPath ($([math]::Round($size / 1KB, 1)) KB)"
