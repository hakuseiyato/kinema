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
    )
    follow_distance: FloatProperty(name="Distance", default=5.0, min=0.0)
    follow_height: FloatProperty(name="Height", default=1.5)
    follow_side: FloatProperty(name="Side Offset", default=0.0)
    follow_damping: FloatProperty(name="Follow Damping", default=0.3, min=0.0, max=1.0)

    # --- LookAt ---
    lookat_target: PointerProperty(
        name="LookAt Target", type=bpy.types.Object, poll=_is_object_poll,
    )
    lookat_damping: FloatProperty(name="LookAt Damping", default=0.3, min=0.0, max=1.0)

    # --- Noise ---
    noise_enabled: BoolProperty(name="Noise", default=False)
    noise_strength_pos: FloatProperty(name="Noise Pos", default=0.05, min=0.0)
    noise_strength_rot: FloatProperty(
        name="Noise Rot (deg)", default=0.5, min=0.0,
        description="ローテーション側のノイズ振幅（度）",
    )
    noise_frequency: FloatProperty(name="Noise Freq", default=0.5, min=0.0)
    noise_seed: IntProperty(name="Noise Seed", default=0, min=0)
