# Manual Smoke Test

beta1 系の全機能を手動で確認する手順。Blender 5.0 を完全終了 → 再起動 / Disable → Enable してから始めること。

## 1. インストール確認

```powershell
cd C:\Work\Yato\Claude\kinema\scripts
.\dev_install.ps1 -BlenderVersion "5.0"
```

Blender 起動 → `Edit > Preferences > Add-ons` で **Kinema** を有効化。

`Properties > Scene > Kinema` パネルが見えれば OK。

## 2. cineflow 衝突確認

cineflow が enabled の場合、パネル先頭に **赤い警告バナー**が出る:

```
⚠ cineflow が enabled です
   kinema の frame_change handler は待機中
   [Disable cineflow & enable kinema handlers]
```

ボタン → cineflow 無効化 + kinema handler 有効化。

## 3. Workspace

`Workspace` ボックスの **Create Kinema Workspace** ボタンで `Kinema` タブが上部に追加される。
**Remove Kinema Workspace** で消える（Blender 5.x の `bpy.ops.workspace.delete` 経由）。

## 4. Preset ソース準備

### Quick Start (連打可)

`Quick Start (+1 Sample)` を 3 回押す → `Sample_Camera` / `Sample_Camera_001` / `Sample_Camera_002` が `Kinema_Presets` 配下に追加される。

### Capture View / Add Selected

- **Capture View**: 現在の 3D ビュー視点で新規 Camera を作って Preset 登録
- **Add Selected**: 選択中の既存 Camera を Preset 登録

### コレクション階層を作って折り畳み確認

Outliner で `Kinema_Presets` 配下に `TOP` / `SIDE` という空コレクションを作り、それぞれにカメラを 2〜3 個ずつ入れる:

```
Kinema_Presets/
├── TOP/
│   ├── Sample_Camera.010
│   ├── Sample_Camera.011
└── SIDE/
    ├── Sample_Camera.002
    ├── Sample_Camera.003
```

**Scan アイコン** で再走査 → グループヘッダで折り畳めることを確認:

```
▼ TOP (2)
  Sample_Camera.010
  Sample_Camera.011
▼ SIDE (2)
  Sample_Camera.002
  Sample_Camera.003
```

▼/▶ クリックで折り畳み・展開できる。

## 5. Load Preset → Instance

プリセット 1 つを選択 → **Load Selected Preset**。Instances 一覧に `#1` で表示。複数 Load → `#1 / #2 / #3` で番号区別される。

カスタムプロパティ `kn_default_lens` が設定された Preset の場合、Load 時にカメラのレンズに自動適用される（0 以外なら）。

## 6. Active Instance パネル

選択中の Instance に対して以下が編集可能：

### Lens / Shift

- `Lens (mm)` スライダー + Apply ボタン
- Shift X / Y（Camera Data 直接）

### Depth of Field

- `Depth of Field` チェック ON
- Focus Object（指定すると Focus Distance が隠れる）
- F-Stop / Blades / Rotation / Ratio

### Follow

- Target にスザンヌ等を指定
- **Rotation (X / Y / Z)**:
  - X: 上下角（正値=見下ろし）
  - Y: ロール（LookAt 無効時のみ反映）
  - Z: 水平回り（0=正面, 90=右, 180=背後, -90=左）
- Front / Right / Back / Left プリセット
- Distance / Height / Side Offset / Follow Damping
- Auto Look at Follow Target チェック

### LookAt

- Target 明示指定（無し + Auto Look at ON なら Follow Target を見る）
- 自動連動中は `→ Auto: <object 名>` が表示
- LookAt Damping

### Noise

- 手振れノイズ（Pos / Rot / Frequency / Seed）

## 7. Damping 動作確認

1. Follow Damping = 0.3 に設定
2. **再生中**: Suzanne を G で移動 → カメラがふんわり追従（フレーム dt）
3. **停止中**: Suzanne を G で移動 → カメラがふんわり追従（実時間 dt）
4. Damping = 0 → スナップ即追従
5. Damping = 1 → ほぼ動かない

## 8. Duplicate Instance

Instances ヘッダの Duplicate アイコン、または各行のアイコンで複製。Camera + 親 + Constraint Target も丸ごとコピーされ、Follow / LookAt / Noise / Lens / DoF / Shift のパラメータも引き継ぐ。

