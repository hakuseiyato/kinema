# kinema dev install: Junction を Blender 5.x の extensions/user_default に張る
#
# blender_manifest.toml を持つ Extensions システム扱いなので、
# %APPDATA%\Blender Foundation\Blender\<ver>\extensions\user_default\<addon>
# に Junction を作る（scripts\addons では認識されない）。
#
# 使い方:
#   .\dev_install.ps1                  # userpref.blend が最新のバージョンに張る
#   .\dev_install.ps1 -BlenderVersion "5.0"
#
# 既存 Junction/フォルダは退避してから新規 Junction を作成。
# 過去に scripts\addons に置かれていた kinema があれば自動的に剥がす。

[CmdletBinding()]
param(
    [string]$BlenderVersion = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$srcAddon = Join-Path $repoRoot "src\kinema"

if (-not (Test-Path $srcAddon)) {
    throw "ソースが見つかりません: $srcAddon"
}

$blenderUserRoot = Join-Path $env:APPDATA "Blender Foundation\Blender"
if (-not (Test-Path $blenderUserRoot)) {
    throw "Blender ユーザー設定が見つかりません: $blenderUserRoot"
}

# バージョン自動検出: userpref.blend の更新日時で「現役」を判定する
# （バージョン番号最大ではなく、最後に起動された版を選ぶ）
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
    Write-Host "[info] Blender バージョン自動検出: $BlenderVersion (userpref.blend が最新)"
    Write-Host "       他に張りたければ -BlenderVersion '5.0' で明示してください"
}

$verRoot = Join-Path $blenderUserRoot $BlenderVersion

# ---- 旧 scripts\addons 配下の誤 Junction を剥がす ----
$legacyTarget = Join-Path $verRoot "scripts\addons\kinema"
if (Test-Path $legacyTarget) {
    $legacyItem = Get-Item $legacyTarget -Force
    if ($legacyItem.LinkType -eq "Junction") {
        Write-Host "[warn] 旧 Junction を scripts\addons から削除: $legacyTarget"
        & cmd /c rmdir "`"$legacyTarget`""
    } else {
        $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
        $legacyBackup = "$legacyTarget.backup_$stamp"
        Write-Host "[warn] 旧フォルダを退避: $legacyBackup"
        Move-Item -Path $legacyTarget -Destination $legacyBackup
    }
}

# ---- Extensions パスに Junction を作る ----
$extensionsDir = Join-Path $verRoot "extensions\user_default"
if (-not (Test-Path $extensionsDir)) {
    Write-Host "[info] extensions/user_default ディレクトリを作成: $extensionsDir"
    New-Item -ItemType Directory -Path $extensionsDir -Force | Out-Null
}

$target = Join-Path $extensionsDir "kinema"

if (Test-Path $target) {
    $item = Get-Item $target -Force
    if ($item.LinkType -eq "Junction") {
        Write-Host "[info] 既存 Junction を剥がして張り直し: $target"
        & cmd /c rmdir "`"$target`""
    } else {
        $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
        $backup = "$target.backup_$stamp"
        Write-Host "[info] 既存フォルダを退避: $backup"
        Move-Item -Path $target -Destination $backup
    }
}

Write-Host "[info] Junction を作成:"
Write-Host "       $target"
Write-Host "    -> $srcAddon"
New-Item -ItemType Junction -Path $target -Target $srcAddon | Out-Null

Write-Host ""
Write-Host "[done] インストール完了。Blender $BlenderVersion を起動し、"
Write-Host "       Edit > Preferences > Add-ons で 'Kinema' を検索して有効化してください。"
Write-Host ""
Write-Host "       既に起動中の場合は Blender を一度完全に終了してから再起動してください"
Write-Host "       (blender_manifest.toml は起動時のみスキャンされるため)。"
