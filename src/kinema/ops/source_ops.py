"""Preset ソース生成 Operator。

Yato さんが Preset 階層を手で組まずに済むよう、ワンクリックで揃える系の
Operator を集める。中身は `utils/source_init.py` の薄いラッパで、純粋ロジック
は将来 Yato Project Kit 側にも移植可能な形にしてある。
"""

from __future__ import annotations

import bpy

from ..utils import source_init
from ._base import KinemaOperator


class KINEMA_OT_init_preset_root(KinemaOperator):
    """Preset Root コレクションを作る（無ければ）。"""
    bl_idname = "kinema.init_preset_root"
    bl_label = "Initialize Preset Root"
    bl_description = "scene.kinema.preset_root_name のコレクションを Scene 直下に作成"

    def run(self, context):
        scene = context.scene
        st = scene.kinema
        root = source_init.ensure_preset_root(scene, st.preset_root_name)
        self.report({"INFO"}, f"Preset Root: {root.name}")
        return {"FINISHED"}


class KINEMA_OT_quick_start(KinemaOperator):
    """ワンクリック初期化（押すたびに新サンプル Camera を 1 件追加）。"""
    bl_idname = "kinema.quick_start"
    bl_label = "Quick Start (+1 Sample)"
    bl_description = "Preset Root を確保し、毎回新しいサンプル Camera を追加してスキャン"

    def run(self, context):
        scene = context.scene
        st = scene.kinema

        # Preset Root を確保
        root = source_init.ensure_preset_root(scene, st.preset_root_name)

        # 採番: Sample_Camera, Sample_Camera_001, Sample_Camera_002, ...
        # bpy.data.collections と bpy.data.objects 両方の名前空間で被らないように
        from ..utils import naming
        existing = set(bpy.data.collections.keys()) | set(bpy.data.objects.keys())
        unique_name = naming.next_unique_name("Sample_Camera", existing)

        # 新規 Collection + Camera Object をその場で作る
        sample_coll = bpy.data.collections.new(unique_name)
        root.children.link(sample_coll)
        cam_data = bpy.data.cameras.new(unique_name)
        cam_obj = bpy.data.objects.new(unique_name, cam_data)
        sample_coll.objects.link(cam_obj)

        # 自動でスキャン
        try:
            bpy.ops.kinema.scan_presets()
        except Exception:
            pass
        self.report(
            {"INFO"},
            f"Preset Root '{root.name}' にサンプル '{sample_coll.name}' を追加",
        )
        return {"FINISHED"}


class KINEMA_OT_capture_view_as_preset(KinemaOperator):
    """現在の 3D ビューから新規カメラを作って Preset Root にプリセット登録。"""
    bl_idname = "kinema.capture_view_as_preset"
    bl_label = "Capture View as Preset"
    bl_description = "現在のビューポート視点で新規カメラを作り、Preset として登録"

    def run(self, context):
        scene = context.scene
        st = scene.kinema
        root = source_init.ensure_preset_root(scene, st.preset_root_name)
        try:
            sub, cam = source_init.capture_view_as_new_preset(context, root)
        except ValueError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        try:
            bpy.ops.kinema.scan_presets()
        except Exception:
            pass
        self.report({"INFO"}, f"Preset 追加: {sub.name} (Camera: {cam.name})")
        return {"FINISHED"}


class KINEMA_OT_add_selected_cameras_as_presets(KinemaOperator):
    """選択中の Camera オブジェクトを Preset Root の配下にプリセットとして登録。"""
    bl_idname = "kinema.add_selected_cameras_as_presets"
    bl_label = "Add Selected Cameras"
    bl_description = "選択中のカメラオブジェクトを Preset Root にプリセットとして追加"

    def run(self, context):
        scene = context.scene
        st = scene.kinema
        cameras = [obj for obj in context.selected_objects if obj.type == "CAMERA"]
        if not cameras:
            self.report({"WARNING"}, "選択中の Camera オブジェクトがありません")
            return {"CANCELLED"}
        root = source_init.ensure_preset_root(scene, st.preset_root_name)
        for cam in cameras:
            source_init.register_camera_as_preset(scene, root, cam)
        try:
            bpy.ops.kinema.scan_presets()
        except Exception:
            pass
        self.report({"INFO"}, f"{len(cameras)} カメラを Preset 登録")
        return {"FINISHED"}
