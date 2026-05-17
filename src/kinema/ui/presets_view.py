"""Preset UIList。

新仕様: Camera オブジェクト 1 つ = 1 行。所属コレクション階層を group 列で表示。
"""

from __future__ import annotations

import bpy


class KINEMA_UL_presets(bpy.types.UIList):
    """プリセット一覧 UIList（Camera ベース）。"""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):  # noqa: ARG002
        row = layout.row(align=True)

        # 階層インデント
        depth = item.group.count("/") + 1 if item.group else 0
        for _ in range(depth):
            row.label(text="", icon="BLANK1")

        # メイン: Camera オブジェクト名
        row.label(text=item.name, icon="OUTLINER_OB_CAMERA")

        # 所属コレクション（最も近い親）
        if item.group:
            parent_label = item.group.split("/")[-1]
            row.label(text=f"in {parent_label}", icon="OUTLINER_COLLECTION")

        # 右寄せ補助情報
        right = row.row(align=True)
        right.alignment = "RIGHT"
        if item.has_anim:
            right.label(text="", icon="ANIM")
        if item.tags:
            right.label(text=item.tags, icon="BOOKMARKS")
        if item.default_lens and item.default_lens > 0.001:
            right.label(text=f"{item.default_lens:.0f}mm")
