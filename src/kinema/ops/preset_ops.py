"""Preset 系 Operator。"""

from __future__ import annotations

import bpy

from ..utils import collections as kn_collections
from ..utils import refs
from ._base import KinemaOperator


class KINEMA_OT_scan_presets(KinemaOperator):
    """Preset Root をスキャンして scene.kinema.presets を再構築する。"""
    bl_idname = "kinema.scan_presets"
    bl_label = "Scan Presets"
    bl_description = "Preset Root のコレクションを走査して一覧を更新"

    def run(self, context):
        st = context.scene.kinema
        # 折り畳み状態を保持しておく（再スキャン後も維持するため）
        collapsed_groups = {
            item.group for item in st.presets if item.is_header and item.header_collapsed
        }

        flat = kn_collections.scan_presets_with_headers(context.scene, st.preset_root_name)
        st.presets.clear()
        camera_count = 0
        for entry in flat:
            item = st.presets.add()
            item.name = entry["name"]
            item.is_header = entry["is_header"]
            item.header_collapsed = (
                entry.get("header_collapsed", False)
                or (entry["is_header"] and entry["group"] in collapsed_groups)
            )
            item.child_count = entry.get("child_count", 0)
            item.group = entry["group"]
            item.short_name = entry["short_name"]
            item.display_name = entry.get("display_name") or entry["short_name"]
            item.camera_name = entry["camera_name"]
            meta = entry["meta"]
            item.tags = meta["tags"]
            item.has_anim = meta["has_anim"]
            item.default_lens = meta["default_lens"]
            item.preview_end = meta["preview_end"]
            item.follow_target = meta["follow_target"]
            item.lookat_target = meta["lookat_target"]
            if not entry["is_header"]:
                camera_count += 1

        if st.presets:
            st.active_preset_index = min(st.active_preset_index, len(st.presets) - 1)
        else:
            st.active_preset_index = 0
        self.report({"INFO"}, f"Scan: {camera_count} cameras")
        return {"FINISHED"}


class KINEMA_OT_toggle_preset_group_collapse(KinemaOperator):
    """Preset 一覧のグループヘッダ行の折り畳み状態をトグル。"""
    bl_idname = "kinema.toggle_preset_group_collapse"
    bl_label = "Toggle Group Collapse"
    bl_description = "Preset グループの折り畳み状態を切り替える"

    index: bpy.props.IntProperty(default=-1)

    def run(self, context):
        st = context.scene.kinema
        if self.index < 0 or self.index >= len(st.presets):
            return {"CANCELLED"}
        item = st.presets[self.index]
        if not item.is_header:
            return {"CANCELLED"}
        item.header_collapsed = not item.header_collapsed
        return {"FINISHED"}


class KINEMA_OT_load_preset(KinemaOperator):
    """選択中のプリセット（Camera オブジェクト）を Instances Root に複製。"""
    bl_idname = "kinema.load_preset"
    bl_label = "Load Selected Preset"
    bl_description = "選択中の Camera プリセットを関連オブジェクトごと複製して Instance に追加"

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

        # 新仕様: sel.name は Camera オブジェクト名
        src_cam = bpy.data.objects.get(sel.name)
        if src_cam is None or src_cam.type != "CAMERA":
            self.report({"ERROR"}, f"Camera オブジェクトが見つかりません: {sel.name}")
            return {"CANCELLED"}

        preset_root = kn_collections.get_preset_root(scene, st.preset_root_name)
        instances_root = kn_collections.get_or_create_instances_root(
            scene, st.instances_root_name,
        )
        try:
            new_coll, new_cam = kn_collections.duplicate_camera_as_instance(
                src_cam, instances_root,
                root_scope=preset_root,
                base_name=src_cam.name,
            )
        except Exception as exc:
            self.report({"ERROR"}, f"複製失敗: {exc}")
            return {"CANCELLED"}

        # 安全チェック: 万一既存 Instance と同じ collection を指していたら警告
        for existing in st.instances:
            if refs.safe_collection(existing.collection_ref) is new_coll:
                self.report(
                    {"WARNING"},
                    f"既存 Instance が同じ collection を参照 ({new_coll.name})",
                )
                break

        inst = st.instances.add()
        inst.name = new_coll.name
        inst.source_preset = sel.name
        inst.collection_ref = new_coll
        inst.camera_ref = new_cam
        # Preset のカスタムプロパティ kn_default_lens があれば優先して適用
        if new_cam is not None and new_cam.data is not None:
            if sel.default_lens and sel.default_lens > 0.001:
                new_cam.data.lens = float(sel.default_lens)
            inst.lens_mm = float(new_cam.data.lens)

        st.active_instance_index = len(st.instances) - 1
        self.report({"INFO"}, f"Loaded: {new_coll.name} ({new_cam.name})")
        return {"FINISHED"}
