# Changelog

[Keep a Changelog](https://keepachangelog.com/) 形式。

## [Unreleased]

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
