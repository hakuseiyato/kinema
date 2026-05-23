"""Preset UIList。

コレクションごとにグループ化し、ヘッダ行で折り畳み可能にする。
ヘッダ行とカメラ行を **アイコン形状・色・インデント** でしっかり差別化する。
"""

from __future__ import annotations

import bpy


class KINEMA_UL_presets(bpy.types.UIList):
    """プリセット一覧 UIList（コレクション別グループ + 折り畳み）。"""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):  # noqa: ARG002
        if item.is_header:
            # ========================
            # グループヘッダ行
            # ========================
            # 行をやや背を高くして強調 + 黄色いコレクションアイコン
            row = layout.row(align=True)
            row.scale_y = 1.15
            tri_icon = "DISCLOSURE_TRI_RIGHT" if item.header_collapsed else "DISCLOSURE_TRI_DOWN"
            op = row.operator(
                "kinema.toggle_preset_group_collapse",
                text="", icon=tri_icon, emboss=False,
            )
            op.index = index
            # コレクションアイコン（黄色フォルダ）
            row.label(text="", icon="OUTLINER_COLLECTION")
            # ヘッダ名は ALL CAPS で目立たせる
            label_text = (item.display_name or item.group).upper()
            row.label(text=label_text)
            right = row.row(align=True)
            right.alignment = "RIGHT"
            right.label(text=f"[{item.child_count}]")
            return

        # ========================
        # 通常の Camera Preset 行
        # ========================
        row = layout.row(align=True)
        # グループ配下なら BLANK1 を 2 個重ねて深くインデント。
        # ルート直下は 1 個だけ（折り畳み三角の代わり）。
        if item.group:
            row.label(text="", icon="BLANK1")
            row.label(text="", icon="BLANK1")
        else:
            row.label(text="", icon="BLANK1")
        # Camera Data アイコン（緑系のカメラ筐体シルエット）— コレクションの
        # 黄色フォルダと色・形状ともに違うのでぱっと見で区別可能
        row.label(text="", icon="CAMERA_DATA")
        row.label(text=item.name)

        # 右寄せ補助情報
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
