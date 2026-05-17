"""Video Sequencer のヘッダに kinema コントロールを Append する。

kinema モード OFF 時は全 Sequencer エディタで起動ボタンを表示。
ON 時は **ホスト Area のみ** で Kinema コントロールを表示し、他の Sequencer
は標準の状態を保つ。
"""

from __future__ import annotations

import bpy

from . import host_resolver


def _header_draw(self, context):
    """SEQUENCER_HT_header に append される描画関数。"""
    layout = self.layout
    wm = context.window_manager
    if not hasattr(wm, "kinema"):
        return

    st = wm.kinema
    if st.timeline_mode_on:
        if host_resolver.is_host_area(context.area, context.window):
            row = layout.row(align=True)
            row.separator()
            row.label(text="Kinema Timeline", icon="CAMERA_DATA")
            row.operator("kinema.add_shot_at_playhead", text="Add Shot", icon="ADD")
            row.operator("kinema.toggle_timeline_mode", text="", icon="X")
    else:
        # OFF: 全 Sequencer エディタで kinema 起動ボタンを出す
        row = layout.row(align=True)
        row.separator()
        row.operator("kinema.toggle_timeline_mode", text="Kinema", icon="CAMERA_DATA")


def register() -> None:
    try:
        bpy.types.SEQUENCER_HT_header.remove(_header_draw)
    except Exception:
        pass
    bpy.types.SEQUENCER_HT_header.append(_header_draw)


def unregister() -> None:
    try:
        bpy.types.SEQUENCER_HT_header.remove(_header_draw)
    except Exception:
        pass
