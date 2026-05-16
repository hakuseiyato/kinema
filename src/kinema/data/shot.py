"""ShotClip — タイムラインの「カメラショット」1 区間。

各 Shot は所属トラック・フレーム範囲・カメラ・Lens/DoF オーバーライド・
Follow/LookAt/Noise パラメータを持つ。
"""

from __future__ import annotations

import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    FloatVectorProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)


TRANSITION_ITEMS = (
    ("CUT", "Cut", "瞬間切替（v2.0 はこれのみ実装）"),
    ("FADE", "Fade", "フェード（v2.4+）"),
    ("MIX", "Mix", "クロスフェード（v2.4+）"),
)


def _is_camera_poll(self, obj):
    return obj is None or obj.type == "CAMERA"


def _is_object_poll(self, obj):
    return True


class KinemaShotClip(bpy.types.PropertyGroup):
    # --- 基底（共通 Clip 基底相当）---
    uid: StringProperty(name="UID", default="")
    name: StringProperty(name="Name", default="Shot")
    track_uid: StringProperty(name="Track UID", default="")
    frame_start: IntProperty(name="Start", default=1, min=0)
    frame_end: IntProperty(name="End (exclusive)", default=51, min=1)
    color: FloatVectorProperty(
        name="Color", subtype="COLOR", size=3, default=(0.3, 0.6, 0.9), min=0.0, max=1.0,
    )
    locked: BoolProperty(name="Locked", default=False)
    mute: BoolProperty(name="Mute", default=False)
    notes: StringProperty(name="Notes", default="")

    # --- ショット固有 ---
    camera: PointerProperty(name="Camera", type=bpy.types.Object, poll=_is_camera_poll)
    lens_override: FloatProperty(
        name="Lens Override (mm)",
        description="0 で継承（カメラ data の lens をそのまま使用）",
        default=0.0,
        min=0.0,
    )

    dof_override: BoolProperty(name="DoF Override", default=False)
    dof_focus_distance: FloatProperty(name="Focus Distance", default=5.0, min=0.0)
    dof_fstop: FloatProperty(name="F-Stop", default=2.8, min=0.1)

    # --- Follow / LookAt / Noise（旧 cineflow 由来）---
    follow_target: PointerProperty(name="Follow Target", type=bpy.types.Object, poll=_is_object_poll)
    follow_distance: FloatProperty(name="Distance", default=5.0, min=0.0)
    follow_height: FloatProperty(name="Height", default=1.5)
    follow_side: FloatProperty(name="Side", default=0.0)
    follow_damping: FloatProperty(name="Follow Damping", default=0.3, min=0.0, max=1.0)

    lookat_target: PointerProperty(name="LookAt Target", type=bpy.types.Object, poll=_is_object_poll)
    lookat_damping: FloatProperty(name="LookAt Damping", default=0.3, min=0.0, max=1.0)

    noise_enabled: BoolProperty(name="Noise", default=False)
    noise_strength_pos: FloatProperty(name="Noise Pos", default=0.05, min=0.0)
    noise_strength_rot: FloatProperty(name="Noise Rot (deg)", default=0.5, min=0.0)
    noise_frequency: FloatProperty(name="Noise Freq", default=0.5, min=0.0)
    noise_seed: IntProperty(name="Noise Seed", default=0, min=0)

    # --- Transition（構造のみ、適用は v2.4+）---
    transition_in: EnumProperty(name="In", items=TRANSITION_ITEMS, default="CUT")
    transition_in_frames: IntProperty(name="In Frames", default=0, min=0)
    transition_out: EnumProperty(name="Out", items=TRANSITION_ITEMS, default="CUT")
    transition_out_frames: IntProperty(name="Out Frames", default=0, min=0)
