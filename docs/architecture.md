# kinema アーキテクチャ

> CLAUDE.md 規約「architecture.md は doc 配下に置く / プロジェクト概要・依存・構成を記述」に従う。

## プロジェクト概要

- **アドオン名**: kinema
- **形式**: Blender 5.x Extensions (`blender_manifest.toml` を持つ)
- **位置づけ**: 旧 cineflow（Cinemachine 風 Follow/LookAt/Noise）の後継。Camera オブジェクト単位の Preset 管理、全方位 Follow（Euler XYZ）、設定コピペ、キーフレーム支援、cineflow からの取り込みを提供
- **対象 Blender**: 5.0+（`blender_manifest.toml: blender_version_min = "4.2.0"`）
- **依存パッケージ**: Blender 同梱の `bpy / mathutils / bpy_extras` のみ。サードパーティ依存なし

## 技術スタック

| 種別 | 内容 |
|---|---|
| 言語 | Python 3.11+（Blender 5.x 同梱版） |
| Blender API | bpy / bpy.types / bpy.props / mathutils / bpy.app.handlers |
| 配布 | Blender Extensions（`extensions/user_default/` 配下に Junction or ZIP） |
| ビルド | PowerShell スクリプト（`scripts/build_zip.ps1`） + GitHub Actions |
| テスト | pytest 風の純粋ロジックテスト（bpy 非依存、5 ファイル） |

## ディレクトリ構成

```
kinema/
├── src/kinema/                  # アドオン本体（Junction で配布先に貼る対象）
│   ├── __init__.py              # bl_info / register / unregister / 遅延 setup
│   ├── blender_manifest.toml    # Extensions 形式のメタデータ
│   ├── preferences.py           # AddonPreferences（最小実装）
│   ├── config/
│   │   └── constants.py         # KN_* キー名・デフォルトコレクション名・Workspace 名
│   ├── data/                    # PropertyGroup 定義
│   │   ├── preset_item.py       # Preset 一覧の 1 行（is_header / group / camera 情報）
│   │   ├── instance_item.py     # ロード済みカメラ 1 行（Follow/LookAt/Noise + Solo/Lock）
│   │   ├── scene_settings.py    # Scene.kinema（root 名 + presets/instances Collection）
│   │   └── wm_settings.py       # WindowManager.kinema_clipboard（Copy/Paste 用）
│   ├── ops/                     # Operator 群（基底 _base.KinemaOperator）
│   │   ├── _base.py             # UNDO flag + tag_redraw 自動化
│   │   ├── preset_ops.py        # Scan / Load / Toggle Collapse
│   │   ├── instance_ops.py      # Duplicate / Unload / Preview / Set Follow Angle 等
│   │   ├── source_ops.py        # Quick Start / Init Root / Capture View / Add Selected
│   │   ├── workspace_ops.py     # Create / Remove Kinema Workspace
│   │   ├── handler_ops.py       # cineflow 切替 + handler toggle
│   │   ├── diagnostics_ops.py   # Run Diagnostics
│   │   ├── keyframe_ops.py      # Key All / Rebuild Keying Set / Toggle Auto KF
│   │   ├── clipboard_ops.py     # Copy/Paste（カテゴリ別 + 一括）
│   │   ├── io_ops.py            # JSON Export / Import
│   │   └── cineflow_import.py   # 旧 cineflow Instance 取り込み
│   ├── runtime/                 # frame_change/depsgraph で動くロジック
│   │   ├── handlers.py          # handler 登録/解除 + cineflow 共存制御
│   │   ├── damping.py           # FPS+実時間ハイブリッド dt（純粋ロジック）
│   │   ├── follow_lookat.py     # Euler XYZ Follow + 自前 LookAt + Roll
│   │   ├── noise.py             # delta_location/euler への手振れ書込
│   │   └── instance_dispatcher.py # 全 Instance 走査して 1 ステップ適用
│   ├── ui/                      # Panel / UIList
│   │   ├── main_panel.py        # Properties > Scene > Kinema
│   │   ├── presets_view.py      # UIList（折り畳みグループ）
│   │   └── instances_view.py    # UIList（#1/#2 + Solo/Mute/Lock 3 アイコン + DUP 警告）
│   └── utils/                   # 純粋ロジック・bpy 薄ラッパ
│       ├── collections.py       # scan_presets_with_headers / duplicate_camera_as_instance
│       ├── source_init.py       # ensure_preset_root / quick_start
│       ├── naming.py            # _001 採番
│       ├── tags.py              # カンマ区切りタグ
│       ├── props.py             # safe_get/safe_set
│       ├── refs.py              # safe_object/safe_collection
│       ├── clipboard.py         # copy_fields / paste_fields（純粋ロジック）
│       └── json_io.py           # schema_version 1 のエクスポート/インポート
├── scripts/
│   ├── dev_install.ps1          # Junction を extensions/user_default に張る
│   ├── dev_uninstall.ps1
│   ├── build_zip.ps1            # 配布 ZIP 生成（__pycache__ 除外）
│   └── check_version.ps1        # manifest vs bl_info の version 一致確認
├── tests/                       # bpy 非依存の pytest
│   ├── test_naming.py
│   ├── test_tags.py
│   ├── test_damping.py
│   ├── test_clipboard.py
│   └── test_json_io.py
├── docs/
│   ├── architecture.md          # ← 本ファイル
│   ├── manual_smoke_test.md     # 動作確認手順
│   ├── source_init_spec.md      # Yato Project Kit 引継仕様
│   ├── spike0_findings.md       # Blender 5.0 API 検証結果
│   └── dev_workflow.md          # Junction reload と Disable→Enable 手順
├── .github/workflows/
│   └── release.yml              # tag push → ZIP & GitHub Release
├── CHANGELOG.md
├── README.md
├── LICENSE                      # GPL-3.0-or-later
└── .gitignore
```

