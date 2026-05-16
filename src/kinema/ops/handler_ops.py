"""cineflow 衝突回避 / handler 手動 enable 用 Operator。"""

from __future__ import annotations

import bpy

from ..runtime import handlers
from ._base import KinemaOperator


class KINEMA_OT_disable_cineflow_and_enable_handlers(KinemaOperator):
    """cineflow を無効化してから kinema handler を有効化する。"""
    bl_idname = "kinema.disable_cineflow_and_enable_handlers"
    bl_label = "Disable cineflow & enable kinema handlers"
    bl_description = "cineflow アドオンを無効化してから kinema の frame_change handler を有効化"

    def run(self, context):  # noqa: ARG002
        addons = bpy.context.preferences.addons
        cineflow_keys = [k for k in ("cineflow", "bl_ext.user_default.cineflow") if k in addons.keys()]
        for key in cineflow_keys:
            try:
                bpy.ops.preferences.addon_disable(module=key)
            except Exception as exc:
                self.report({"WARNING"}, f"cineflow 無効化失敗 ({key}): {exc}")
        if handlers.register_all():
            self.report({"INFO"}, "kinema handlers を有効化しました")
        else:
            self.report({"WARNING"}, "まだ cineflow が enabled です。Preferences で無効化してください")
        return {"FINISHED"}


class KINEMA_OT_toggle_handlers(KinemaOperator):
    """kinema handler の有効/無効をトグル。"""
    bl_idname = "kinema.toggle_handlers"
    bl_label = "Toggle Kinema Handlers"
    bl_description = "kinema の frame_change handler を有効/無効にする"

    def run(self, context):  # noqa: ARG002
        # Blender の handler list に kinema_frame_change_pre が居るかで判定
        present = any(
            getattr(fn, "__name__", "") == "kinema_frame_change_pre"
            for fn in bpy.app.handlers.frame_change_pre
        )
        if present:
            handlers.unregister_all()
            self.report({"INFO"}, "kinema handlers を無効化しました")
        else:
            if handlers.register_all():
                self.report({"INFO"}, "kinema handlers を有効化しました")
            else:
                self.report({"WARNING"}, "cineflow が enabled なので登録できません")
        return {"FINISHED"}
