"""Shot Manager パネル（3D View > N panel > Yato tab）。

Phase 1: 旧 cuts[] と yato_vis.groups[].cast_markers の統合管理 UI。
- shots[] の UIList + Active Shot 編集
- Cast マトリクス（Active Shot のみ展開、UI 描画コスト抑制）
- Migrate / Sync / Diagnose ボタン
"""

from __future__ import annotations

import bpy

from ..utils import visibility_kit_bridge as _vkb


CATEGORY = "Yato"  # yato_visibility_kit と同じタブに同居


class KINEMA_UL_shots(bpy.types.UIList):
    bl_idname = "KINEMA_UL_shots"

    def draw_item(
        self, context, layout, data, item, icon, active_data, active_propname, index,
    ):
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            row = layout.row(align=True)
            row.prop(
                item, "enabled", text="",
                icon="HIDE_OFF" if item.enabled else "HIDE_ON",
                emboss=False,
            )
            if item.orphan:
                row.label(text="", icon="ERROR")
            else:
                row.label(text="", icon="MARKER_HLT")
            # name + marker
            if item.marker_name and item.marker_name != item.name:
                row.label(text=f"{item.name}  [{item.marker_name}]")
            else:
                row.label(text=item.name or "(unnamed)")
            # instance binding
            if item.instance_name:
                row.label(text=f"→ {item.instance_name}", icon="OUTLINER_OB_CAMERA")
            else:
                row.label(text="(no inst)", icon="QUESTION")
            # cast 数
            n_cast = sum(1 for c in item.cast if c.enabled)
            row.label(text=f"cast:{n_cast}")
        elif self.layout_type == "GRID":
            layout.alignment = "CENTER"
            layout.label(text="", icon="MARKER_HLT")


class KINEMA_PT_shot_manager(bpy.types.Panel):
    bl_label = "Shots"
    bl_idname = "KINEMA_PT_shot_manager"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = CATEGORY
    bl_order = 5

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        st = getattr(scene, "kinema", None)
        if st is None:
            layout.label(text="kinema PropertyGroup 未登録", icon="ERROR")
            return

        # データフォーマットバージョン警告
        dfv = getattr(st, "data_format_version", 1)
        if dfv < 2 and hasattr(st, "cuts") and len(st.cuts) > 0:
            warn = layout.box()
            warn.alert = True
            warn.label(text="旧 cuts[] データが残っています", icon="ERROR")
            warn.label(text=f"  cuts: {len(st.cuts)} 件")
            warn.operator(
                "kinema.migrate_to_shots", text="Migrate to Shots", icon="MOD_TIME",
            )
            layout.separator()

        # ツール行
        tools_row = layout.row(align=True)
        tools_row.operator(
            "kinema.sync_shots_from_markers", text="Sync", icon="FILE_REFRESH",
        )
        tools_row.operator(
            "kinema.migrate_to_shots", text="", icon="MOD_TIME",
        )
        tools_row.operator(
            "kinema.diagnose_shots", text="", icon="VIEWZOOM",
        )

        # 状態表示
        info = layout.row(align=True)
        n_total = len(st.shots)
        n_enabled = sum(1 for s in st.shots if s.enabled and not s.orphan)
        n_orphan = sum(1 for s in st.shots if s.orphan)
        info.label(text=f"Shots: {n_enabled}/{n_total}")
        if n_orphan:
            info.label(text=f"⚠ {n_orphan} orphan")
        if not _vkb.is_available(scene):
            info.label(text="(no yato_vis)", icon="QUESTION")

        # Shot リスト
        list_row = layout.row()
        list_row.template_list(
            "KINEMA_UL_shots", "",
            st, "shots",
            st, "active_shot_index",
            rows=6,
        )
        side = list_row.column(align=True)
        side.operator("kinema.add_shot", text="", icon="ADD")
        side.operator("kinema.remove_shot", text="", icon="REMOVE")
        side.separator()
        up = side.operator("kinema.move_shot", text="", icon="TRIA_UP")
        up.direction = -1
        dn = side.operator("kinema.move_shot", text="", icon="TRIA_DOWN")
        dn.direction = 1
        side.separator()
        side.operator("kinema.jump_to_shot", text="", icon="PLAY")
        side.operator("kinema.rename_shot", text="", icon="GREASEPENCIL")

        # Active Shot 編集
        idx = st.active_shot_index
        if not (0 <= idx < len(st.shots)):
            return
        shot = st.shots[idx]

        edit = layout.box()
        if shot.orphan:
            warn = edit.row()
            warn.alert = True
            warn.label(
                text=f"Marker '{shot.marker_name}' が見つかりません",
                icon="ERROR",
            )

        # 主要設定
        main = edit.column(align=True)
        main.use_property_split = True
        main.use_property_decorate = False
        nm_row = main.row(align=True)
        nm_row.label(text=f"Name: {shot.name}", icon="MARKER_HLT")
        nm_row.operator("kinema.rename_shot", text="Rename", icon="GREASEPENCIL")
        main.prop_search(shot, "instance_name", st, "instances", text="Instance")
        main.prop(shot, "enabled", text="Render Enabled")

        # フレーム範囲
        fr_row = main.row(align=True)
        fr_row.prop(shot, "frame_override", text="Override Frame Range")
        if not shot.frame_override:
            try:
                from ..ops.shot_ops import _resolve_shot_frame_range, _sorted_markers
                fs, fe = _resolve_shot_frame_range(scene, shot, _sorted_markers(scene))
                fr_row.label(text=f"F{fs} – {fe}")
            except Exception:
                pass
        else:
            rrow = main.column(align=True)
            rrow.prop(shot, "frame_start_override", text="Frame Start")
            rrow.prop(shot, "frame_end_override", text="End")

        main.prop(shot, "notes", text="Notes")

        # Marker 表示（情報のみ）
        adv = edit.row(align=True)
        adv.alignment = "RIGHT"
        adv.label(text=f"Marker: {shot.marker_name or '-'}",
                  icon="OUTLINER_DATA_GP_LAYER")

        # Cast マトリクス（Active Shot のみ展開で UI 軽量化）
        cast_box = edit.box()
        cast_hdr = cast_box.row(align=True)
        cast_hdr.label(text="Cast", icon="OUTLINER_OB_ARMATURE")
        all_groups = _vkb.all_group_names(scene)
        cast_names_active = {c.group_name for c in shot.cast if c.enabled}
        cast_hdr.label(text=f"{len(cast_names_active)} / {len(all_groups)} on stage")
        if not _vkb.is_available(scene):
            cast_box.label(
                text="yato_visibility_kit が無いので Cast は表示されません",
                icon="INFO",
            )
        elif not all_groups:
            cast_box.label(
                text="yato_vis.groups[] が空。Visibility パネルで Group 作成して下さい",
                icon="INFO",
            )
        else:
            for gname in all_groups:
                row = cast_box.row(align=True)
                is_on = gname in cast_names_active
                op = row.operator(
                    "kinema.shot_cast_toggle",
                    text="",
                    icon="CHECKBOX_HLT" if is_on else "CHECKBOX_DEHLT",
                    emboss=False,
                )
                op.group_name = gname
                row.label(text=gname)
