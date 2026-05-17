"""Instance 系 Operator。"""

from __future__ import annotations

import bpy
from bpy.props import IntProperty, FloatProperty

from ..utils import collections as kn_collections
from ..utils import refs
from ..runtime import follow_lookat
from ._base import KinemaOperator


class KINEMA_OT_duplicate_instance(KinemaOperator):
    """選択中の Instance を複製する。

    複製先は Instances Root の配下に新規サブコレクション、新規 Camera オブジェクト
    として作る。Follow/LookAt/Noise / Lens 等のパラメータも丸ごとコピー。
    """
    bl_idname = "kinema.duplicate_instance"
    bl_label = "Duplicate Instance"
    bl_description = "選択中の Instance を関連オブジェクトごと複製"

    index: IntProperty(default=-1)

    def run(self, context):
        scene = context.scene
        st = scene.kinema
        idx = self.index if self.index >= 0 else st.active_instance_index
        if idx < 0 or idx >= len(st.instances):
            self.report({"WARNING"}, "Instance が選択されていません")
            return {"CANCELLED"}

        src = st.instances[idx]
        src_cam = refs.safe_object(src.camera_ref)
        if not refs.is_camera_object(src_cam):
            self.report({"ERROR"}, "複製元 Camera が見つかりません")
            return {"CANCELLED"}

        src_coll = refs.safe_collection(src.collection_ref)
        instances_root = kn_collections.get_or_create_instances_root(
            scene, st.instances_root_name,
        )

        # Camera + 関連オブジェクトを複製
        try:
            new_coll, new_cam = kn_collections.duplicate_camera_as_instance(
                src_cam, instances_root,
                root_scope=src_coll,  # 元のコレクション内で関連を探す
                base_name=src_coll.name if src_coll else src_cam.name,
            )
        except Exception as exc:
            self.report({"ERROR"}, f"複製失敗: {exc}")
            return {"CANCELLED"}

        # Instance Item を新規追加して元のパラメータをコピー
        inst = st.instances.add()
        inst.name = new_coll.name
        inst.source_preset = src.source_preset
        inst.collection_ref = new_coll
        inst.camera_ref = new_cam
        inst.enabled = src.enabled
        inst.lens_mm = src.lens_mm

        # Follow / LookAt / Noise パラメータをコピー
        inst.follow_target = src.follow_target
        inst.follow_distance = src.follow_distance
        inst.follow_height = src.follow_height
        inst.follow_side = src.follow_side
        inst.follow_damping = src.follow_damping
        inst.lookat_target = src.lookat_target
        inst.lookat_damping = src.lookat_damping
        inst.noise_enabled = src.noise_enabled
        inst.noise_strength_pos = src.noise_strength_pos
        inst.noise_strength_rot = src.noise_strength_rot
        inst.noise_frequency = src.noise_frequency
        inst.noise_seed = src.noise_seed

        # 実カメラの lens も同期
        if new_cam.data is not None and src_cam.data is not None:
            new_cam.data.lens = src_cam.data.lens

        st.active_instance_index = len(st.instances) - 1
        self.report({"INFO"}, f"Duplicated: {new_coll.name}")
        return {"FINISHED"}


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
