"""Camera Data に紐づく事前設定 PropertyGroup。

`bpy.types.Camera.kinema_preset` で Camera Data 単位に保持する。Instance と
同じスキーマで Follow / LookAt / Noise を持ち、`Load Selected Preset` 時に
Instance にコピーされる。

加えて、Preset として選択中（`scene.camera` がこの Camera と一致）の場合、
`instance_dispatcher` が `_apply_preview_preset` 経由でこの設定をライブ
プレビューとして適用する。各プロパティに update callback を仕込んで、
スライダー操作でも即時反映する。
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


def _apply_preview_now(self, context):
    """Preset プロパティ変更時にプレビューを即時更新。

    Instance の `_apply_now` と同じく `instance_dispatcher.dispatch` を呼ぶ。
    dispatch 側で「scene.camera が preset cam なら preview を適用」する判定
    が走るので、ここでは無条件で呼んで OK。
    """
    try:
        from ..runtime import instance_dispatcher  # noqa: PLC0415
        if instance_dispatcher._in_dispatch:
            return
        instance_dispatcher.dispatch(context.scene)
    except Exception:
        pass


class KinemaCameraPreset(bpy.types.PropertyGroup):
    """Camera Data に紐づく事前設定。Instance とフィールド構成を揃える。"""

    # --- Follow ---
    follow_target: PointerProperty(
        name="Follow Target", type=bpy.types.Object, poll=_is_object_poll,
        update=_apply_preview_now,
    )
    follow_distance: FloatProperty(
        name="Distance", default=5.0, min=0.0,
        update=_apply_preview_now,
    )
    follow_rot_x: FloatProperty(
        name="X 軸回転 (上下)",
        default=0.0, min=-89.0, max=89.0,
        update=_apply_preview_now,
    )
    follow_rot_y: FloatProperty(
        name="Y 軸回転 (ロール)",
        default=0.0, min=-180.0, max=180.0,
        update=_apply_preview_now,
    )
    follow_rot_z: FloatProperty(
        name="Z 軸回転 (水平回り)",
        default=0.0, min=-360.0, max=360.0,
        update=_apply_preview_now,
    )
    follow_height: FloatProperty(
        name="Height", default=0.0, update=_apply_preview_now,
    )
    follow_side: FloatProperty(
        name="Side Offset", default=0.0, update=_apply_preview_now,
    )
    follow_damping: FloatProperty(
        name="Follow Damping", default=0.3, min=0.0, max=1.0,
        update=_apply_preview_now,
    )
    follow_auto_lookat: BoolProperty(
        name="Auto Look at Follow Target",
        default=True,
        update=_apply_preview_now,
    )

    # --- LookAt ---
    lookat_target: PointerProperty(
        name="LookAt Target", type=bpy.types.Object, poll=_is_object_poll,
        update=_apply_preview_now,
    )
    lookat_damping: FloatProperty(
        name="LookAt Damping", default=0.3, min=0.0, max=1.0,
        update=_apply_preview_now,
    )

    # --- Noise ---
    noise_enabled: BoolProperty(
        name="Noise", default=False, update=_apply_preview_now,
    )
    noise_strength_pos: FloatProperty(
        name="Noise Pos", default=0.05, min=0.0,
        update=_apply_preview_now,
    )
    noise_strength_rot: FloatProperty(
        name="Noise Rot (deg)", default=0.5, min=0.0,
        update=_apply_preview_now,
    )
    noise_frequency: FloatProperty(
        name="Noise Freq", default=0.5, min=0.0,
        update=_apply_preview_now,
    )
    noise_seed: IntProperty(
        name="Noise Seed", default=0, min=0,
        update=_apply_preview_now,
    )
