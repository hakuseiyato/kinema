"""Preset UIList。

Outliner の階層構造をそのまま反映する設計に変更（旧 `_` 分割グループは撤廃）。
親コレクションに Camera が無い場合、その親が "グループ" として扱われ、子は
インデント表示される。
"""

from __future__ import annotations

import bpy


class KINEMA_UL_presets(bpy.types.UIList):
    """プリセット一覧 UIList。"""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):  # noqa: ARG002
        row = layout.row(align=True)

        # 階層インデント: group ("Hero/Subgroup") のスラッシュ数だけ空アイコンを出す
        depth = item.group.count("/") + 1 if item.group else 0
        for _ in range(depth):
            row.label(text="", icon="BLANK1")

        # 名前
        row.label(text=item.name, icon="CAMERA_DATA")

        # 親パス表示（深さ > 0 のときのみ）
        if item.group:
            parent_label = item.group.split("/")[-1]
            row.label(text=f"in {parent_label}")

        # 右寄せ補助情報
        right = row.row(align=True)
        right.alignment = "RIGHT"
        if item.camera_name and item.camera_name != item.name:
            right.label(text=item.camera_name, icon="OUTLINER_OB_CAMERA")
        if item.has_anim:
            right.label(text="", icon="ANIM")
        if item.tags:
            right.label(text=item.tags, icon="BOOKMARKS")
        if item.default_lens and item.default_lens > 0.001:
            right.label(text=f"{item.default_lens:.0f}mm")
