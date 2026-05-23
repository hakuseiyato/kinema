"""Properties > Scene > Kinema パネル。

alpha1 は Cameras タブのみ実装。Pose / Lens & DoF / Behavior / Settings は
後続のリリースで追加していく。
"""

from __future__ import annotations

import bpy

from ..config import constants as C
from ..runtime import handlers as handler_mod
from ..utils import refs


class KINEMA_PT_main(bpy.types.Panel):
    bl_label = "Kinema"
    bl_idname = "KINEMA_PT_main"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"

    def draw(self, context):  # type: ignore[override]
        layout = self.layout
        scene = context.scene
        st = getattr(scene, "kinema", None)
        if st is None:
            layout.label(text="kinema PropertyGroup が未登録です", icon="ERROR")
            return

        # --- cineflow 衝突警告 + Import ---
        if _cineflow_enabled() and not _kinema_handlers_active():
            box = layout.box()
            box.alert = True
            box.label(text="cineflow が enabled です", icon="ERROR")
            box.label(text="kinema の frame_change handler は待機中")
            box.operator(
                "kinema.import_from_cineflow",
                text="Import from cineflow",
                icon="IMPORT",
            )
            box.operator(
                "kinema.disable_cineflow_and_enable_handlers",
                icon="UNLINKED",
            )

        # --- Workspace ---
        ws_box = layout.box()
        ws_box.label(text="Workspace", icon="WORKSPACE")
        ws = bpy.data.workspaces.get(C.KN_WORKSPACE_NAME)
        if ws is None:
            ws_box.operator("kinema.create_workspace", icon="ADD")
        else:
            row = ws_box.row(align=True)
            row.label(text=f"'{C.KN_WORKSPACE_NAME}' 作成済み", icon="CHECKMARK")
            row.operator("kinema.remove_workspace", text="", icon="X")

        # --- Source ---
        src = layout.box()
        src.label(text="Source", icon="OUTLINER_COLLECTION")
        src.prop(st, "preset_root_name")
        src.prop(st, "instances_root_name")

        # Preset Root の状態判定
        preset_root_coll = bpy.data.collections.get(st.preset_root_name)
        root_in_scene = preset_root_coll is not None and any(
            c == preset_root_coll for c in scene.collection.children
        )
        root_has_children = root_in_scene and bool(list(preset_root_coll.children))

        # --- Quick Start / Source 追加（常設）---
        qs = layout.box()
        qs.label(text="Quick Start / Add Source", icon="PLAY")
        if not root_in_scene:
            qs.label(
                text=f"Preset Root '{st.preset_root_name}' が未準備です",
                icon="INFO",
            )
        elif not root_has_children:
            qs.label(text="Preset Root は空です", icon="INFO")
        qs.operator("kinema.quick_start", icon="SOLO_ON")
        row = qs.row(align=True)
        row.operator("kinema.init_preset_root", text="Init Root", icon="ADD")
        row.operator("kinema.capture_view_as_preset", text="Capture View", icon="VIEW_CAMERA")
        qs.operator(
            "kinema.add_selected_cameras_as_presets",
            text="Add Selected Cameras",
            icon="OUTLINER_OB_CAMERA",
        )

        # --- Presets ---
        preset_box = layout.box()
        row = preset_box.row(align=True)
        # is_header を除いた件数
        cam_count = sum(1 for p in st.presets if not p.is_header)
        row.label(text=f"Presets ({cam_count} cameras)", icon="OUTLINER_OB_CAMERA")
        row.operator("kinema.scan_presets", text="", icon="FILE_REFRESH")

        preset_box.template_list(
            "KINEMA_UL_presets", "",
            st, "presets",
            st, "active_preset_index",
            rows=6,
        )
        preset_box.operator("kinema.load_preset", icon="IMPORT")

        # 通常モードでも Source 追加系を畳んで配置（Root 準備済の時）
        if root_in_scene and root_has_children:
            add_row = preset_box.row(align=True)
            add_row.operator("kinema.capture_view_as_preset", text="Capture View", icon="VIEW_CAMERA")
            add_row.operator(
                "kinema.add_selected_cameras_as_presets",
                text="Add Selected",
                icon="OUTLINER_OB_CAMERA",
            )

        # --- Instances ---
        inst_box = layout.box()
        row = inst_box.row(align=True)
        row.label(text=f"Instances ({len(st.instances)})", icon="OUTLINER_OB_CAMERA")
        row.prop(
            st, "auto_preview_on_select", text="",
            icon="HIDE_OFF" if st.auto_preview_on_select else "HIDE_ON",
        )
        row.operator("kinema.duplicate_instance", text="", icon="DUPLICATE")
        row.operator("kinema.refresh_instances", text="", icon="FILE_REFRESH")

        # リスト + 並べ替えボタン
        list_row = inst_box.row(align=True)
        list_row.template_list(
            "KINEMA_UL_instances", "",
            st, "instances",
            st, "active_instance_index",
            rows=4,
        )
        side = list_row.column(align=True)
        up = side.operator("kinema.move_instance", text="", icon="TRIA_UP")
        up.direction = "UP"
        dn = side.operator("kinema.move_instance", text="", icon="TRIA_DOWN")
        dn.direction = "DOWN"

        # --- Selected instance detail ---
        if 0 <= st.active_instance_index < len(st.instances):
            inst = st.instances[st.active_instance_index]
            cam = refs.safe_object(inst.camera_ref)
            if cam is not None:
                detail = layout.box()
                # Lock 中は中身を編集不可（灰色）
                detail.enabled = not getattr(inst, "locked", False)
                # Auto Keyframe ON 中は警告色で目立たせる
                ts_auto_kf = scene.tool_settings.use_keyframe_insert_auto
                if ts_auto_kf:
                    detail.alert = True
                head = detail.row(align=True)
                head.enabled = True  # ヘッダは常に有効
                lock_icon = "LOCKED" if inst.locked else "DOT"
                label_text = f"Active: {inst.name}"
                if ts_auto_kf:
                    label_text = "● REC  " + label_text
                head.label(text=label_text, icon=lock_icon)
                # Key 関連ボタン
                key_row = head.row(align=True)
                key_row.alignment = "RIGHT"
                ts = scene.tool_settings
                key_row.operator(
                    "kinema.toggle_auto_keyframe",
                    text="",
                    icon="REC" if ts.use_keyframe_insert_auto else "RADIOBUT_OFF",
                    depress=ts.use_keyframe_insert_auto,
                )
                key_row.operator("kinema.keyframe_all", text="Key All", icon="KEY_HLT")
                key_row.operator(
                    "kinema.clear_unchanged_keys", text="", icon="KEY_DEHLT",
                )
                key_row.operator(
                    "kinema.bake_animation", text="", icon="REC",
                )
                key_row.operator(
                    "kinema.rebuild_keying_set", text="", icon="KEYINGSET",
                )
                # 一括コピペ
                cpy_all = key_row.operator(
                    "kinema.copy_settings", text="", icon="COPYDOWN",
                )
                cpy_all.category = "all"
                paste_all = key_row.operator(
                    "kinema.paste_settings", text="", icon="PASTEDOWN",
                )
                paste_all.category = "all"

                # Lens & Shift (Pose カテゴリ)
                pose_header = detail.row(align=True)
                pose_header.label(text="Lens / Shift", icon="OBJECT_ORIGIN")
                _draw_copy_paste(pose_header, "pose")

                lens_row = detail.row(align=True)
                lens_row.prop(inst, "lens_mm")
                lens_row.operator("kinema.apply_lens", text="", icon="CHECKMARK")

                if cam.data is not None:
                    shift_row = detail.row(align=True)
                    shift_row.prop(cam.data, "shift_x", text="X")
                    shift_row.prop(cam.data, "shift_y", text="Y")

                # Depth of Field（Camera Data.dof 直接編集）
                if cam.data is not None:
                    dof = cam.data.dof
                    dof_box = detail.box()
                    dof_head = dof_box.row(align=True)
                    dof_head.prop(
                        dof, "use_dof",
                        text="Depth of Field", icon="CON_CAMERASOLVER",
                    )
                    _draw_copy_paste(dof_head, "dof")
                    if dof.use_dof:
                        dof_box.prop(dof, "focus_object", text="Focus Object")
                        if dof.focus_object is None:
                            dof_box.prop(dof, "focus_distance", text="Focus Distance")
                        aperture = dof_box.column(align=True)
                        aperture.label(text="Aperture")
                        aperture.prop(dof, "aperture_fstop", text="F-Stop")
                        aperture.prop(dof, "aperture_blades", text="Blades")
                        aperture.prop(dof, "aperture_rotation", text="Rotation")
                        aperture.prop(dof, "aperture_ratio", text="Ratio")

                # Follow
                follow_col = detail.column(align=True)
                follow_head = follow_col.row(align=True)
                follow_head.label(text="Follow")
                _draw_copy_paste(follow_head, "follow")
                follow_col.prop(inst, "follow_target", text="Target")
                if refs.safe_object(inst.follow_target):
                    follow_col.prop(inst, "follow_distance")

                    # X / Y / Z 軸回転 + プリセット
                    angle_box = follow_col.box()
                    angle_box.label(text="Rotation (X / Y / Z)", icon="ORIENTATION_GIMBAL")
                    angle_box.prop(inst, "follow_rot_x")
                    angle_box.prop(inst, "follow_rot_y")
                    angle_box.prop(inst, "follow_rot_z")
                    angle_box.label(
                        text="※ Y 軸 (Roll) は LookAt Target 無効時のみ反映",
                        icon="INFO",
                    )
                    preset_row = angle_box.row(align=True)
                    for label, rx, rz in (
                        ("Front", 0.0, 0.0),
                        ("Right", 0.0, 90.0),
                        ("Back", 0.0, 180.0),
                        ("Left", 0.0, -90.0),
                    ):
                        op = preset_row.operator(
                            "kinema.set_follow_angle", text=label,
                        )
                        op.rot_x = rx
                        op.rot_y = 0.0
                        op.rot_z = rz

                    follow_col.prop(inst, "follow_height")
                    follow_col.prop(inst, "follow_side")
                    follow_col.prop(inst, "follow_damping")
                    follow_col.prop(inst, "follow_auto_lookat")

                # LookAt
                look_col = detail.column(align=True)
                look_head = look_col.row(align=True)
                look_head.label(text="LookAt")
                _draw_copy_paste(look_head, "lookat")
                look_col.prop(inst, "lookat_target", text="Target")
                # 明示指定がない場合に Follow Target を自動注視している旨を表示
                if (
                    not refs.safe_object(inst.lookat_target)
                    and refs.safe_object(inst.follow_target)
                    and inst.follow_auto_lookat
                ):
                    look_col.label(
                        text=f"→ Auto: {inst.follow_target.name}",
                        icon="HIDE_OFF",
                    )
                if refs.safe_object(inst.lookat_target) or (
                    refs.safe_object(inst.follow_target) and inst.follow_auto_lookat
                ):
                    look_col.prop(inst, "lookat_damping")

                # Noise
                noise_col = detail.column(align=True)
                noise_head = noise_col.row(align=True)
                noise_head.prop(inst, "noise_enabled", text="Noise")
                _draw_copy_paste(noise_head, "noise")
                if inst.noise_enabled:
                    noise_col.prop(inst, "noise_strength_pos")
                    noise_col.prop(inst, "noise_strength_rot")
                    noise_col.prop(inst, "noise_frequency")
                    noise_col.prop(inst, "noise_seed")
            else:
                layout.label(text="アクティブ Instance にカメラがありません", icon="ERROR")

        # --- Render ---
        render_box = layout.box()
        render_box.label(text="Render", icon="RENDER_ANIMATION")
        render_box.label(
            text=f"Base: {scene.render.filepath}",
            icon="FILE_FOLDER",
        )
        # Marker 件数表示
        n_markers = sum(
            1 for m in scene.timeline_markers if m.camera is not None
        )
        if n_markers > 0:
            render_box.label(
                text=f"Camera Markers: {n_markers}",
                icon="MARKER_HLT",
            )
        rrow = render_box.row(align=True)
        rrow.operator(
            "kinema.render_by_markers",
            text="By Markers",
            icon="MARKER",
        )
        rrow.operator(
            "kinema.render_active_instance",
            text="Active Only",
            icon="OUTLINER_OB_CAMERA",
        )

        # --- Import / Export ---
        io_box = layout.box()
        io_box.label(text="Import / Export", icon="FILE")
        io_row = io_box.row(align=True)
        io_row.operator("kinema.export_json", text="Export JSON", icon="EXPORT")
        io_row.operator("kinema.import_json", text="Import JSON", icon="IMPORT")

        # --- Diagnostics ---
        diag_box = layout.box()
        diag_row = diag_box.row(align=True)
        diag_row.label(text="Diagnostics", icon="TOOL_SETTINGS")
        diag_row.operator("kinema.run_diagnostics", text="Run", icon="PLAY")
        diag_row.operator("kinema.toggle_handlers", text="", icon="FILE_REFRESH")

        # 最新 Run の出力をパネル内に貼り付け
        wm = context.window_manager
        if hasattr(wm, "kinema_clipboard"):
            log = wm.kinema_clipboard.diag_log
            if log:
                log_box = diag_box.box()
                log_col = log_box.column(align=True)
                log_col.scale_y = 0.8
                for line in log.split("\n"):
                    tag = "OK"
                    icon = "CHECKMARK"
                    if "[NG]" in line:
                        icon = "ERROR"
                    elif "[WARN]" in line:
                        icon = "INFO"
                    elif "[--]" in line:
                        icon = "BLANK1"
                    log_col.label(text=line, icon=icon)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _draw_copy_paste(layout, category: str) -> None:
    """セクションヘッダ用の Copy / Paste アイコン群。

    Paste は 2 種:
      - PASTEDOWN: Active Instance のみ
      - PASTEDOWN_MULTIPLE: Outliner で選択中のカメラに紐づく全 Instance
    """
    right = layout.row(align=True)
    right.alignment = "RIGHT"
    cpy = right.operator("kinema.copy_settings", text="", icon="COPYDOWN")
    cpy.category = category
    pst = right.operator("kinema.paste_settings", text="", icon="PASTEDOWN")
    pst.category = category
    pst.target = "ACTIVE"
    pst_sel = right.operator(
        "kinema.paste_settings", text="", icon="GROUP_VERTEX",
    )
    pst_sel.category = category
    pst_sel.target = "SELECTED"


def _cineflow_enabled() -> bool:
    addons = bpy.context.preferences.addons
    return "cineflow" in addons.keys() or "bl_ext.user_default.cineflow" in addons.keys()


def _kinema_handlers_active() -> bool:
    return any(
        getattr(fn, "__name__", "") == "kinema_frame_change_pre"
        for fn in bpy.app.handlers.frame_change_pre
    )
