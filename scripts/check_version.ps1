# Verify that blender_manifest.toml version base matches bl_info["version"].
# Returns exit 1 on mismatch (suitable for pre-commit hook or CI).
#
# Usage:
#   .\check_version.ps1

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$manifestPath = Join-Path $repoRoot "src\kinema\blender_manifest.toml"
$initPath = Join-Path $repoRoot "src\kinema\__init__.py"

if (-not (Test-Path $manifestPath)) {
    throw "manifest not found: $manifestPath"
}
if (-not (Test-Path $initPath)) {
    throw "__init__.py not found: $initPath"
}

# Extract version from blender_manifest.toml
$manifestText = Get-Content $manifestPath -Raw
$manifestMatch = [regex]::Match($manifestText, '(?m)^version\s*=\s*"([^"]+)"')
if (-not $manifestMatch.Success) {
    throw "version not found in manifest"
}
$manifestVer = $manifestMatch.Groups[1].Value

# Extract version tuple from bl_info
$initText = Get-Content $initPath -Raw
$initMatch = [regex]::Match($initText, '"version"\s*:\s*\((\d+)\s*,\s*(\d+)\s*,\s*(\d+)\)')
if (-not $initMatch.Success) {
    throw "bl_info version tuple not found"
}
$initVer = ("{0}.{1}.{2}" -f
    $initMatch.Groups[1].Value,
    $initMatch.Groups[2].Value,
    $initMatch.Groups[3].Value
)

Write-Host "manifest: $manifestVer"
Write-Host "bl_info : $initVer"

# Manifest may have a suffix like "-beta2"; compare only the leading X.Y.Z
$baseMatch = [regex]::Match($manifestVer, '^(\d+\.\d+\.\d+)')
if ($baseMatch.Success) {
    $manifestBase = $baseMatch.Groups[1].Value
} else {
    $manifestBase = $manifestVer
}

if ($manifestBase -eq $initVer) {
    Write-Host "[OK] base version match: $manifestBase"
    exit 0
} else {
    Write-Host "[NG] mismatch (manifest base='$manifestBase' vs bl_info='$initVer')"
    exit 1
}
