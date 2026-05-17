"""ロード済みカメラインスタンス（Preset から複製されたもの）。"""

from __future__ import annotations

import bpy
from bpy.props import (
    BoolProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)


def _is_camera_poll(self, obj):
    return obj is None or obj.type == "CAMERA"


def _is_object_poll(self, obj):
    return True


def _apply_now(self, context):
    """Instance プロパティが変わった時に即座に Follow/LookAt/Noise を 1 ステップ適用。

    再生していない状態でもユーザーがスライダーを動かしたら追従が見えるようにする。
    """
    try:
        from ..runtime import instance_dispatcher
        # 再帰防止：dispatch 中の自己呼び出しを抑止
        if instance_dispatcher._in_dispatch:
            return
        instance_dispatcher.dispatch(context.scene)
    except Exception:
        # update callback は何があっても UI を壊さない
        pass


class KinemaInstanceItem(bpy.types.PropertyGroup):
    """1 つのロード済みプリセット = 1 行。"""

    # --- 識別 ---
    name: StringProperty(name="Name", default="")
    source_preset: StringProperty(name="Source Preset", default="")
    collection_ref: PointerProperty(name="Collection", type=bpy.types.Collection)
    camera_ref: PointerProperty(
        name="Camera",
        type=bpy.types.Object,
        poll=_is_camera_poll,
    )

    # --- ON/OFF ---
    enabled: BoolProperty(
        name="Enabled",
        description="ランタイム（Follow/LookAt/Noise）を適用するか",
        default=True,
        update=_apply_now,
    )

    # --- Lens ---
    lens_mm: FloatProperty(
        name="Lens (mm)",
        description="焦点距離。Pose タブから上書きできる",
        default=50.0,
        min=1.0,
        max=5000.0,
    )

    # --- Follow ---
    follow_target: PointerProperty(
        name="Follow Target", type=bpy.types.Object, poll=_is_object_poll,
        update=_apply_now,
    )
    follow_distance: FloatProperty(name="Distance", default=5.0, min=0.0, update=_apply_now)
    follow_height: FloatProperty(name="Height", default=1.5, update=_apply_now)
    follow_side: FloatProperty(name="Side Offset", default=0.0, update=_apply_now)
    follow_damping: FloatProperty(name="Follow Damping", default=0.3, min=0.0, max=1.0, update=_apply_now)
    follow_auto_lookat: BoolProperty(
        name="Auto Look at Follow Target",
        description=(
            "LookAt Target が未指定の場合、Follow Target を自動的に注視する。"
            "「変な方向を見る」事故を防ぐ"
        ),
        default=True,
        update=_apply_now,
    )

    # --- LookAt ---
    lookat_target: PointerProperty(
        name="LookAt Target", type=bpy.types.Object, poll=_is_object_poll,
        update=_apply_now,
    )
    lookat_damping: FloatProperty(name="LookAt Damping", default=0.3, min=0.0, max=1.0, update=_apply_now)

    # --- Noise ---
    noise_enabled: BoolProperty(name="Noise", default=False, update=_apply_now)
    noise_strength_pos: FloatProperty(name="Noise Pos", default=0.05, min=0.0, update=_apply_now)
    noise_strength_rot: FloatProperty(
        name="Noise Rot (deg)", default=0.5, min=0.0,
        description="ローテーション側のノイズ振幅（度）",
        update=_apply_now,
    )
    noise_frequency: FloatProperty(name="Noise Freq", default=0.5, min=0.0, update=_apply_now)
    noise_seed: IntProperty(name="Noise Seed", default=0, min=0, update=_apply_now)
