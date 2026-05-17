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

        # --- Quick Start バナー（Root が無い or 空の時に強調表示）---
        if not root_in_scene or not root_has_children:
            qs = layout.box()
            qs.label(text="Quick Start", icon="PLAY")
            qs.label(
                text=("Preset Root '{}' が未準備です".format(st.preset_root_name)
                      if not root_in_scene else
                      "Preset Root は空です。プリセットを追加してください"),
                icon="INFO",
            )
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
        row.label(text=f"Presets ({len(st.presets)})", icon="CAMERA_DATA")
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
