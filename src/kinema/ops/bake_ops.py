"""Active Instance のカメラを scene.frame_start〜frame_end でベイク。

Follow / LookAt / Noise の damping 効果を全フレームの keyframe として焼き込み、
独立した f-curve として後段で手動編集できる状態にする。

内部で `bpy.ops.nla.bake` を使う。Operator override で active object を
切替えてから実行する。
"""

from __future__ import annotations

import bpy

from ..utils import refs
from ._base import KinemaOperator


class KINEMA_OT_bake_animation(KinemaOperator):
    """Active Instance のカメラを scene.frame_start〜frame_end で bake。"""
    bl_idname = "kinema.bake_animation"
    bl_label = "Bake Camera Animation"
    bl_description = (
        "Active Instance のカメラに対し、scene.frame_start〜frame_end で"
        " location / rotation を毎フレームキーフレーム化（visual keying）"
    )

    def invoke(self, context, event):  # noqa: ARG002
        return context.window_manager.invoke_props_dialog(self, width=380)

    def draw(self, context):  # noqa: ARG002
        st = context.scene.kinema
        idx = st.active_instance_index
        layout = self.layout
        layout.label(text="Bake Camera Animation", icon="REC")
        layout.separator()
        if 0 <= idx < len(st.instances):
            inst = st.instances[idx]
            cam = inst.camera_ref
            cam_name = cam.name if cam is not None else "(none)"
            layout.label(text=f"対象: {cam_name}")
            layout.label(
                text=f"フレーム: {context.scene.frame_start} – {context.scene.frame_end}",
            )
            layout.label(text="Follow/LookAt/Noise の効果を毎フレームに焼き込みます")
            layout.label(text="（既存の f-curve は上書きされます）", icon="INFO")
        else:
            layout.label(text="Instance が選択されていません", icon="ERROR")

    def run(self, context):
        scene = context.scene
        st = scene.kinema
        idx = st.active_instance_index
        if idx < 0 or idx >= len(st.instances):
            self.report({"WARNING"}, "Instance が選択されていません")
            return {"CANCELLED"}
        inst = st.instances[idx]
        cam = refs.safe_object(inst.camera_ref)
        if not refs.is_camera_object(cam):
            self.report({"ERROR"}, "Active Instance にカメラがありません")
            return {"CANCELLED"}

        # bake 対象カメラを active object に
        try:
            for o in context.view_layer.objects:
                try:
                    o.select_set(False)
                except Exception:
                    pass
            cam.select_set(True)
            context.view_layer.objects.active = cam
        except Exception as exc:
            self.report({"ERROR"}, f"カメラ選択失敗: {exc}")
            return {"CANCELLED"}

        # bake 実行
        try:
            bpy.ops.nla.bake(
                frame_start=scene.frame_start,
                frame_end=scene.frame_end,
                only_selected=True,
                visual_keying=True,
                clear_constraints=False,
                clear_parents=False,
                bake_types={"OBJECT"},
            )
        except Exception as exc:
            self.report({"ERROR"}, f"Bake 失敗: {exc}")
            return {"CANCELLED"}

        self.report(
            {"INFO"},
            f"Baked {cam.name}: F{scene.frame_start}–{scene.frame_end}",
        )
        return {"FINISHED"}
