# Changelog

[Keep a Changelog](https://keepachangelog.com/) 形式。

## [Unreleased]

## [2.0.0-alpha1.6] - 2026-05-16

### Added
- **Preset 一覧をコレクション別グループ + 折り畳み**
  - `data/preset_item`: `header_collapsed` / `child_count` フィールド追加
  - `utils/collections.scan_presets_with_headers`: グループヘッダ行を挿入
  - `ops/preset_ops.KINEMA_OT_toggle_preset_group_collapse`: ▼/▶ クリックで
    折り畳み
  - `ui/presets_view`: ヘッダ行描画 + `filter_items` で折り畳まれたグループの
    子を非表示
  - 再スキャンしても折り畳み状態を維持

### Changed
- **Quick Start バナーを常設化**: Preset Root に子があっても Quick Start /
  Init Root / Capture View / Add Selected ボタンが常に出る
- バースト抑制を 120Hz → **240Hz** に緩和（4ms 間隔まで dispatch を通す）。
  停止中のスライダー / target 移動のカクつきを軽減

## [2.0.0-alpha1.5] - 2026-05-16

### Fixed
- **Workspace 削除失敗**: `bpy.data.workspaces.remove` が Blender 5.x で存在
  しないため `bpy.ops.workspace.delete()` に切替。フォールバックで
  `bpy.data.batch_remove` も用意
- **Quick Start 連打**: 採番ロジックを Operator 内で明示。
  `bpy.data.collections` と `bpy.data.objects` の両名前空間を見て
  `Sample_Camera / Sample_Camera_001 / Sample_Camera_002 ...` と確実に採番
- **スライダー操作で Damping が効かずスナップする**:
  - `runtime/damping.compute_dt`: バースト連続呼び出しでも 0 を返さなくなった
    （`max(elapsed, 1e-4)`）。0 を返すと damping_alpha が 1.0 (スナップ) に
    なって追従が固くなる挙動が直る
  - 初回呼び出しは引き続き dt=0（スナップ起点）
  - `runtime/shot_dispatcher.dispatch`: バースト抑制（120Hz 超の連続呼び出しを
    間引き）を追加し、スライダー連打や depsgraph の連発で `_apply_now` が暴走
    しないようにした
  - `frame_change_pre` 経路は `force=True` で抑制を回避

## [2.0.0-alpha1.4] - 2026-05-16

### Changed (breaking)
- **Preset 単位を「Camera オブジェクト」に変更**
  - 旧: コレクション = Preset、最初の Camera が代表
  - 新: 各 Camera オブジェクトが 1 Preset。コレクション階層は所属を表す
    "group" として表示にのみ使う
  - 1 つのコレクションに複数の Camera を置いてもすべて Preset として認識される
- `utils/collections.scan_presets`: Preset Root 配下の全 Camera を再帰収集
- `utils/collections.duplicate_camera_as_instance` を新設。Camera + 親チェーン
  + constraint target を最小範囲で複製（cineflow の duplicate_camera_preset 移植）
- `ops/preset_ops.load_preset`: 新 duplicate を使用、`sel.name` は Camera 名
- `utils/source_init.quick_start`: 毎回新サンプル Camera を採番付きで追加
  （旧: root に子があれば何もしない、を撤廃）

### Fixed
- **Damping が再生中に効かない問題**
  - `runtime/damping.compute_dt` をフレーム差 + 実時間 dt のハイブリッドに
  - 再生中の自然な進行: フレーム差で damping
  - 再生中にターゲットを動かす: 同フレーム内の実時間 dt で damping
  - 停止中にターゲットを動かす: 実時間 dt で damping（ふんわり追従）
  - 長期放置後の最初の更新: dt=0 でスナップ
- `runtime/handlers.kinema_depsgraph_update_post`: 再生中 skip を撤回（compute_dt
  側が自動でスナップ/Damping を判定するため）

### UI
- `ui/presets_view`: Camera ベース表示に変更（アイコンを Camera 中心に）
- `ui/main_panel`: Presets 行に "N cameras" 表記

## [2.0.0-alpha1.3] - 2026-05-16

### Changed
- **Preset 一覧を Outliner 階層と一致**：`_` 分割でのグループ化を撤廃し、
  Preset Root を再帰スキャンして「Camera を含むコレクションを Preset、含まない
  親コレクションはグループ」と素直に判定する方式に変更
- `utils/collections.scan_presets`: 再帰スキャン版に書き直し、各エントリに
  `depth` / `parent_path` / `group` を持たせる
- `ui/presets_view`: グループヘッダ行を廃止し、`group` の深さに応じたインデント
  と `in <親名>` の併記で階層を表示
- `runtime/handlers.kinema_depsgraph_update_post`: **再生中は skip** して
  `frame_change_pre` に処理を委譲（Damping が効くようにする）
- `ui/instances_view`: 行頭に `#1 / #2` の index 番号を表示（同名 Instance の
  判別性向上）
- `ops/preset_ops.load_preset`: 重複検知を **警告のみ** に緩和（過剰発動による
  ロールバックを防止）

### Fixed
- Yato さん指摘の「再生停止中だと Damping を持たない動きしか出ない」を
  「停止中はスナップ / 再生中は Damping」のハイブリッドに切り替え
- 旧 `_` 分割グループ化で `Sample_Camera` が "Sample" グループ + "Camera"
  ショート名に分かれてしまい、Outliner と一致しない問題を解消

## [2.0.0-alpha1.2] - 2026-05-16

### Added
- **リアルタイム反映**: Instance の Follow/LookAt/Noise プロパティに update
  callback を仕込み、`depsgraph_update_post` handler も追加。再生していなく
  ても、スライダー操作・ターゲット移動でカメラが即座に追従するようになった
- **Preset UIList の情報量強化**: グループヘッダ・ショート名・元の完全名・
  代表カメラ名・タグ・デフォルト Lens を併記
- **Instance UIList の情報量強化**: コレクション名・ソースプリセット名・
  カメラ名・Lens を併記。**collection_ref 重複検出**で `DUP` 警告アイコン
- **Diagnostics ボタン** (`kinema.run_diagnostics`): handler 登録数・Instance
  重複参照・参照切れ・Workspace 状態を Info Area / System Console に出力
- Load Preset の安全チェック: 既存 Instance と同じ collection_ref が生まれ
  たら即 rollback してエラー報告

### Changed
- `runtime/handlers.py`: `_HOOKS` に `depsgraph_update_post` を追加
- `data/instance_item.py`: 各プロパティに `update=_apply_now` を仕込み
- 重複参照や handler 重複は **UI から目視確認可能** に
  （Yato さん：「Disable→Enable 重複チェック」は Diagnostics ボタンで実行可能）

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
