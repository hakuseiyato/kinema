# spike0 dev install: Junction を Blender 5.x の extensions/user_default に張る
#
# blender_manifest.toml を持つアドオンは Extensions システム扱いになるため、
# %APPDATA%\Blender Foundation\Blender\<ver>\extensions\user_default\<addon>
# に Junction を作る（scripts\addons では認識されない）。
#
# 使い方:
#   .\dev_install.ps1                  # 最新の Blender バージョンを自動検出
#   .\dev_install.ps1 -BlenderVersion "5.0"
#   .\dev_install.ps1 -BlenderVersion "5.1"
#
# 既存のフォルダ/Junction はタイムスタンプ付きで退避してから新規 Junction を作成。
# また、過去に scripts\addons に置かれていた kinema_spike0 があれば自動的に剥がす。

[CmdletBinding()]
param(
    [string]$BlenderVersion = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$srcAddon = Join-Path $repoRoot "src\kinema_spike0"

if (-not (Test-Path $srcAddon)) {
    throw "ソースが見つかりません: $srcAddon"
}

# Blender ユーザー設定ディレクトリ
$blenderUserRoot = Join-Path $env:APPDATA "Blender Foundation\Blender"
if (-not (Test-Path $blenderUserRoot)) {
    throw "Blender ユーザー設定が見つかりません: $blenderUserRoot"
}

# バージョン自動検出: config\userpref.blend の更新日時が最新の版を「現役」と判定する
# （単に最新バージョン番号を選ぶと、過去に作られたが未使用の 5.1 などを誤選択する）
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
    Write-Host "       他バージョンに張りたい場合は -BlenderVersion '5.0' のように明示してください"
}

$verRoot = Join-Path $blenderUserRoot $BlenderVersion

# ---- 既存の誤った Junction（scripts\addons 配下）を剥がす ----
$legacyTarget = Join-Path $verRoot "scripts\addons\kinema_spike0"
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

# ---- Extensions パス（5.x の正しい場所）に Junction を作る ----
$extensionsDir = Join-Path $verRoot "extensions\user_default"
if (-not (Test-Path $extensionsDir)) {
    Write-Host "[info] extensions/user_default ディレクトリを作成: $extensionsDir"
    New-Item -ItemType Directory -Path $extensionsDir -Force | Out-Null
}

$target = Join-Path $extensionsDir "kinema_spike0"

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
Write-Host "       Edit > Preferences > Get Extensions / Add-ons で"
Write-Host "       'Kinema spike0' を検索して有効化してください。"
Write-Host ""
Write-Host "       既に起動中の場合は Blender を一度終了してから再起動してください"
Write-Host "       (blender_manifest.toml は起動時のみスキャンされるため)。"
