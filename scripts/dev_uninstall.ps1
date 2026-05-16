# kinema dev uninstall
#
# 使い方:
#   .\dev_uninstall.ps1                  # 自動検出
#   .\dev_uninstall.ps1 -BlenderVersion "5.0"

[CmdletBinding()]
param(
    [string]$BlenderVersion = ""
)

$ErrorActionPreference = "Stop"

$blenderUserRoot = Join-Path $env:APPDATA "Blender Foundation\Blender"
if (-not (Test-Path $blenderUserRoot)) {
    throw "Blender ユーザー設定が見つかりません: $blenderUserRoot"
}

if ([string]::IsNullOrWhiteSpace($BlenderVersion)) {
    $candidates = Get-ChildItem -Path $blenderUserRoot -Directory |
        Where-Object { $_.Name -match '^\d+\.\d+$' }
    if (-not $candidates) {
        throw "Blender バージョンディレクトリが見つかりません: $blenderUserRoot"
    }
    $scored = $candidates | ForEach-Object {
        $userpref = Join-Path $_.FullName "config\userpref.blend"
        $mtime = if (Test-Path $userpref) { (Get-Item $userpref).LastWriteTime } else { [DateTime]::MinValue }
        [PSCustomObject]@{ Name = $_.Name; MTime = $mtime }
    } | Sort-Object MTime -Descending
    $BlenderVersion = $scored[0].Name
    Write-Host "[info] Blender バージョン自動検出: $BlenderVersion"
}

$verRoot = Join-Path $blenderUserRoot $BlenderVersion

$paths = @(
    (Join-Path $verRoot "extensions\user_default\kinema"),
    (Join-Path $verRoot "scripts\addons\kinema")
)

$found = $false
foreach ($p in $paths) {
    if (-not (Test-Path $p)) { continue }
    $found = $true
    $item = Get-Item $p -Force
    if ($item.LinkType -eq "Junction") {
        Write-Host "[info] Junction を削除: $p"
        & cmd /c rmdir "`"$p`""
    } else {
        Write-Host "[warn] Junction ではないため Remove-Item: $p"
        Remove-Item -Path $p -Recurse -Force
    }
}

if (-not $found) {
    Write-Host "[info] kinema のインストールは見つかりませんでした"
    return
}

Write-Host "[done] アンインストール完了"
