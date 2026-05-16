# Kinema spike0

Blender 5.x の API が kinema 本体実装に耐えるかを確認するための、最小テストアドオン。

## 検証項目（8 点）

| # | 検証内容 | 確認方法 |
|---|---|---|
| 1 | `blender_manifest.toml` がアドオンとして認識される | Preferences > Add-ons で "Kinema spike0" が表示・有効化できる |
| 2 | `SpaceImageEditor.draw_handler_add(POST_PIXEL)` で矩形描画 | "Toggle Draw Handler" 押下 → Image Editor に青いクワッドが見える |
| 3 | `gpu.shader.from_builtin('UNIFORM_COLOR')` が動く | 同上（クワッドが描けていれば OK） |
| 4 | `blf.draw()` with `font_id=0` でテキスト描画 | クワッドの上に "Kinema spike0: gpu+blf OK" が見える |
| 5 | Modal Operator が起動・終了、`REGISTER, UNDO` でアンドゥが効く | "Run Modal (commit)" → マウス左右で値変化 → 左クリック確定 → `Ctrl+Z` で値が元に戻る |
| 6 | Modal の `CANCELLED` 終了時に undo に積まれない | "Run Modal (cancel only)" → マウス動かす → ESC で終了 → `Ctrl+Z` を押しても何も起こらない（直前の commit が戻る、または "Nothing to undo" が出る） |
| 7 | `IMAGE_HT_header.append` が表示され `unregister` で消える | Image Editor のヘッダに "K-spike0" が表示される → アドオン無効化で消える |
| 8 | `Window.as_pointer()` / `Area.as_pointer()` の安定性 | "Snapshot Pointers" → Workspace 切替 / Area ドラッグ移動 / Image Editor を 2 分割 → "Check Pointers" で結果を見る |

## 実行手順

### 1. 既存の誤インストールを剥がす（v1 で `scripts\addons` に張ってしまっていた場合）

```powershell
cd C:\Work\Yato\Claude\kinema\spike0\scripts
.\dev_uninstall.ps1
```

> v1 の dev_install.ps1 は `scripts\addons` に Junction を作っていました。`blender_manifest.toml`
> を持つアドオンは Blender 5.x の **Extensions システム** 扱いで、`extensions\user_default`
> に置かないと認識されません。新しい dev_install.ps1 は正しい場所に張り直します。

### 2. インストール（Junction）

```powershell
cd C:\Work\Yato\Claude\kinema\spike0\scripts
.\dev_install.ps1
# 特定バージョンに張りたい場合:
# .\dev_install.ps1 -BlenderVersion "5.0"
```

`%APPDATA%\Blender Foundation\Blender\<最新>\extensions\user_default\kinema_spike0`
に Junction が張られる。バージョン自動検出は最新（例: 5.1）を優先。

### 3. Blender 5.x 起動 → アドオン有効化

**重要**: Blender が起動中なら一度完全に終了してから起動し直す。
`blender_manifest.toml` は Blender 起動時にしかスキャンされない。

1. Blender を完全終了 → 起動
2. `Edit > Preferences > Add-ons`（または `Get Extensions` タブ）で
   "Kinema spike0" を検索して有効化
3. **(1)** これが有効化できれば OK

### 3. Image Editor を開く

1. 任意の Area を `Image Editor` に切替
2. サイドバー（N キー）を開く → `Kinema spike0` タブが見える
3. **(7)** ヘッダに "K-spike0" 表示 OK

### 4. 描画系テスト (2)(3)(4)

1. `Toggle Draw Handler` をクリック
2. Image Editor の左下に **青いクワッド + テキスト** が出れば OK
3. もう一度クリックで消える

### 5. Modal + Undo テスト (5)

1. `Run Modal (commit)` をクリック
2. マウスを左右に動かす → `value` が変化することを目視
3. 左クリックで確定
4. `Ctrl+Z` を押す → `value` が Modal 起動前の値に戻れば OK

### 6. Modal CANCELLED が undo に積まれないか (6)

1. 一度 `Run Modal (commit)` で何かを確定（undo スタックに「直前の commit」を置いておく）
2. 次に `Run Modal (cancel only)` を起動 → マウスを動かす → **ESC** または **右クリック**で終了
3. ここで `Ctrl+Z` を押す
4. **期待**: 直前の commit が undo される（= CANCELLED の Modal は undo に積まれていない）
5. もし「CANCELLED の Modal の起動前の値に戻った」場合は **NG**。spike0_findings に記録して dry-run+apply パターンの fallback を採用する

### 7. Pointer 安定性 (8)

1. Image Editor を 1 つだけ開いた状態で `Snapshot Pointers` をクリック
2. Results に `screen=Layout area_idx=N` が表示される
3. 次のシナリオを順に実行し、その都度 `Check Pointers` をクリックして結果を Results で確認:
   - **a)** そのまま `Check Pointers` → "OK: 一次キー (pointer) も二次キー も成立" が出るはず
   - **b)** Workspace タブを `Modeling` 等に切り替える → 戻ってきて `Check Pointers`
   - **c)** Image Editor の境界をドラッグして Area サイズを変える → `Check Pointers`
   - **d)** Image Editor を 2 つに分割 → 分割後の片方で `Check Pointers`
   - **e)** Image Editor を一度閉じて、別の Area を Image Editor に切替 → `Check Pointers`
4. **判定**:
   - 全部 "pointer 一致" → 一次キー (pointer) のみで足りる
   - "pointer 不一致 だが screen+index で復帰可" が 1 つでもあれば、本体実装で **二次キー fallback 必須**
   - "両方とも見つからず" が出たケースを記録 → そのシナリオでは自動 OFF + 警告が必要

### 8. アンインストール

```powershell
cd C:\Work\Yato\Claude\kinema\spike0\scripts
.\dev_uninstall.ps1
```

## 結果のフィードバック先

各検証項目の結果（OK/NG とコメント）を `C:\Work\Yato\Claude\kinema\docs\spike0_findings.md` に書き残す。NG が出た項目は v7 プランの「spike0 NG 時の fallback 設計」テーブルから採用すべき方針を選択して記録。
