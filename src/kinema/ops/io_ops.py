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


class KINEMA_OT_import_json(KinemaOperator, ImportHelper):
    """JSON から Scene の kinema Instance 設定をインポート。"""
    bl_idname = "kinema.import_json"
    bl_label = "Import Kinema JSON"
    bl_description = "JSON から Instance 一覧を取り込む（既存に追加 / 全置換 選択可）"

    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})

    clear_existing: BoolProperty(
        name="Clear existing instances before import",
        description="ON: 既存の Instance を全削除してから取り込み（クリーンインポート）",
        default=False,
    )

    def draw(self, context):
        self.layout.prop(self, "clear_existing")

    def run(self, context):
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            self.report({"ERROR"}, f"読込失敗: {exc}")
            return {"CANCELLED"}

        scene = context.scene
        st = scene.kinema

        if self.clear_existing:
            st.instances.clear()

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
            f"Imported {result['added']} instances (schema v{result['schema']})",
        )
        return {"FINISHED"}
