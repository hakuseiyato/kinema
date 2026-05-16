"""Preset 系 Operator。"""

from __future__ import annotations

import bpy

from ..utils import collections as kn_collections
from ._base import KinemaOperator


class KINEMA_OT_scan_presets(KinemaOperator):
    """Preset Root をスキャンして scene.kinema.presets を再構築する。"""
    bl_idname = "kinema.scan_presets"
    bl_label = "Scan Presets"
    bl_description = "Preset Root のコレクションを走査して一覧を更新"

    def run(self, context):
        st = context.scene.kinema
        flat = kn_collections.scan_presets_grouped(context.scene, st.preset_root_name)
        st.presets.clear()
        for entry in flat:
            item = st.presets.add()
            item.name = entry["name"]
            item.is_header = entry["is_header"]
            item.group = entry["group"]
            item.short_name = entry["short_name"]
            item.display_name = entry["display_name"]
            item.camera_name = entry["camera_name"]
            meta = entry["meta"]
            item.tags = meta["tags"]
            item.has_anim = meta["has_anim"]
            item.default_lens = meta["default_lens"]
            item.preview_end = meta["preview_end"]
            item.follow_target = meta["follow_target"]
            item.lookat_target = meta["lookat_target"]
        if st.presets:
            st.active_preset_index = min(st.active_preset_index, len(st.presets) - 1)
        else:
            st.active_preset_index = 0
        self.report({"INFO"}, f"Scan: {len([e for e in flat if not e['is_header']])} presets")
        return {"FINISHED"}


class KINEMA_OT_load_preset(KinemaOperator):
    """選択中のプリセットを Instances Root に複製してロードする。"""
    bl_idname = "kinema.load_preset"
    bl_label = "Load Selected Preset"
    bl_description = "選択中のプリセットコレクションを複製して Instance として追加"

    def run(self, context):
        scene = context.scene
        st = scene.kinema
        if not st.presets:
            self.report({"WARNING"}, "プリセット一覧が空です。先に Scan Presets を実行してください")
            return {"CANCELLED"}
        if st.active_preset_index < 0 or st.active_preset_index >= len(st.presets):
            self.report({"WARNING"}, "プリセットが選択されていません")
            return {"CANCELLED"}
        sel = st.presets[st.active_preset_index]
        if sel.is_header:
            self.report({"WARNING"}, "グループヘッダは Load できません")
            return {"CANCELLED"}

        source = bpy.data.collections.get(sel.name)
        if source is None:
            self.report({"ERROR"}, f"プリセットコレクションが見つかりません: {sel.name}")
            return {"CANCELLED"}

        instances_root = kn_collections.get_or_create_instances_root(
            scene, st.instances_root_name,
        )
        new_coll, cam = kn_collections.duplicate_collection(
            source, instances_root, base_name=sel.name,
        )

        inst = st.instances.add()
        inst.name = new_coll.name
        inst.source_preset = sel.name
        inst.collection_ref = new_coll
        inst.camera_ref = cam
        if cam is not None and cam.data is not None:
            inst.lens_mm = float(cam.data.lens)

        st.active_instance_index = len(st.instances) - 1
        self.report({"INFO"}, f"Loaded: {new_coll.name}")
        return {"FINISHED"}