## データフロー

```
User 操作
   ↓
ui/main_panel    ─ Operator 呼出 ─→  ops/*_ops
                                       ↓
PropertyGroup update_callback  ←─  data.* に書込
   ↓
runtime/instance_dispatcher.dispatch (with バースト抑制)
   ↓
runtime/follow_lookat / noise    →  cam_obj.location / rotation_euler / data.lens
                                    cam_obj.delta_location / delta_rotation_euler
                                    LookAt Proxy Empty の位置 (damping)
```

## 主要設計判断

| 課題 | 採用方針 |
|---|---|
| Preset の単位 | **Camera オブジェクト 1 つ = 1 Preset**（コレクションは表示用グループ） |
| Follow の方向指定 | **Euler XYZ 軸回転**。target.matrix_world 基準で球面配置（X=上下 / Y=ロール / Z=水平回り） |
| LookAt の Roll | **Track To 制約を捨て、自前 quaternion 計算 + local Z 軸回転** で実現 |
| Damping の dt | **フレーム差 + 実時間 のハイブリッド**。再生中・停止中いずれもふんわり追従 |
| 独自タイムライン UI | **撤回**。Blender 標準 Timeline / Dopesheet / VSE で運用、kinema は Camera 管理に集中 |
| Workspace | 専用 `Kinema` Workspace を append/remove。普段のレイアウトに干渉しない |
| キーフレーム | Key All Operator + Auto Keyframe (赤丸) 連携 + Kinema Camera Keying Set 自動生成 |
| 設定コピペ | WindowManager に JSON クリップボード（カテゴリ別スロット 6 + 一括 1） |
| cineflow 共存 | 起動時に検知 → 警告 + handler 登録 skip + Import ボタン |
| 配布 | `scripts/build_zip.ps1` + GitHub Actions（tag push → ZIP & Release） |

## 拡張ポイント

- **Pose タブ**（カメラ直接操作 UI）は将来の課題。Active Instance パネルで簡易にカバー済
- **Yato Project Kit** との連携は `utils/source_init.py` の API を将来の Kit から呼べる形で公開済（`docs/source_init_spec.md`）
- 旧 cineflow データの取り込みは `ops/cineflow_import.py` でカバー
- 異なる Blender バージョンへの対応: `bl_info` と `blender_manifest.toml` の version を `scripts/check_version.ps1` で揃える運用
