"""Instance 系 Operator。"""

from __future__ import annotations

import bpy
from bpy.props import IntProperty, FloatProperty

from ..utils import collections as kn_collections
from ..utils import refs
from ..runtime import follow_lookat
from ._base import KinemaOperator


class KINEMA_OT_unload_instance(KinemaOperator):
    """選択中のインスタンスをアンロード（コレクション削除）する。"""
    bl_idname = "kinema.unload_instance"
    bl_label = "Unload Instance"
    bl_description = "選択中の Instance をシーンから削除"

    index: IntProperty(default=-1)  # 指定があればその index、無ければ active

    def run(self, context):
        st = context.scene.kinema
        idx = self.index if self.index >= 0 else st.active_instance_index
        if idx < 0 or idx >= len(st.instances):
            self.report({"WARNING"}, "Instance が選択されていません")
            return {"CANCELLED"}
        inst = st.instances[idx]
        coll = refs.safe_collection(inst.collection_ref)
        cam = refs.safe_object(inst.camera_ref)
        # LookAt Proxy を掃除
        if cam is not None:
            follow_lookat.cleanup_lookat_proxy(cam)
        if coll is not None:
            kn_collections.remove_collection_recursive(coll)
        st.instances.remove(idx)
        st.active_instance_index = max(0, min(idx, len(st.instances) - 1))
        return {"FINISHED"}


class KINEMA_OT_preview_instance(KinemaOperator):
    """選択中の Instance のカメラを scene.camera にする（カメラビューには切替えない）。"""
    bl_idname = "kinema.preview_instance"
    bl_label = "Preview Camera"
    bl_description = "選択中の Instance のカメラを scene.camera に設定"

    index: IntProperty(default=-1)

    def run(self, context):
        scene = context.scene
        st = scene.kinema
        idx = self.index if self.index >= 0 else st.active_instance_index
        if idx < 0 or idx >= len(st.instances):
            return {"CANCELLED"}
        inst = st.instances[idx]
        cam = refs.safe_object(inst.camera_ref)
        if not refs.is_camera_object(cam):
            self.report({"WARNING"}, "カメラが見つかりません")
            return {"CANCELLED"}
        scene.camera = cam
        return {"FINISHED"}


class KINEMA_OT_apply_lens(KinemaOperator):
    """選択中の Instance に焦点距離を適用。"""
    bl_idname = "kinema.apply_lens"
    bl_label = "Apply Lens"
    bl_description = "選択中の Instance のカメラに lens_mm を即時反映"

    lens: FloatProperty(default=0.0, min=0.0)

    def run(self, context):
        st = context.scene.kinema
        idx = st.active_instance_index
        if idx < 0 or idx >= len(st.instances):
            return {"CANCELLED"}
        inst = st.instances[idx]
        cam = refs.safe_object(inst.camera_ref)
        if not refs.is_camera_object(cam) or cam.data is None:
            return {"CANCELLED"}
        lens = self.lens if self.lens > 0.001 else inst.lens_mm
        cam.data.lens = lens
        inst.lens_mm = lens
        return {"FINISHED"}


class KINEMA_OT_refresh_instances(KinemaOperator):
    """Outliner で削除/リネームされた Instance を整理する。"""
    bl_idname = "kinema.refresh_instances"
    bl_label = "Refresh Instances"
    bl_description = "削除済み参照のクリーンアップとリネーム同期"

    def run(self, context):
        st = context.scene.kinema
        removed = 0
        # 後ろから走査して安全に削除
        for i in range(len(st.instances) - 1, -1, -1):
            inst = st.instances[i]
            coll = refs.safe_collection(inst.collection_ref)
            cam = refs.safe_object(inst.camera_ref)
            if coll is None and cam is None:
                st.instances.remove(i)
                removed += 1
                continue
            # 名前を同期
            if coll is not None and inst.name != coll.name:
                inst.name = coll.name
        if removed:
            self.report({"INFO"}, f"Cleaned up {removed} stale instances")
        return {"FINISHED"}
