# kinema

Blender 5.x 向け **カメラワークフロー支援アドオン**。
旧 cineflow の Follow / LookAt / Noise を吸収しつつ、Camera 単位の Preset 管理・全方位カメラ配置・キーフレーム支援・設定コピペを追加した後継。

GitHub: https://github.com/hakuseiyato/kinema (Private)

## 機能サマリー

| カテゴリ | 機能 |
|---|---|
| **Camera Preset** | Camera オブジェクト 1 つ = 1 Preset。所属コレクションごとに折り畳みグループで表示 |
| **Quick Start** | ワンクリックで Preset Root + サンプル Camera を生成 |
| **Source 追加** | Capture View（現在のビューから新規カメラ）/ Add Selected（選択中カメラを Preset 登録） |
| **Instance** | Preset を Load して複製。Duplicate で関連オブジェクトごと丸ごとコピー |
| **Follow** | 球面 Euler XYZ で target 周りに配置。Front / Right / Back / Left プリセット |
| **Auto LookAt** | LookAt Target 未指定時、Follow Target を自動注視 |
| **Y 軸 Roll** | カメラの傾き（LookAt 無効時のみ反映、Track To 制約のため） |
| **Lens / Shift** | 焦点距離・カメラシフトを Instance パネルから直接編集 |
| **Depth of Field** | use_dof / focus_object / focus_distance / aperture (fstop, blades, rotation, ratio) |
| **Noise** | 手振れノイズ (位置/回転 / 周波数 / シード) |
| **Damping** | FPS 非依存 + 実時間ハイブリッドで再生中/停止中ともふんわり追従 |
| **Workspace** | "Kinema" 専用 Workspace を append/remove |
| **キーフレーム** | Key All（一括）/ Auto Keyframe 連携 / Kinema Camera Keying Set 自動生成 |
| **設定コピペ** | カテゴリ別 (Lens/Shift / DoF / Follow / LookAt / Noise) + 一括 |
| **Diagnostics** | handler 重複・参照切れ・cineflow 共存・Workspace/Keying Set 状態を Info 出力 |
| **cineflow 共存** | enabled なら warning + handler 登録 skip、ボタンで切替 |

## インストール（dev install）

```powershell
cd C:\Work\Yato\Claude\kinema\scripts
.\dev_install.ps1 -BlenderVersion "5.0"
```

`%APPDATA%\Blender Foundation\Blender\<ver>\extensions\user_default\kinema` に Junction が張られる。

> `blender_manifest.toml` を持つ Extensions 形式なので `scripts\addons` ではなく `extensions\user_default` 側に置く必要があります（dev_install.ps1 が自動でその場所を選択）。

Blender 5.0 を起動 → `Edit > Preferences > Add-ons` で "Kinema" を検索 → 有効化。

## 動作確認

[docs/manual_smoke_test.md](docs/manual_smoke_test.md) を参照。

## アーキテクチャ

```
src/kinema/
├── __init__.py               # bl_info / register / _deferred_setup
├── blender_manifest.toml
├── preferences.py            # AddonPreferences
├── config/
│   └── constants.py
├── data/                     # PropertyGroup 群
│   ├── preset_item.py        # スキャン結果の 1 行
│   ├── instance_item.py      # ロード済みカメラの 1 行（+ update callback で _apply_now）
│   ├── scene_settings.py     # Scene.kinema
│   └── wm_settings.py        # WindowManager.kinema_clipboard
├── ops/                      # Operator 群（基底は _base.KinemaOperator）
│   ├── preset_ops.py         # Scan / Load / Toggle Collapse
│   ├── instance_ops.py       # Duplicate / Unload / Preview / Apply Lens / Refresh / Set Follow Angle
│   ├── source_ops.py         # Quick Start / Init Root / Capture View / Add Selected
│   ├── workspace_ops.py
│   ├── handler_ops.py        # cineflow 共存・handler toggle
│   ├── diagnostics_ops.py
│   ├── keyframe_ops.py       # Key All / Rebuild Keying Set / Toggle Auto KF
│   └── clipboard_ops.py      # Copy/Paste（カテゴリ別 + 一括）
├── runtime/
│   ├── handlers.py           # frame_change_pre / depsgraph_update_post / load_post
│   ├── damping.py            # FPS+実時間ハイブリッド dt
│   ├── follow_lookat.py      # Euler XYZ + Track To 経由の LookAt Proxy
│   ├── noise.py
│   └── instance_dispatcher.py # 全 Instance を 1 ステップ適用
├── ui/
│   ├── main_panel.py
│   ├── presets_view.py       # UIList（グループ折り畳み）
│   └── instances_view.py     # UIList（#1/#2 番号 + DUP 警告）
└── utils/
    ├── collections.py        # scan_presets_with_headers / duplicate_camera_as_instance
    ├── source_init.py        # ensure_preset_root / quick_start
    ├── naming.py             # _001 採番
    ├── tags.py
    ├── props.py
    ├── refs.py               # safe_object / safe_collection
    └── clipboard.py          # copy/paste 純粋ロジック
```

## テスト

```powershell
cd C:\Work\Yato\Claude\kinema
python tests\test_naming.py
python tests\test_tags.py
python tests\test_damping.py
python tests\test_clipboard.py
```

bpy 非依存の純粋ロジックのみ。UI / Modal / Operator は手動 smoke test で。

## ライセンス

GPL-3.0-or-later
