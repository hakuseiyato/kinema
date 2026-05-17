"""Preset UIList。

コレクションごとにグループ化し、ヘッダ行で折り畳み可能にする。
"""

from __future__ import annotations

import bpy


class KINEMA_UL_presets(bpy.types.UIList):
    """プリセット一覧 UIList（コレクション別グループ + 折り畳み）。"""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):  # noqa: ARG002
        if item.is_header:
            # グループヘッダ行
            row = layout.row(align=True)
            tri_icon = "DISCLOSURE_TRI_RIGHT" if item.header_collapsed else "DISCLOSURE_TRI_DOWN"
            op = row.operator(
                "kinema.toggle_preset_group_collapse",
                text="", icon=tri_icon, emboss=False,
            )
            op.index = index
            row.label(text=item.display_name or item.group, icon="OUTLINER_COLLECTION")
            right = row.row(align=True)
            right.alignment = "RIGHT"
            right.label(text=f"({item.child_count})")
            return

        # 通常の Camera Preset 行
        row = layout.row(align=True)
        # インデントの代わりに空アイコンを 2 つ
        row.label(text="", icon="BLANK1")
        row.label(text=item.name, icon="OUTLINER_OB_CAMERA")

        right = row.row(align=True)
        right.alignment = "RIGHT"
        if item.has_anim:
            right.label(text="", icon="ANIM")
        if item.tags:
            right.label(text=item.tags, icon="BOOKMARKS")
        if item.default_lens and item.default_lens > 0.001:
            right.label(text=f"{item.default_lens:.0f}mm")

    def filter_items(self, context, data, propname):  # noqa: ARG002
        """折り畳まれているグループの子アイテムを非表示にする。"""
        items = getattr(data, propname)
        n = len(items)
        flt_flags = [self.bitflag_filter_item] * n

        # 折り畳まれたヘッダのグループ名を収集
        collapsed_groups: set[str] = set()
        for item in items:
            if item.is_header and item.header_collapsed:
                collapsed_groups.add(item.group)

        # 子を非表示にマーク
        for i, item in enumerate(items):
            if not item.is_header and item.group in collapsed_groups:
                flt_flags[i] = 0

        return flt_flags, []
