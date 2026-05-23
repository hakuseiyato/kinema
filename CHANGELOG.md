# Changelog

[Keep a Changelog](https://keepachangelog.com/) 形式。

## [Unreleased]

## [2.0.0-beta2.7] - 2026-05-17

### Changed — Duplicate ルール再設計
- **名前: ベース名 + `_NNN` の連番採番**
  - `utils/naming.next_serial_from(name, existing)` 新設
  - `Hero` → `Hero_001`、`Hero_001` → `Hero_002`、`Hero_001_001` → `Hero_001_002`
  - 既存番号の最大値 + 1 を返すので「歯抜けがあってもまとめて埋めない」「suffix
    増殖しない」
- **Lock / Solo を複製先で両方リセット**: 「複製したのに編集できない」事故を防止
- **source_preset を `copy of <元 Instance 名>`** に変更し UI 上で識別可能に
- **複製中の dispatcher を suspend**:
  - `runtime/instance_dispatcher.suspend_dispatch()` / `resume_dispatch()` を新設
  - Duplicate 中はバッチ書込中の中間状態で Follow 計算が走らない
  - 終了後 `dispatch(scene, force=True)` で 1 度だけ整合させる
- 名前の同期: `inst.name` を最後に設定して、update callback で Collection /
  Camera を正しい名前にリネーム

### Added
- **`KINEMA_OT_detach_follow`**: Active Instance の Follow Target を解除し、
  現在のカメラ位置・回転を「凍結」する。dispatcher が follow 計算を skip する
  ので、ユーザーが手でカメラを動かした位置が保持される
  - 確認ダイアログ付き
  - `also_lookat` オプションで LookAt Target も同時解除可能
  - Follow セクションヘッダに `UNLINKED` アイコンで配置（Follow Target が
    set されているときだけ表示）

### Tests
- `tests/test_naming.py`: `next_serial_from` の 5 ケース追加（合計 12 ケース）

## [2.0.0-beta2.6] - 2026-05-17

### Added
- **Instance UIList 上で名前を直接編集可能に**
  - `data/instance_item._on_name_changed`: Instance.name 変更時に
    対応する collection / camera オブジェクトも同名にリネーム
  - 名前衝突時は Blender が `.001` を付けるので、結果を inst.name に
    書き戻して整合
  - 再帰防止フラグ (`_renaming_in_progress` set) で update callback の
    無限ループを防止
  - `ui/instances_view`: 名前 label を `row.prop(item, "name", emboss=False)`
    に変更（ダブルクリックで編集モードに入る）

## [2.0.0-beta2.5] - 2026-05-17

### Added — カメラ別バッチレンダー
- **`KINEMA_OT_render_by_markers`**: Timeline の Camera Marker ごとに
  フレーム範囲を切り分け、`<scene.render.filepath>/<cam_name>/` という
  サブフォルダにそれぞれレンダー
  - 各 marker の frame から次 marker の frame-1 までを担当範囲とする
  - 最後の marker は `scene.frame_end` まで
  - `scene.frame_start` / `scene.frame_end` でクリップ
  - 同じカメラに複数 marker があれば同じフォルダに（範囲がファイル名に出る）
  - MP4 (FFmpeg) でも PNG 連番でも動作。Blender の出力フォーマット設定を
    そのまま使う
  - 実行前に範囲一覧を invoke_props_dialog で確認できる
  - 失敗した範囲があっても他は続行
  - 終了時に `render.filepath` / `frame_start/end` / `scene.camera` を全て復元
- **`KINEMA_OT_render_active_instance`**: Marker を使わず Active Instance の
  カメラだけを scene.frame_start〜end でレンダー（同じ `<base>/<cam>/` 規約）
- UI: 新規 Render ボックスに `By Markers` / `Active Only` ボタン。
  Marker 件数も表示

## [2.0.0-beta2.4] - 2026-05-17

### Added — Round A (健全性 + 小 UX)
- **load_post 健全性チェック**: `.blend` 読込時に各 Scene の
  `active_instance_index` / `active_preset_index` を範囲内に補正、
  参照切れ Instance の件数を System Console に warning 出力
- **Cleanup Unchanged Keys の確認ダイアログ**: invoke で `invoke_props_dialog`
  を出し、削除内容を事前確認できる
- **Auto Keyframe ON 時の視覚強調**: Active Instance ボックスを赤系
  (`alert = True`) + ヘッダに `● REC` プレフィックス
- **Diagnostics 出力をパネル内に貼り付け**: `WindowManager.kinema_clipboard.
  diag_log` に Run 結果を保存し、パネルの Diagnostics ボックス内に行ごと表示
  （System Console を開かなくても見える）
- **Auto Preview on Select**: Instance リスト切替で `scene.camera` も自動切替
  （`auto_preview_on_select` トグルで ON/OFF、Instances ヘッダに目アイコン）
- **Instance リストの並べ替え**（`KINEMA_OT_move_instance`）: リスト横の
  上下三角ボタンで Active を Up/Down 移動

### Added — Round B (機能拡張)
- **Paste to Selected**: Copy/Paste の paste 側に `target` Enum を追加。
  Outliner / Viewport で選択中のカメラに紐づく **全 Instance に一括 paste**。
  各セクションヘッダに従来の Paste アイコンに加え GROUP_VERTEX アイコンを追加
  Lock 中の Instance は paste skip
- **JSON Import モード**: `replace / merge / append` の 3 択
  - **APPEND**: 既存 Instance に追加（従来動作）
  - **MERGE**: 名前一致した Instance に上書き、無いものは追加
  - **REPLACE**: 既存全削除してから読込
- **Bake Camera Animation** (`KINEMA_OT_bake_animation`): Active Instance の
  カメラを `scene.frame_start〜frame_end` で visual keying ベイク。
  Follow/LookAt/Noise の damping 効果を毎フレームの keyframe として焼き込み、
  独立した f-curve として後段で編集できる状態にする。確認ダイアログ付き

## [2.0.0-beta2.3] - 2026-05-17

### Fixed
- **Clear Unchanged Keys が AttributeError**:
  `'Action' object has no attribute 'fcurves'`。Blender 4.4+ で Action が
  **Layered Actions** に移行し `action.fcurves` が廃止されたため。
  `_iter_fcurves(action)` を新設して、レガシー API (`action.fcurves`) と
  新 API (`action.layers[].strips[].channelbag(slot).fcurves`) を両対応
  - (container, fcurve) のタプルで yield して、削除時の container.remove()
    も両 API で動くようにした

## [2.0.0-beta2.2] - 2026-05-17

### Added
- **Cleanup Unchanged Keys** (`KINEMA_OT_clear_unchanged_keys`):
  Active Instance に紐づく f-curve のうち、全 keyframe の値が同一
  （変化していない）ものを削除する。Key All で一括キーした後、結果的に
  動かなかったプロパティを掃除する用途
  - 走査対象: Camera Object / Camera Data / scene.kinema.instances[idx].*
  - 判定: `max(values) - min(values) < 1e-6` で全キー同値かを確認
  - UI: Active Instance ヘッダの Key All ボタンの隣に KEY_DEHLT アイコンで配置
  - Info に削除した f-curve のパスを最大 3 件表示

## [2.0.0-beta2.1] - 2026-05-17

### Added
- **Kinema UI のカメラ選択 → Outliner / Viewport 連動**
  - `data/scene_settings._on_active_preset_changed`: Preset 行をクリックすると
    対応 Camera オブジェクトを Outliner / Viewport で **select + active** にする
  - `data/scene_settings._on_active_instance_changed`: 既存の Keying Set
    Rebuild に加え、Instance 行クリック時に該当カメラを同様に選択
  - 既存選択は全解除して単一選択にする（Outliner 単クリック相当）
  - グループヘッダ行は無視

### Fixed
- `.github/workflows/release.yml`: Node.js 20 deprecation warning を解消。
  workflow に `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: "true"` を env で設定し、
  actions/checkout@v4 と softprops/action-gh-release@v2 を Node.js 24 で実行

## [2.0.0-beta2] - 2026-05-17

「残タスク一括処理」フェーズ。alpha/beta1 系で積み残していた機能・運用・配布
周りをまとめて実装した結節点。次マイルストーンに向けて bump。

### Added — 機能
- **Y 軸 Roll を LookAt 中も反映**: Track To 制約を撤回し、`direction.to_track_quat`
  ベースの自前 LookAt + local Z 軸回転で Roll を実現
- **Solo / Mute / Lock**: 各 Instance に `solo` / `locked` を追加（enabled は既存
  = Mute の逆）。dispatcher は solo フラグの立った Instance だけを評価し、locked
  は UI 編集禁止 + Auto Keyframe / Key All の対象外に
- **Keying Set の自動 Rebuild**: `active_instance_index` の update callback で
  "Kinema Camera" Keying Set がある場合に `bpy.ops.kinema.rebuild_keying_set` を
  自動呼出し
- **JSON Export / Import** (`utils/json_io.py` + `ops/io_ops.py`): schema_version 1
  で Scene の Instance 一覧を保存・読込。Pointer は名前で永続化、
  `bpy_extras.ImportHelper/ExportHelper` ベースのファイルブラウザ
- **cineflow Importer** (`ops/cineflow_import.py`): cineflow が enabled な
  状態で `KINEMA_OT_import_from_cineflow` を実行して Instance を変換。
  cineflow 警告バナーに Import ボタンを追加

### Added — 配布
- `LICENSE`: GPL-3.0-or-later 全文
- `scripts/check_version.ps1`: `blender_manifest.toml` と `bl_info["version"]`
  の base version 一致を確認（exit 0 で OK）
- `scripts/build_zip.ps1`: 配布 ZIP をローカル生成（`__pycache__` / `.pyc` 除外）
- `.github/workflows/release.yml`: `v*.*.*` tag push をトリガに ZIP を作って
  GitHub Release に添付。`-` を含む tag は prerelease 扱い

### Added — ドキュメント
- `docs/architecture.md`: CLAUDE.md 規約に沿ったアーキ図・データフロー・主要設計判断
- `docs/dev_workflow.md`: Junction reload と Disable→Enable の判断早見表 +
  バージョン更新 / GitHub Release 手順 / よくあるトラブル
- yato-atlas に `kinema/INDEX.md` を追加（プロジェクト引き継ぎファイル）

### Tests
- `tests/test_json_io.py`: 純粋ロジック 5 ケース緑（pytest 対象が 5 → 6 ファイルに）

## [2.0.0-beta1.10] - 2026-05-17

### 整理 / リファクタ
- **遅延 import を module top に集約**:
  `runtime/follow_lookat.py` の `from mathutils import Euler` と
  `runtime/instance_dispatcher.py` の `import math` を関数内から
  module top に移動
- **`utils/clipboard.py` を新設**してコピペの純粋ロジックを bpy 非依存に分離
  - `copy_fields` / `paste_fields` / `copy_object_ref` / `paste_object_ref`
  - これに対する `tests/test_clipboard.py` を追加（10 ケース）
- `ops/clipboard_ops.py` は新ヘルパを呼ぶラッパに
- `ops/diagnostics_ops.py` の点検範囲を整理（cineflow アドオン状態 /
  Preset Root / Instances Root / Keying Set の有無も追加表示）

### 機能追加
- **Preset の `kn_default_lens` を Load 時にカメラへ自動適用**
  - 旧: 複製後のカメラの現在 lens をそのまま使う
  - 新: PresetItem.default_lens が 0 以外なら、複製後の Camera Data.lens に
    上書き → ユーザーは Preset 側に「使用想定の焦点距離」を仕込んでおける

### 削除（dead code）
- `config/constants.py` から `LEGACY_CF_*` 7 定数（cineflow importer 未実装）
- `data/scene_settings.py` から `tag_filter`（UI 未配線、未使用）
- `preferences.py` の未使用フィールド全て
  （`keymap_backup_json` / `step_translate` / `step_rotate` /
   `auto_enable_handler_after_cineflow_disable`）
  → AddonPreferences は表示用の最小実装に縮小
- 空の `src/kinema/importers/` ディレクトリを削除
- `docs/alpha1_smoke_test.md` 削除（manual_smoke_test.md に置換）

### ドキュメント
- **`README.md` を現状機能リストに全面更新**
- **`docs/manual_smoke_test.md` 新設**：12 セクションの動作確認手順 +
  チェックリスト 18 項目で beta1 系の全機能をカバー

## [2.0.0-beta1.9] - 2026-05-16

### Fixed
- **Rebuild Keying Set のエラー**:
  `scene.keying_sets.remove()` が Blender 5.x で存在しないため
  `AttributeError: bpy_prop_collection: attribute "remove" not found`。
  既存 KS があれば `paths.clear()` で再利用する方式に変更
- **Auto Keyframe が常に最初の Scene にキーを打つ問題**:
  `_apply_now` が `context.scene` を使っていたため、複数 Scene 構成で
  別 Scene の Instance を編集中も「context.scene = 1_MainScene」が選ばれて
  しまっていた。`bpy.data.scenes` を走査して **自分が属する Scene を逆引き**
  する `_find_owner_scene()` を追加し、Auto Keyframe / dispatch ともに
  所有 Scene を使うように修正
- Copy / Paste の Info レポートに **対象 Instance 名** を表示するように改善
  （`Copied [follow] from 'XXX' (8 fields)` のような表記）

### Known (要 fix が必要なら別途連絡)
- Keying Set の path は作成時の Scene を target ID として記録するため、別
  Scene で同じ Keying Set を使うと最初の Scene にキーが飛ぶ。複数 Scene
  運用時は Scene 切替後に **Rebuild Keying Set** を再実行する必要あり

## [2.0.0-beta1.8] - 2026-05-16

### Added — 設定のコピー/ペースト
- `data/wm_settings.KinemaClipboard`: session-only クリップボード
  PropertyGroup（`WindowManager.kinema_clipboard`）。カテゴリ別に
  6 スロット（all / pose / dof / follow / lookat / noise）の JSON 文字列
- `ops/clipboard_ops.py` 新規:
  - `KINEMA_OT_copy_settings(category)`: Active Instance の指定カテゴリを
    JSON 化して該当スロットに保存
  - `KINEMA_OT_paste_settings(category)`: 該当スロットから読み込んで
    Active Instance に適用
- PointerProperty (Follow Target / LookAt Target / Focus Object) は名前で
  保存し、ペースト時に `bpy.data.objects.get` で解決
- UI:
  - Active Instance ヘッダに **Copy All / Paste All** アイコン
  - 各セクション (Lens/Shift / DoF / Follow / LookAt / Noise) のヘッダに
    **個別 Copy / Paste** アイコン

### 使い方
- 1 つの Instance の Follow 設定を完成させる → セクション横の Copy → 他の
  Instance を Active に → Paste で同じ Follow 設定を反映
- 全体丸ごとコピーしたい場合は Active ヘッダの Copy All / Paste All
- カテゴリ別と一括は独立スロットなので、Follow を Copy した直後に Lens を
  Copy しても Follow スロットは保持される

## [2.0.0-beta1.7] - 2026-05-16

### Added — キーフレーム
- `ops/keyframe_ops.py` 新規:
  - `KINEMA_OT_keyframe_all`: Active Instance の Transform / Lens / Shift /
    DoF / Follow パラメータを現フレームに一括 keyframe_insert
  - `KINEMA_OT_rebuild_keying_set`: kinema 専用 Keying Set "Kinema Camera"
    を Active Instance ベースで自動生成・更新。Blender 標準 I キーや Auto
    Keyframe と統合される
  - `KINEMA_OT_toggle_auto_keyframe`: Blender 標準の Auto Keyframe (赤丸)
    を kinema パネルからワンタッチでトグル
- `data/instance_item._apply_now`: Blender 標準の Auto Keyframe (赤丸) が ON
  のとき、Instance プロパティ変更時に scene 経由で `kinema.instances[i].xxx`
  の全パスを `scene.keyframe_insert` で自動キー
- `ui/main_panel`: Active Instance ヘッダに 3 ボタン
  - REC アイコン: Auto Keyframe (赤丸) ON/OFF（点灯で ON）
  - "Key All" (KEY_HLT アイコン): 一括キー
  - KEYINGSET アイコン: Keying Set 再構築

### 使い方
- 即席で 1 フレームだけキーを打ちたい → "Key All"
- 編集中ずっと自動キーしたい → REC ボタンで Auto Keyframe を ON
- Blender 標準の I キーや Dopesheet と統合したい → Rebuild Keying Set →
  Keying Set ドロップダウンで "Kinema Camera" を active に

## [2.0.0-beta1.6] - 2026-05-16

### Changed (breaking)
- **Follow の角度パラメータを Yaw/Pitch から Euler XYZ にリネーム**
  - 旧: `follow_yaw` / `follow_pitch`
  - 新: `follow_rot_x`（X 軸回転 = 上下角）/ `follow_rot_y`（Y 軸回転 = ロール）
        / `follow_rot_z`（Z 軸回転 = 水平回り）
  - 同義だが Blender 流の Euler XYZ 表記に統一して直感性向上
- `update_follow`: `mathutils.Euler((rot_x, 0, rot_z), 'XYZ')` で初期方向 (0,1,0)
  を回転して target からの相対位置を計算する形に書き換え
- `set_follow_angle` Operator の引数も `yaw/pitch` → `rot_x/rot_y/rot_z`
- Duplicate Operator: 新フィールドをコピー対象に
- UI: プリセットを Front / Right / Back / Left の 4 つに絞り、上下プリセットは
  X 軸スライダーで対応してもらう方針に簡素化

### Added
- **Y 軸回転 (Roll)**: カメラの視線軸まわりの傾き。
  - `instance_dispatcher._apply_roll`: Track To 制約が active なら効かない
    （現バージョンの制約）ので、LookAt Target を空にしたシナリオで有効
  - UI に「※ Y 軸 (Roll) は LookAt Target 無効時のみ反映」と注記

## [2.0.0-beta1.5] - 2026-05-16

### Added
- **Active Instance パネルに Shift / Depth of Field セクション**を追加
  - Shift X / Y を 1 行に並べて編集
  - 被写界深度: use_dof トグル / Focus Object / Focus Distance（Object が
    無い場合のみ）/ F-Stop / Blades / Rotation / Ratio
  - データの真は Camera Data そのもの。Instance スキーマは増やさず、
    `cam.data` / `cam.data.dof` を `layout.prop` で直接編集
  - Duplicate 時は `data.copy()` で独立コピーされるので、Instance ごとに
    別 DoF / Shift 設定を持てる（共有はしない）

## [2.0.0-beta1.4] - 2026-05-16

### Added (breaking)
- **全方位 Follow（球面座標）**: Follow Target の周りを Yaw / Pitch で
  自由に位置決めできるよう設計変更
  - `data/instance_item`: `follow_yaw` (deg, default=0=正面) / `follow_pitch`
    (deg, default=0=水平) を追加
  - `runtime/follow_lookat.update_follow`: target.matrix_world を基準にした
    球面座標 (yaw, pitch, distance) でカメラ位置を計算。world up と直交する
    接線ベクトルで side offset を算出
  - 旧「`-forward * dist` (TPS 後方固定)」を撤回。新デフォルトは yaw=0 で
    target の正面 (+Y) に配置 → 立ち絵の正面撮影が自然に成立
- **方向プリセットボタン** (`KINEMA_OT_set_follow_angle`):
  Front / Right / Back / Left / Top↓ / Bot↑ / FrtUp / FrtDn の 8 ボタン
  - Yaw / Pitch をワンクリックで切替
- UI: Follow セクションに Orbit ボックス（Yaw / Pitch + プリセット）追加
- Duplicate Operator: yaw / pitch もコピー対象に

### Notes
- 旧 Instance の follow_height デフォルトは 1.5 だったが、新デフォルトは
  0.0（球面座標で位置決定するため、Z 軸オフセットは「微調整」に格下げ）
- `yaw=180` にすれば旧 TPS 後方追従と互換挙動になる

## [2.0.0-beta1.3] - 2026-05-16

### Added
- **Follow Target の自動 LookAt**: Instance に
  `follow_auto_lookat: BoolProperty(default=True)` を追加。
  LookAt Target が空でも Follow Target を見続けるよう自動的に回転追従させる。
  別オブジェクトを意図せず LookAt して挙動が崩れる事故を防ぐ
- `runtime/follow_lookat.update_lookat_with_target`: 任意の target を引数で
  渡せる LookAt 更新 API
- UI: Follow セクションに `Auto Look at Follow Target` トグル。
  LookAt セクションに「→ Auto: <object 名>」表示で何を見ているかを明示

### Changed
- `instance_dispatcher._apply_instances`: LookAt Target 明示指定 > Follow
  Target 自動採用 > 何もない → Proxy 掃除、の優先順で評価
- `KINEMA_OT_duplicate_instance`: `follow_auto_lookat` もコピー対象に

## [2.0.0-beta1.2] - 2026-05-16

### Removed (revert)
- **独自タイムライン UI を全撤回**（Yato さん要望：Blender 標準
  Timeline / VSE を運用で使う方針に変更）
  - `ui/timeline/` (host_resolver / drawer / header_append / modal_ops)
  - `ops/timeline_ops.py`（Toggle Mode / Add Shot / Delete / Clear All）
  - `data/wm_settings.py` (WindowManager.kinema)
  - `data/shot.py`, `data/track.py`, `data/timeline_view.py`
  - `runtime/shot_dispatcher.py`
  - `docs/beta1_smoke_test.md`
  - `main_panel` の Shot Timeline セクション
- `scene_settings`: tracks / shot_clips / active_clip_uid / timeline_view
  フィールドを撤去

### Added
- `runtime/instance_dispatcher.py`: 旧 shot_dispatcher の Instance フォール
  バック部分のみを抽出したシンプルな dispatcher。frame_change / depsgraph /
  update callback から呼ばれ、Instance に Follow/LookAt/Noise を 1 ステップ適用
- **`KINEMA_OT_duplicate_instance`**: 選択中の Instance を関連オブジェクトごと
  複製。Follow/LookAt/Noise/Lens 等のパラメータも丸ごとコピー
- Instance UIList と Instances ボックスヘッダに **Duplicate ボタン** 追加

## [2.0.0-beta1.1] - 2026-05-16

### Changed
- **ホスト Editor を Image Editor → Video Sequencer (VSE) に変更**
  - `host_resolver.HOST_AREA_TYPE = "SEQUENCE_EDITOR"`
  - `drawer`: `SpaceSequenceEditor.draw_handler_add` に切替
  - `header_append`: `SEQUENCER_HT_header` に Append
  - `modal_ops`: キーマップを "SequencerCommon" / SEQUENCE_EDITOR に登録
  - `timeline_ops.toggle_timeline_mode`: エラーメッセージ更新
  - `docs/beta1_smoke_test.md`: 手順を Sequencer に書き直し
- タイムラインを扱うエディタとしての自然さを優先（Yato さん要望）

## [2.0.0-beta1] - 2026-05-16

### Added — Shot Timeline UI 基盤
- `data/wm_settings.KinemaWMSettings`: WindowManager.kinema PropertyGroup
  （host_window_pointer / host_area_pointer / host_screen_name / host_area_index
  / timeline_mode_on / modal_dryrun_state）
- `ui/timeline/host_resolver`: 主キー (pointer) + 二次キー (screen+index) で
  ホスト Area を識別。pointer 無効化時に二次キーから self-heal
- `ui/timeline/drawer`: `SpaceImageEditor.draw_handler_add` 経由で背景・
  フレームグリッド・トラック・Shot ストリップ・プレイヘッドを GPU 描画
- `ui/timeline/header_append`: IMAGE_HT_header に kinema モード ON/OFF
  トグルを追加
- `ui/timeline/modal_ops.KINEMA_OT_timeline_click`: 左クリックで Shot 選択 /
  プレイヘッド移動
- `ops/timeline_ops`:
  - `KINEMA_OT_toggle_timeline_mode`: ホスト指定 + モード切替
  - `KINEMA_OT_add_shot_at_playhead`: プレイヘッド位置に 50 フレーム Shot 追加
  - `KINEMA_OT_delete_active_shot` / `KINEMA_OT_clear_shots`
- `ui/main_panel`: Shot Timeline セクション追加（Shot 一覧 + 操作ボタン）
- `docs/beta1_smoke_test.md`: 動作確認手順

### Notes
- shot_dispatcher (alpha1 実装) と直結しているので、Shot を追加して再生すると
  `scene.camera` が自動切替される
- 描画は kinema 専用ホスト Area の 1 つだけで行われ、他の Image Editor は
  通常通り画像表示用として使える

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