複製先と元の Camera Data は **独立**（複製先で Lens を変えても元には影響しない）。

## 9. キーフレーム

### Auto Keyframe (赤丸)

Active Instance ヘッダの **REC アイコン**で Blender 標準の Auto Keyframe（赤丸）を ON/OFF。点灯中はスライダー操作のたびに Instance プロパティが自動キー化される。

Instance プロパティは `_apply_now` で **所有 Scene** を逆引きしてキーが打たれる（複数 Scene 構成でも正しい Scene にキーが入る）。

### Key All

**Key All** ボタンで Active Instance の以下を現フレームに一括キー:
- Camera Object: location / rotation_euler
- Camera Data: lens / shift_x / shift_y
- Camera Data.dof: use_dof / focus_distance / aperture (fstop, blades, rotation, ratio)
- Instance: lens_mm / follow_distance / follow_rot_x/y/z / follow_height / follow_side / follow_damping / lookat_damping / noise_*

### Keying Set

**KEYINGSET アイコン** で `Kinema Camera` Keying Set を Active Instance ベースで自動生成。タイムラインヘッダの Keying Set ドロップダウンで選択すると、Blender 標準の I キーで同じ項目セットを一発キー。

> 注: Keying Set の path は作成時の Scene を target ID として固定するため、別 Scene で同じ Keying Set を使うと最初の Scene にキーが飛ぶ。複数 Scene 運用時は Scene 切替後に Rebuild を押し直すこと。

## 10. 設定コピペ

### 一括

Active ヘッダの **Copy All（COPYDOWN）/ Paste All（PASTEDOWN）** で全部一括コピペ。

### カテゴリ別

各セクション（Lens/Shift / DoF / Follow / LookAt / Noise）のヘッダ右端のアイコンで個別 Copy / Paste。例:

1. Instance #1 で Follow を細かく設定 → Follow セクションの 📋⬇
2. Instance #2 を選択 → Follow セクションの 📋⬆ で同じ Follow 設定だけ反映、DoF は維持

PointerProperty（Follow Target / LookAt Target / Focus Object）は名前で保存・復元。同名オブジェクトが見つからなければ None になる。

クリップボードは `WindowManager.kinema_clipboard` の JSON 文字列。Blender を閉じるまで保持される。

## 11. Diagnostics

`Diagnostics` ボックスの **Run** ボタン → Info Area / System Console に状態出力:

```
[OK] frame_change_pre: kinema=1, cineflow=0
[OK] depsgraph_update_post: kinema=1, cineflow=0
[OK] load_post: kinema=1, cineflow=0
[OK] cineflow: disabled
[OK] Instance 重複参照: なし（合計 N）
[OK] 参照切れ Instance: なし
[OK] Collection 'Kinema_Presets': 存在
[OK] Collection 'Kinema_Instances': 存在
[OK] Workspace 'Kinema': 作成済み
[OK] Keying Set 'Kinema Camera': N paths
```

Disable → Enable を 3 回繰り返した後にこのボタンを押して `kinema=1` のままなら handler 重複防止が効いている証拠。

## 12. 確認チェックリスト

- [ ] Preferences で Kinema が有効化できる
- [ ] cineflow 警告 → Disable & Enable が動く
- [ ] Workspace 作成 / 削除
- [ ] Quick Start が連打で増える
- [ ] Capture View / Add Selected
- [ ] コレクション別グループの折り畳み (▼ / ▶)
- [ ] Load Preset で `#1 / #2 / #3` 区別される
- [ ] Preset の kn_default_lens がカメラに反映される
- [ ] Lens / Shift / DoF が編集できる
- [ ] Follow Rotation X/Y/Z + Front/Right/Back/Left プリセット
- [ ] Auto Look at Follow Target で「→ Auto: ...」表示
- [ ] Damping: 再生中も停止中もふんわり追従
- [ ] Duplicate Instance（パラメータ + 関連オブジェクトコピー）
- [ ] Auto Keyframe（REC）ON 中のスライダー操作で自動キー
- [ ] Key All ボタンで全項目キー
- [ ] Rebuild Keying Set でエラーなく "Kinema Camera" 生成
- [ ] Copy / Paste（一括 + カテゴリ別）
- [ ] Diagnostics Run で全項目 OK
- [ ] Disable → Enable 3 回繰り返しても handler が `kinema=1` のまま
