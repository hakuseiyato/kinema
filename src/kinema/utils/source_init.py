"""Preset ソース生成ロジック（kinema からも Yato Project Kit からも呼べる API）。

設計意図:
  Yato さんは Preset 階層を手で組むのが煩雑だと感じている。本モジュールに
  「コレクション階層を作る」「カメラを Preset として登録する」操作を集約し、
  kinema の Operator は薄いラッパに留める。将来 Yato Project Kit が新規 .blend
  生成時に同じロジックを呼べるよう、bpy への依存はあるが scene を引数で受ける
  純粋関数のスタイルで書く。

API 互換性:
  - `ensure_preset_root(scene, name) -> Collection`
  - `make_empty_preset(root, name, camera=None) -> Collection`
  - `register_camera_as_preset(scene, root, cam_obj, name=None) -> Collection`
  - `quick_start(scene, root_name) -> (root, sample_collection)`

すべて冪等。既存のコレクションに対しては破壊的な書換を行わない。
"""

from __future__ import annotations

from typing import Optional

import bpy

from ..config import constants as C
from . import naming


def ensure_preset_root(scene, name: Optional[str] = None) -> bpy.types.Collection:
    """Preset Root コレクションを取得 or 作成して返す。

    name が省略された場合は `Kinema_Presets` を使用。Scene 直下の子として配置。
    既に同名コレクションが Scene 直下にあればそれを返す（破壊しない）。
    """
    target = name or C.DEFAULT_PRESET_ROOT
    for child in scene.collection.children:
        if child.name == target:
            return child
    # 既に同名コレクションが bpy.data に存在する場合はリンクして使い回す
    existing = bpy.data.collections.get(target)
    if existing is not None:
        scene.collection.children.link(existing)
        return existing
    new_coll = bpy.data.collections.new(target)
    scene.collection.children.link(new_coll)
    return new_coll


def make_empty_preset(
    root: bpy.types.Collection,
    name: str,
    camera: Optional[bpy.types.Object] = None,
) -> bpy.types.Collection:
    """root 配下にプリセット用サブコレクションを作る。

    name が既存と重複すれば `_001` で採番。camera が指定されればそのオブジェクトを
    新コレクションに link する（既存所属コレクションからは unlink しない）。
    """
    existing_names = set(bpy.data.collections.keys())
    unique_name = naming.next_unique_name(name, existing_names)
    sub = bpy.data.collections.new(unique_name)
    root.children.link(sub)
    if camera is not None:
        sub.objects.link(camera)
    return sub


def register_camera_as_preset(
    scene,
    root: bpy.types.Collection,
    cam_obj: bpy.types.Object,
    name: Optional[str] = None,
) -> bpy.types.Collection:
    """既存の Camera を root の配下に「プリセット 1 件」として登録する。

    新規サブコレクションを作って camera を link する（元の所属コレクションは
    そのまま）。name 省略時は `<cam_name>` を base にして採番。
    """
    if cam_obj is None or cam_obj.type != "CAMERA":
        raise ValueError("register_camera_as_preset: cam_obj は Camera オブジェクトである必要があります")
    base = name or cam_obj.name
    return make_empty_preset(root, base, camera=cam_obj)


def capture_view_as_new_preset(
    context,
    root: bpy.types.Collection,
    base_name: str = "ViewCam",
) -> tuple[bpy.types.Collection, bpy.types.Object]:
    """現在の 3D ビューポートから新規カメラを作り、root の配下にプリセットとして追加。

    3D View Area が必要。無い場合は ValueError。
    返り値: (新規サブコレクション, 新規カメラ)
    """
    view3d_area = None
    for area in context.window.screen.areas:
        if area.type == "VIEW_3D":
            view3d_area = area
            break
    if view3d_area is None:
        raise ValueError("3D Viewport が必要です。3D View を 1 つ開いてください")

    space = next((s for s in view3d_area.spaces if s.type == "VIEW_3D"), None)
    if space is None or space.region_3d is None:
        raise ValueError("3D View の region_3d が取れません")

    region_3d = space.region_3d
    # 新規 Camera データ + Object
    cam_data = bpy.data.cameras.new(base_name)
    cam_obj = bpy.data.objects.new(base_name, cam_data)
    # ビュー行列の逆行列がカメラ姿勢
    cam_obj.matrix_world = region_3d.view_matrix.inverted()

    # サブコレクションを作って入れる
    sub = make_empty_preset(root, base_name, camera=cam_obj)
    return sub, cam_obj


def quick_start(
    scene,
    root_name: Optional[str] = None,
) -> tuple[bpy.types.Collection, bpy.types.Collection]:
    """ワンクリック初期化（毎回新規サンプルを追加）。

    動作:
      1. Preset Root を作成（既存ならそのまま）
      2. **毎回** 新しいサンプル Camera プリセットを 1 件追加（採番付き）
      3. root と新規サブコレクションを返す

    旧仕様の「root に子があれば何もしない」は撤廃。連打しても増えるようにする
    （Yato さん要望）。
    """
    root = ensure_preset_root(scene, root_name)
    # 既存名と被らない採番
    existing = set(bpy.data.collections.keys()) | set(bpy.data.objects.keys())
    name = naming.next_unique_name("Sample_Camera", existing)
    sample = bpy.data.collections.new(name)
    root.children.link(sample)
    cam_data = bpy.data.cameras.new(name)
    cam_obj = bpy.data.objects.new(name, cam_data)
    sample.objects.link(cam_obj)
    return root, sample
