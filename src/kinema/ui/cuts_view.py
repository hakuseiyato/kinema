"""Cuts UIList — Timeline Marker と紐付くカット一覧。"""

from __future__ import annotations

import bpy


class KINEMA_UL_cuts(bpy.types.UIList):
    bl_idname = "KINEMA_UL_cuts"

    def draw_item(
        self, context, layout, data, item, icon, active_data, active_propname, index
    ):
        # item: KinemaCut
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            row = layout.row(align=True)
            # enabled トグル
            row.prop(item, "enabled", text="", icon="HIDE_OFF" if item.enabled else "HIDE_ON",
                     emboss=False)
            # orphan インジケータ
            if item.orphan:
                row.label(text="", icon="ERROR")
            else:
                row.label(text="", icon="MARKER_HLT")
            # 名前 + Marker 名（不一致なら両方表示）
            if item.marker_name and item.marker_name != item.name:
                row.label(text=f"{item.name}  ↔  [{item.marker_name}]")
            else:
                row.label(text=item.name or "(unnamed)")
            # Instance 表示
            if item.instance_name:
                row.label(text=f"→ {item.instance_name}", icon="OUTLINER_OB_CAMERA")
            else:
                row.label(text="(no instance)", icon="QUESTION")
        elif self.layout_type == "GRID":
            layout.alignment = "CENTER"
            layout.label(text="", icon="MARKER_HLT")
