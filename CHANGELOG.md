# Changelog

[Keep a Changelog](https://keepachangelog.com/) 形式。

## [Unreleased]

## [2.0.0-alpha1.1] - 2026-05-16

### Added
- **Preset ソース生成のワンクリック化**
  - `utils/source_init.py`: `ensure_preset_root` / `make_empty_preset` /
    `register_camera_as_preset` / `capture_view_as_new_preset` / `quick_start`
    の純粋ロジック層（Yato Project Kit からの呼び出しも想定）
  - `ops/source_ops.py`: 上記の Operator ラッパ（`KINEMA_OT_init_preset_root`、
    `KINEMA_OT_quick_start`、`KINEMA_OT_capture_view_as_preset`、
    `KINEMA_OT_add_selected_cameras_as_presets`）
  - UI: Preset Root が未準備 / 空の時に Quick Start バナーを表示。準備済の時も
    Capture View / Add Selected ボタンを Presets ボックスに常設
- `docs/source_init_spec.md`: Yato Project Kit に引き継ぐための API 仕様

### Changed
- `docs/alpha1_smoke_test.md` の Step 5 をワンクリック手順優先に書き換え
- 動作確認チェックリストに Quick Start / Capture View / Add Selected を追加

## [2.0.0-alpha1] - 2026-05-16

### Added
- 初期リポ骨格 (`src/kinema/` の `config/data/ops/ui/runtime/utils/importers`)
- `blender_manifest.toml` (Extensions システム対応) と最小 `bl_info`
- Properties > Scene > Kinema パネル（Cameras タブ）
- Preset スキャン / Load / Instance 一覧
- Follow / LookAt / Noise の cineflow からの移植（`runtime/follow_lookat.py` `runtime/noise.py`）
- 純粋ロジックの damping math を `runtime/damping.py` に分離（bpy 非依存・テスト可能）
- handler 重複防止 (`runtime/handlers.py`)
- cineflow 共存時の handler 登録 skip + 警告バナー + 切替ボタン
- 専用 Workspace "Kinema" の作成・削除 Operator
- PointerProperty 安全アクセス (`utils/refs.py`)
- 自動採番 (`utils/naming.py`)
- カンマ区切りタグ集約 (`utils/tags.py`)
- AddonPreferences (keymap backup placeholder / Pose step enum / auto-enable handler)
- dev_install.ps1 (Junction、userpref.blend 更新日時で現役判定、Extensions パス対応)
- 純粋ロジックの単体テスト (`tests/test_naming.py`, `test_tags.py`, `test_damping.py`)
- 動作確認手順 (`docs/alpha1_smoke_test.md`)

### Notes
- 旧 cineflow とは別アドオンとして共存可能（手動無効化推奨）
- 描画ホスト方針: Image Editor を **専用 Workspace で包む**（Yato さん希望）
- alpha2 で Pose タブ（カメラ直接操作 UI）を追加予定
- beta1 で独自タイムライン UI 基盤を実装予定
