"""Preset UIList。"""

from __future__ import annotations

import bpy


class KINEMA_UL_presets(bpy.types.UIList):
    """プリセット一覧 UIList。グループヘッダ行と通常行で見た目を変える。"""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):  # noqa: ARG002,D401
        if item.is_header:
            row = layout.row()
            row.alignment = "LEFT"
            row.label(text=item.display_name or item.group, icon="DISCLOSURE_TRI_DOWN")
            return

        row = layout.row(align=True)
        row.label(text=item.display_name or item.name, icon="CAMERA_DATA")
        if item.has_anim:
            row.label(text="", icon="ANIM")
        if item.tags:
            row.label(text=f"[{item.tags}]")
        if item.default_lens and item.default_lens > 0.001:
            row.label(text=f"{item.default_lens:.0f}mm")
