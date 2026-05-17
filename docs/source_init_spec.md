# Preset ソース初期化仕様（Yato Project Kit 引継ぎ用）

## 背景

kinema は「`scene.collection > <Preset Root> > <サブコレクション> > <Camera>`」という階層をプリセットの真正データとして読み書きする。この階層は **Blender 起動直後のシーンには存在しない** ため、ユーザーは手で組む必要があり、躓きやすい。

そこで kinema 内に `utils/source_init.py` というワンクリック初期化用の純粋ロジック層を設け、Operator（`ops/source_ops.py`）はその薄いラッパーとして実装している。本ファイルは、将来 **Yato Project Kit**（新規 Blender プロジェクトを始める時のスケルトン生成ツール）に同じロジックを引き継ぐための仕様メモ。

## 目標

- 新規 .blend を作る時に、Yato Project Kit が `Kinema_Presets` コレクションを **自動で用意済み**にしておく
- kinema 側の Quick Start ボタン群は「Yato Project Kit が初期化していなかった場合のフォールバック」として残す
- 同じロジックを 2 つの場所で重複実装しないため、kinema の `utils/source_init.py` を **API として公開** し、Yato Project Kit からも import 可能にする
- もしくは Yato Project Kit が独自実装する場合も、同じ階層構造・同じ命名規約を守る

## ディレクトリ階層の約束

```
Scene Collection
└── <Preset Root>            # デフォルト名: "Kinema_Presets"
    ├── <Group>_<Short>      # 例: Hero_Wide, Hero_CloseUp
    │   └── Camera           # サブコレクション直下、または更に下の階層
    ├── <Short>              # グループ無しのサブコレクション
    │   └── Camera
    └── ...
```

- Preset Root の名前は `scene.kinema.preset_root_name`（StringProperty）で動的に決まる。デフォルトは `"Kinema_Presets"`
- サブコレクション名に `_` が含まれていれば、最初の `_` でグループ化される（`Hero_Wide`、`Hero_CloseUp` は "Hero" グループ）
- サブコレクション配下の最初の Camera オブジェクトが代表カメラとして扱われる

## カスタムプロパティ（任意、サブコレクションに書く）

| キー | 型 | 役割 |
|---|---|---|
| `kn_tags` | str | カンマ区切りタグ（AND フィルタで使う） |
| `kn_default_lens` | float | ロード時にカメラに適用するデフォルト焦点距離 |
| `kn_has_anim` | bool | アニメ持ちフラグ（UI に "ANIM" アイコン表示） |
| `kn_preview_end` | int | Preview Play の終端フレーム |
| `kn_follow_target` | str | Load 時に自動リンクする Follow Target のオブジェクト名 |
| `kn_lookat_target` | str | LookAt Target のオブジェクト名 |

旧 cineflow キー (`cf_*`) は `importers/cineflow_import.py` でのみ参照する。

## API 仕様（`utils/source_init.py`）

すべて冪等。既存コレクションを破壊しない。

### `ensure_preset_root(scene, name=None) -> Collection`

- Scene 直下に Preset Root コレクションを取得 or 作成
- `name=None` の場合は `kinema.config.constants.DEFAULT_PRESET_ROOT`（= `"Kinema_Presets"`）を使う
- すでに `bpy.data.collections` に同名があれば、Scene 直下に link するだけ

### `make_empty_preset(root, name, camera=None) -> Collection`

- `root` の配下に新規サブコレクションを作る
- 名前重複時は `_001` で採番（`utils/naming.next_unique_name` 使用）
- `camera` が指定されればそのオブジェクトを link（既存の所属コレクションからは unlink しない）

### `register_camera_as_preset(scene, root, cam_obj, name=None) -> Collection`

- 既存の Camera オブジェクトを `root` 配下にプリセットとして登録
- 内部で `make_empty_preset` を呼ぶラッパ

### `capture_view_as_new_preset(context, root, base_name="ViewCam") -> (Collection, Object)`

- 現在の 3D Viewport から新規 Camera を作って `root` に登録
- ビュー行列の逆行列をカメラの world matrix に設定
- 3D View が無ければ `ValueError`

### `quick_start(scene, root_name=None) -> (Collection, Optional[Collection])`

- 1 ボタンで「Preset Root 作成 + 空の場合はサンプル 1 件追加」
- 既に root に子があれば「破壊せず何もしない（root だけ返す）」

## Yato Project Kit からの呼び出し例

```python
# Yato Project Kit が新規 .blend テンプレートを生成する時の擬似コード
import bpy

# kinema が enable されていれば、その API を使う
try:
    from kinema.utils import source_init as kn_source
    HAS_KINEMA = True
except ImportError:
    HAS_KINEMA = False

def init_scene_for_kinema(scene):
    if HAS_KINEMA:
        kn_source.ensure_preset_root(scene)
        # 必要なら Yato 標準プリセット群もここで kn_source.make_empty_preset で追加
    else:
        # フォールバック: kinema が無くても同じ階層を組む
        coll = bpy.data.collections.new("Kinema_Presets")
        scene.collection.children.link(coll)
```

将来 kinema が独自パッケージ ID（`bl_ext.user_default.kinema`）になっても、`utils/source_init` の API シグネチャは維持する。

## 関連

- 設計プラン v7: `C:/Users/brain/.claude/plans/blender-cineflow-...-foamy-bengio.md`
- kinema 本体: `src/kinema/utils/source_init.py`
- 対応 Operator: `src/kinema/ops/source_ops.py`
- UI 配線: `src/kinema/ui/main_panel.py`（Quick Start バナー）
