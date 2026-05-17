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

        # --- cineflow 衝突警告 ---
        if _cineflow_enabled() and not _kinema_handlers_active():
            box = layout.box()
            box.alert = True
            box.label(text="cineflow が enabled です", icon="ERROR")
            box.label(text="kinema の frame_change handler は待機中")
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
        row.operator("kinema.refresh_instances", text="", icon="FILE_REFRESH")

        inst_box.template_list(
            "KINEMA_UL_instances", "",
            st, "instances",
            st, "active_instance_index",
            rows=4,
        )

        # --- Selected instance detail ---
        if 0 <= st.active_instance_index < len(st.instances):
            inst = st.instances[st.active_instance_index]
            cam = refs.safe_object(inst.camera_ref)
            if cam is not None:
                detail = layout.box()
                detail.label(text=f"Active: {inst.name}", icon="DOT")

                # Lens
                lens_row = detail.row(align=True)
                lens_row.prop(inst, "lens_mm")
                lens_row.operator("kinema.apply_lens", text="", icon="CHECKMARK")

                # Follow
                follow_col = detail.column(align=True)
                follow_col.label(text="Follow")
                follow_col.prop(inst, "follow_target", text="Target")
                if refs.safe_object(inst.follow_target):
                    follow_col.prop(inst, "follow_distance")
                    follow_col.prop(inst, "follow_height")
                    follow_col.prop(inst, "follow_side")
                    follow_col.prop(inst, "follow_damping")

                # LookAt
                look_col = detail.column(align=True)
                look_col.label(text="LookAt")
                look_col.prop(inst, "lookat_target", text="Target")
                if refs.safe_object(inst.lookat_target):
                    look_col.prop(inst, "lookat_damping")

                # Noise
                noise_col = detail.column(align=True)
                noise_col.prop(inst, "noise_enabled", text="Noise")
                if inst.noise_enabled:
                    noise_col.prop(inst, "noise_strength_pos")
                    noise_col.prop(inst, "noise_strength_rot")
                    noise_col.prop(inst, "noise_frequency")
                    noise_col.prop(inst, "noise_seed")
            else:
                layout.label(text="アクティブ Instance にカメラがありません", icon="ERROR")

        # --- Shot Timeline ---
        tl_box = layout.box()
        wm = context.window_manager
        tl_header = tl_box.row(align=True)
        tl_mode_on = hasattr(wm, "kinema") and wm.kinema.timeline_mode_on
        tl_header.label(
            text=f"Shot Timeline ({len(st.shot_clips)})",
            icon="SEQUENCE",
        )
        if tl_mode_on:
            tl_header.label(text="ON", icon="CHECKMARK")
        else:
            tl_header.label(text="OFF", icon="X")

        tl_box.label(
            text="Image Editor のヘッダから 'Kinema' を押すと有効化",
            icon="INFO",
        )
        tl_ops = tl_box.row(align=True)
        tl_ops.operator("kinema.add_shot_at_playhead", text="Add Shot", icon="ADD")
        tl_ops.operator("kinema.delete_active_shot", text="", icon="X")
        tl_ops.operator("kinema.clear_shots", text="Clear All", icon="TRASH")

        # 簡易 Shot 一覧（最大 6 件まで表示）
        if st.shot_clips:
            shots_col = tl_box.column(align=True)
            for clip in list(st.shot_clips)[:6]:
                row = shots_col.row(align=True)
                is_active = clip.uid == st.active_clip_uid
                row.label(
                    text=f"{clip.name}: F{clip.frame_start}-{clip.frame_end}",
                    icon="DOT" if is_active else "BLANK1",
                )
                if clip.camera is not None:
                    row.label(text=clip.camera.name, icon="OUTLINER_OB_CAMERA")
            if len(st.shot_clips) > 6:
                shots_col.label(text=f"... and {len(st.shot_clips) - 6} more")

        # --- Diagnostics ---
        diag_box = layout.box()
        diag_row = diag_box.row(align=True)
        diag_row.label(text="Diagnostics", icon="TOOL_SETTINGS")
        diag_row.operator("kinema.run_diagnostics", text="Run", icon="PLAY")
        diag_row.operator("kinema.toggle_handlers", text="", icon="FILE_REFRESH")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cineflow_enabled() -> bool:
    addons = bpy.context.preferences.addons
    return "cineflow" in addons.keys() or "bl_ext.user_default.cineflow" in addons.keys()


def _kinema_handlers_active() -> bool:
    return any(
        getattr(fn, "__name__", "") == "kinema_frame_change_pre"
        for fn in bpy.app.handlers.frame_change_pre
    )
