"""Image Editor のヘッダに kinema コントロールを Append する。

kinema モード OFF 時は何も描画しない（早期 return）。OFF→ON のトグルだけは
全 Image Editor のヘッダから可能（kinema モードに入る入口）。
"""

from __future__ import annotations

import bpy

from . import host_resolver


def _header_draw(self, context):
    """IMAGE_HT_header に append される描画関数。"""
    layout = self.layout
    wm = context.window_manager
    if not hasattr(wm, "kinema"):
        return

    st = wm.kinema
    if st.timeline_mode_on:
        # ホスト Area のみ kinema コントロール群を表示
        if host_resolver.is_host_area(context.area, context.window):
            row = layout.row(align=True)
            row.label(text="Kinema Timeline", icon="CAMERA_DATA")
            row.separator()
            row.operator("kinema.add_shot_at_playhead", text="Add Shot", icon="ADD")
            row.operator("kinema.toggle_timeline_mode", text="", icon="X")
        # ホストでない Image Editor は触らない
    else:
        # kinema モード OFF: 全 Image Editor で kinema 起動ボタンだけ出す
        row = layout.row(align=True)
        row.separator()
        row.operator("kinema.toggle_timeline_mode", text="Kinema", icon="CAMERA_DATA")


def register() -> None:
    # 重複防止: 既に append 済みなら remove してから append
    try:
        bpy.types.IMAGE_HT_header.remove(_header_draw)
    except Exception:
        pass
    bpy.types.IMAGE_HT_header.append(_header_draw)


def unregister() -> None:
    try:
        bpy.types.IMAGE_HT_header.remove(_header_draw)
    except Exception:
        pass
