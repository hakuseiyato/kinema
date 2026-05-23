"""Camera Data に紐づく事前設定 PropertyGroup。

`bpy.types.Camera.kinema_preset` で Camera Data 単位に保持する。Instance と
同じスキーマで Follow / LookAt / Noise を持ち、`Load Selected Preset` 時に
Instance にコピーされる。Camera Data は `.blend` に永続化されるので、
Preset の事前設定もシーンを跨いで保持される。

設計意図:
  - Duplicate Operator を廃止して、複数欲しい場合は Preset を複数回 Load する
    運用に変更
  - 各 Preset は「最初から使える状態」になる（Load した瞬間から Follow 等が
    効く）
"""

from __future__ import annotations

import bpy
from bpy.props import (
    BoolProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
)


def _is_camera_poll(self, obj):
    return obj is None or obj.type == "CAMERA"


def _is_object_poll(self, obj):
    return True


class KinemaCameraPreset(bpy.types.PropertyGroup):
    """Camera Data に紐づく事前設定。Instance とフィールド構成を揃える。"""

    # --- Follow ---
    follow_target: PointerProperty(
        name="Follow Target", type=bpy.types.Object, poll=_is_object_poll,
    )
    follow_distance: FloatProperty(name="Distance", default=5.0, min=0.0)
    follow_rot_x: FloatProperty(
        name="X 軸回転 (上下)",
        default=0.0, min=-89.0, max=89.0,
    )
    follow_rot_y: FloatProperty(
        name="Y 軸回転 (ロール)",
        default=0.0, min=-180.0, max=180.0,
    )
    follow_rot_z: FloatProperty(
        name="Z 軸回転 (水平回り)",
        default=0.0, min=-360.0, max=360.0,
    )
    follow_height: FloatProperty(name="Height", default=0.0)
    follow_side: FloatProperty(name="Side Offset", default=0.0)
    follow_damping: FloatProperty(
        name="Follow Damping", default=0.3, min=0.0, max=1.0,
    )
    follow_auto_lookat: BoolProperty(
        name="Auto Look at Follow Target",
        default=True,
    )

    # --- LookAt ---
    lookat_target: PointerProperty(
        name="LookAt Target", type=bpy.types.Object, poll=_is_object_poll,
    )
    lookat_damping: FloatProperty(
        name="LookAt Damping", default=0.3, min=0.0, max=1.0,
    )

    # --- Noise ---
    noise_enabled: BoolProperty(name="Noise", default=False)
    noise_strength_pos: FloatProperty(name="Noise Pos", default=0.05, min=0.0)
    noise_strength_rot: FloatProperty(name="Noise Rot (deg)", default=0.5, min=0.0)
    noise_frequency: FloatProperty(name="Noise Freq", default=0.5, min=0.0)
    noise_seed: IntProperty(name="Noise Seed", default=0, min=0)
