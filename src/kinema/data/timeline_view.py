"""TimelineView — タイムラインパネルの表示状態（スクロール / ズーム）。

session 単位の ホスト Area 識別子は WindowManager 側に置く（こちらは scene 側に
属する「表示の好み」だけを持つ）。
"""

from __future__ import annotations

import bpy
from bpy.props import EnumProperty, FloatProperty, IntProperty


SNAP_ITEMS = (
    ("FRAME", "Frame", "1 フレーム単位にスナップ"),
    ("SECOND", "Second", "1 秒単位にスナップ"),
    ("CLIP_EDGE", "Clip Edge", "クリップの端にスナップ"),
    ("PLAYHEAD", "Playhead", "プレイヘッドにスナップ"),
    ("NONE", "None", "スナップ無し"),
)


class KinemaTimelineView(bpy.types.PropertyGroup):
    # 横方向: フレームあたりピクセル数
    pixels_per_frame: FloatProperty(
        name="Pixels per Frame", default=4.0, min=0.1, max=50.0,
    )
    # 横スクロール: 表示開始フレーム
    scroll_frame: IntProperty(name="Scroll Frame", default=0)
    # 縦スクロール: 表示開始トラック index
    scroll_track: IntProperty(name="Scroll Track", default=0)
    # スナップ
    snap_mode: EnumProperty(name="Snap", items=SNAP_ITEMS, default="FRAME")
