# kinema 開発ワークフロー

dev install（Junction）でソースを Blender に貼り付けて開発する前提の運用手順。
判断軸: 変更内容によって `F3 > Reload Scripts` で済むか、Blender 再起動 / Disable→Enable が要るか。

## 初回セットアップ

```powershell
# クローン
cd C:\Work\Yato\Claude\
git clone https://github.com/hakuseiyato/kinema.git

# Junction 張り
cd kinema\scripts
.\dev_install.ps1 -BlenderVersion "5.0"
```

`%APPDATA%\Blender Foundation\Blender\5.0\extensions\user_default\kinema` に Junction が張られる。
Blender 起動 → Preferences > Add-ons で "Kinema" を有効化。

## ソース編集 → 反映の判断

| 変更内容 | 反映方法 | 備考 |
|---|---|---|
| 関数の中身 / コメント / 文字列 | **F3 > Reload Scripts** | 最速 |
| Operator の execute() ロジック | **F3 > Reload Scripts** | bl_idname を変えなければ OK |
| Panel draw() の中身 | **F3 > Reload Scripts** | 即反映 |
| 新規 Operator / Panel / UIList 追加 | **F3 > Reload Scripts** で多くは OK | register に組み込み済が条件 |
| **PropertyGroup のフィールド追加・型変更** | **Disable→Enable 必須** | Scene が古い型を保持 |
| `Scene.<x> = PointerProperty(type=...)` の変更 | **Disable→Enable 必須** | 同上 |
| `register()` / `unregister()` の呼び出し順 | **Disable→Enable 推奨** | 不整合になりやすい |
| `bl_idname` 変更 | **Disable→Enable 必須** | 旧 ID が残留 |
| `bl_info` 編集 | **再起動推奨** | 表示更新 |
| **`blender_manifest.toml` 編集** | **Blender 再起動必須** | Extensions スキャンは起動時のみ |
| 新規ファイル追加・既存ファイル削除 | **再起動推奨** | importlib キャッシュ |

> 詳細判断ガイド: `F:\Obsidian_memo\Obsidian\03_Resources\Tools\Blender_Addon_Reload_Guide.md`

## Disable→Enable の最速手順

1. `Edit > Preferences > Add-ons`
2. "Kinema" の ✓ を **OFF**
3. すぐ ✓ を **ON** に戻す

これで PropertyGroup が再登録される。`.blend` を保存・再オープンしなくて済む。

## 完全リセット

何か壊れた時:

```powershell
# 既存 Junction を剥がして張り直し
cd C:\Work\Yato\Claude\kinema\scripts
.\dev_uninstall.ps1 -BlenderVersion "5.0"
.\dev_install.ps1 -BlenderVersion "5.0"
```

加えて Junction 先の `__pycache__/` を消すと完全クリーン:

```powershell
Remove-Item -Recurse -Force "$env:APPDATA\Blender Foundation\Blender\5.0\extensions\user_default\kinema\**\__pycache__"
```

## バージョン管理 / リリース

### バージョン更新

```powershell
# 1. blender_manifest.toml の version を編集（"2.0.0-beta1.11" 等）
# 2. src/kinema/__init__.py の bl_info["version"] を編集（(2, 0, 0) のタプル形式）
# 3. 整合性確認
cd C:\Work\Yato\Claude\kinema\scripts
.\check_version.ps1
# → [OK] base version 一致: 2.0.0
```

### 配布 ZIP のローカル生成

```powershell
cd C:\Work\Yato\Claude\kinema\scripts
.\build_zip.ps1
# → dist\kinema-v<version>.zip
```

`__pycache__` / `.pyc` は除外される。

### GitHub Release

```powershell
git tag v2.0.0-beta1.11
git push origin v2.0.0-beta1.11
```

タグ push を GitHub Actions が検知 → ZIP 自動生成 → Release に添付。`-` を含むタグは prerelease 扱い。

## テスト

```powershell
cd C:\Work\Yato\Claude\kinema
python tests\test_naming.py
python tests\test_tags.py
python tests\test_damping.py
python tests\test_clipboard.py
python tests\test_json_io.py
```

すべて bpy 非依存の純粋ロジック。UI / Modal / Operator は [docs/manual_smoke_test.md](manual_smoke_test.md) の手順で。

## よくあるトラブル

### ボタンを押してもエラー、または効かない

1. **System Console を見る** (`Window > Toggle System Console`)
2. スタックトレースのファイル名と行番号を確認
3. **Reload Scripts** か **Disable→Enable** を試す
4. それでも駄目なら Blender 完全再起動

### 「アドオン一覧に Kinema が出ない」

- `blender_manifest.toml` を変更したのに反映されていない場合は **Blender 起動時にしか読まれない**
- `dev_install.ps1` が `extensions/user_default/` ではなく `scripts/addons/` に張っていないか確認（Extensions 形式は前者必須）
- バージョン自動検出が違うバージョンを選んでいる可能性: `-BlenderVersion "5.0"` で明示

### handler が二重登録される

`Properties > Scene > Kinema > Diagnostics > Run` を押して `frame_change_pre: kinema=2` のように 2 以上になっていたら重複。`Disable→Enable` で解消するはず。

### cineflow と競合する

cineflow が enabled だと kinema は handler 登録を待機する。kinema パネル先頭の警告バナーから "Disable cineflow & enable kinema handlers" を押す。または `Import from cineflow` で先にデータを取り込んでから cineflow を無効化。
