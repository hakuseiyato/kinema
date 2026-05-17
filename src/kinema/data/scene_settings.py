"""KinemaSceneSettings — Scene にぶら下がる最上位 PropertyGroup。

Shot Timeline 関連の集合 (tracks / shot_clips / timeline_view) は撤回した。
代わりに Blender 標準 Timeline / VSE / Marker を運用で使う。
"""

from __future__ import annotations

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    IntProperty,
    StringProperty,
)

from ..config import constants as C
from . import preset_item, instance_item


def _on_active_instance_changed(self, context):
    """Active Instance 切替時、kinema Keying Set があれば自動 Rebuild。

    切替前後でカメラ・Instance プロパティの path が変わるので、
    既存の Keying Set を最新の Active に追従させる。
    """
    try:
        from ..ops.keyframe_ops import KEYING_SET_LABEL  # noqa: PLC0415
        scene = context.scene
        ks = scene.keying_sets.get(KEYING_SET_LABEL)
        if ks is None:
            return  # 生成されていなければ何もしない
        # 既存があれば再構築（Operator 呼出で安全に処理）
        bpy.ops.kinema.rebuild_keying_set("INVOKE_DEFAULT")
    except Exception:
        pass


class KinemaSceneSettings(bpy.types.PropertyGroup):
    # --- Source roots ---
    preset_root_name: StringProperty(
        name="Preset Root",
        description="プリセットを格納したコレクション名。Scene のルート直下に置く",
        default=C.DEFAULT_PRESET_ROOT,
    )
    instances_root_name: StringProperty(
        name="Instances Root",
        description="ロードしたカメラを格納するコレクション名",
        default=C.DEFAULT_INSTANCES_ROOT,
    )

    # --- Preset 一覧（scan_presets の結果キャッシュ）---
    presets: CollectionProperty(type=preset_item.KinemaPresetItem)
    active_preset_index: IntProperty(name="Active Preset", default=0)

    # --- Instance 一覧 ---
    instances: CollectionProperty(type=instance_item.KinemaInstanceItem)
    active_instance_index: IntProperty(
        name="Active Instance",
        default=0,
        update=_on_active_instance_changed,
    )

    # --- 動作 ---
    auto_preview_on_select: BoolProperty(
        name="Auto Preview on Select",
        description="Cameras タブで Instance を選択するだけで scene.camera を切り替える",
        default=True,
    )
