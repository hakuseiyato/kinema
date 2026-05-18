"""JSON Export / Import Operator。

ファイルブラウザでパスを選択し、`utils.json_io` でシリアライズ / デシリアライズ
する。シーン間で Instance 設定（カメラ参照は名前で）を持ち運ぶ用途。
"""

from __future__ import annotations

import json

import bpy
from bpy.props import BoolProperty, StringProperty
from bpy_extras.io_utils import ExportHelper, ImportHelper

from ..utils import json_io
from ._base import KinemaOperator


def _resolve_object(name: str):
    return bpy.data.objects.get(name) if name else None


def _resolve_collection(name: str):
    return bpy.data.collections.get(name) if name else None


class KINEMA_OT_export_json(KinemaOperator, ExportHelper):
    """Scene の kinema Instance 設定を JSON にエクスポート。"""
    bl_idname = "kinema.export_json"
    bl_label = "Export Kinema JSON"
    bl_description = "scene.kinema の Instance 一覧と設定を JSON ファイルに保存"

    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})

    def run(self, context):
        scene = context.scene
        st = scene.kinema
        try:
            from ..__init__ import bl_info as _bl  # noqa: PLC0415
            version = ".".join(str(x) for x in _bl.get("version", (2, 0, 0)))
        except Exception:
            version = "2.0.0"
        data = json_io.serialize_scene(st, kinema_version=version)
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            self.report({"ERROR"}, f"書込失敗: {exc}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Exported {len(data['instances'])} instances → {self.filepath}")
        return {"FINISHED"}


_IMPORT_MODE_ITEMS = (
    ("APPEND", "Append", "既存 Instance はそのまま、JSON 内容を末尾に追加"),
    ("MERGE", "Merge by name", "同名 Instance があれば上書き、無いものは追加"),
    ("REPLACE", "Replace all", "既存 Instance を全削除してから JSON 内容を取り込む"),
)


class KINEMA_OT_import_json(KinemaOperator, ImportHelper):
    """JSON から Scene の kinema Instance 設定をインポート。"""
    bl_idname = "kinema.import_json"
    bl_label = "Import Kinema JSON"
    bl_description = "JSON から Instance 一覧を取り込む（append / merge / replace 選択可）"

    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})

    mode: bpy.props.EnumProperty(
        name="Import Mode",
        items=_IMPORT_MODE_ITEMS,
        default="APPEND",
    )

    def draw(self, context):
        self.layout.prop(self, "mode")

    def run(self, context):
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            self.report({"ERROR"}, f"読込失敗: {exc}")
            return {"CANCELLED"}

        scene = context.scene
        st = scene.kinema

        if self.mode == "REPLACE":
            st.instances.clear()

        # MERGE: 名前一致したものに上書き
        merged = 0
        added = 0
        if self.mode == "MERGE":
            existing_by_name = {inst.name: i for i, inst in enumerate(st.instances)}
            for inst_data in data.get("instances", []):
                target_name = inst_data.get("name", "")
                if target_name in existing_by_name:
                    target_inst = st.instances[existing_by_name[target_name]]
                    json_io.deserialize_instance(
                        target_inst, inst_data,
                        resolve_object=_resolve_object,
                        resolve_collection=_resolve_collection,
                    )
                    merged += 1
                else:
                    new_inst = st.instances.add()
                    json_io.deserialize_instance(
                        new_inst, inst_data,
                        resolve_object=_resolve_object,
                        resolve_collection=_resolve_collection,
                    )
                    added += 1
            # schema_version はチェックしておく
            schema = data.get("kinema_schema", 0)
            if schema != json_io.SCHEMA_VERSION:
                self.report({"WARNING"}, f"schema 不一致: {schema}")
                return {"CANCELLED"}
            self.report(
                {"INFO"},
                f"Merged: {merged} updated, {added} added (schema v{schema})",
            )
            return {"FINISHED"}

        # APPEND / REPLACE は deserialize_scene に委譲
        result = json_io.deserialize_scene(
            st, data,
            resolve_object=_resolve_object,
            resolve_collection=_resolve_collection,
            add_instance=lambda: st.instances.add(),
        )
        if not result.get("ok"):
            self.report({"WARNING"}, result.get("reason", "Import failed"))
            return {"CANCELLED"}

        self.report(
            {"INFO"},
            f"Imported {result['added']} instances "
            f"(mode={self.mode}, schema v{result['schema']})",
        )
        return {"FINISHED"}
