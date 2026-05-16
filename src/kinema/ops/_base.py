"""Operator 基底クラス。

UNDO flag を必ず付け、execute 後に `context.area.tag_redraw()` を呼ぶ規約を
基底で強制する。
"""

from __future__ import annotations

import bpy


class KinemaOperator(bpy.types.Operator):
    """非 Modal Operator 用。Blender 標準アンドゥに自動で乗る。"""
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):  # type: ignore[override]
        result = self.run(context)
        self._redraw(context)
        return result

    # サブクラスがこちらを実装する
    def run(self, context):  # noqa: ARG002
        raise NotImplementedError

    def _redraw(self, context) -> None:
        area = getattr(context, "area", None)
        if area is not None:
            area.tag_redraw()
