"""専用 Workspace "Kinema" の作成と削除。

プラン v7 では当初 Image Editor を直接ホストにしていたが、Yato さんの希望で
「専用 Workspace を作って、その中身が Image Editor」という構成に変更。
普段の Layout / Modeling は触らない。
"""

from __future__ import annotations

import bpy

from ..config import constants as C
from ._base import KinemaOperator


class KINEMA_OT_create_workspace(KinemaOperator):
    """`Kinema` Workspace を新規作成（既に存在する場合はそれをアクティブに）。"""
    bl_idname = "kinema.create_workspace"
    bl_label = "Create Kinema Workspace"
    bl_description = "kinema 専用 Workspace タブを追加する"

    def run(self, context):
        name = C.KN_WORKSPACE_NAME
        ws = bpy.data.workspaces.get(name)
        if ws is None:
            # 現在の Workspace を複製して名前を変える。
            # bpy.ops.workspace.duplicate は CONTEXT を要するため、低レベルに API 経由
            # で複製してから rename する。
            try:
                bpy.ops.workspace.duplicate()
            except Exception as exc:
                self.report({"ERROR"}, f"Workspace duplicate failed: {exc}")
                return {"CANCELLED"}
            ws = context.window.workspace
            ws.name = name
            # 既存 Layout から複製しただけだと中身は同じなので、
            # Layout タブの後ろに位置する形になる。
            # ここでメインエリアの 1 つを IMAGE_EDITOR に切り替えるところは
            # v2.0 beta1 の Timeline 実装時に行う（spike0 を踏襲）。
            self.report({"INFO"}, f"Workspace '{name}' を作成しました")
        else:
            context.window.workspace = ws
            self.report({"INFO"}, f"Workspace '{name}' をアクティブにしました")
        return {"FINISHED"}


class KINEMA_OT_remove_workspace(KinemaOperator):
    """`Kinema` Workspace を削除する。"""
    bl_idname = "kinema.remove_workspace"
    bl_label = "Remove Kinema Workspace"
    bl_description = "kinema 専用 Workspace タブを削除する"

    def run(self, context):
        name = C.KN_WORKSPACE_NAME
        ws = bpy.data.workspaces.get(name)
        if ws is None:
            self.report({"INFO"}, "Kinema Workspace は存在しません")
            return {"CANCELLED"}

        # Kinema Workspace をアクティブにしないと workspace.delete が効かない場合がある
        if context.window.workspace is not ws:
            context.window.workspace = ws

        # Blender 5.x では bpy.data.workspaces.remove() が存在しない。
        # bpy.ops.workspace.delete を使う必要がある（INVOKE 経由のほうが
        # アクティブ Workspace を正しく見てくれる）。
        try:
            bpy.ops.workspace.delete()
        except Exception:
            # フォールバック: ID datablock 削除を試みる
            try:
                bpy.data.batch_remove(ids=[ws])
            except Exception as exc:
                self.report({"ERROR"}, f"Workspace 削除失敗: {exc}")
                return {"CANCELLED"}
        return {"FINISHED"}
