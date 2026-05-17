"""Preset UIList。

情報量を増やしすぎないバランスで、判別に必要なものだけ表示する:
  - 通常行: [カメラアイコン] <フル名 or ショート名> [カメラ名] [タグ] [レンズ]
  - グループヘッダ: [▼アイコン] <グループ名>
"""

from __future__ import annotations

import bpy


class KINEMA_UL_presets(bpy.types.UIList):
    """プリセット一覧 UIList。"""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):  # noqa: ARG002,D401
        if item.is_header:
            row = layout.row()
            row.alignment = "LEFT"
            row.label(text=item.group, icon="OUTLINER_OB_GROUP_INSTANCE")
            return

        # 通常行: グループ配下にぶら下がっているならインデントして表示
        outer = layout.row(align=True)
        if item.group:
            # グループ内: ショート名 + 元の完全名 (parenthesized)
            outer.label(text="", icon="BLANK1")  # インデント
            label_text = item.short_name or item.name
            outer.label(text=label_text, icon="CAMERA_DATA")
            # 元のコレクション名（フル）も小さく
            if item.name and item.name != label_text:
                outer.label(text=f"({item.name})")
        else:
            outer.label(text=item.name, icon="CAMERA_DATA")

        # 補助情報を右寄せ
        right = outer.row(align=True)
        right.alignment = "RIGHT"
        if item.camera_name and item.camera_name != item.short_name:
            right.label(text=item.camera_name, icon="OUTLINER_OB_CAMERA")
        if item.has_anim:
            right.label(text="", icon="ANIM")
        if item.tags:
            right.label(text=item.tags, icon="BOOKMARKS")
        if item.default_lens and item.default_lens > 0.001:
            right.label(text=f"{item.default_lens:.0f}mm")
