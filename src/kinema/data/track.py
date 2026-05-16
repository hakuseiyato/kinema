"""トラック（タイムライン上の縦列）。

v2.0 では SHOT のみ実装。他種別の骨格は v2.1 以降で実装する。
"""

from __future__ import annotations

import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatVectorProperty,
    IntProperty,
    StringProperty,
)


KIND_ITEMS = (
    ("SHOT", "Shot", "カメラショット"),
    ("AUDIO", "Audio", "音声（v2.1 で実装）"),
    ("VISIBILITY", "Visibility", "オブジェクト ON/OFF（v2.2 で実装）"),
    ("KEYFRAME", "Keyframe", "任意プロパティのキーフレーム（v2.3 で実装）"),
)


class KinemaTrack(bpy.types.PropertyGroup):
    uid: StringProperty(name="UID", default="")
    name: StringProperty(name="Name", default="Track")
    kind: EnumProperty(name="Kind", items=KIND_ITEMS, default="SHOT")
    order: IntProperty(name="Order", default=0)
    height: IntProperty(name="Height (px)", default=32, min=16, max=128)
    color_tint: FloatVectorProperty(
        name="Tint", subtype="COLOR", size=3, default=(0.7, 0.7, 0.8), min=0.0, max=1.0,
    )
    solo: BoolProperty(name="Solo", default=False)
    mute: BoolProperty(name="Mute", default=False)
    locked: BoolProperty(name="Locked", default=False)
    collapsed: BoolProperty(name="Collapsed", default=False)
