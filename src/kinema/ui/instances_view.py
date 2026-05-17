"""Instance UIList。

判別性のため:
  - コレクション名（Outliner の実体名）
  - カメラ名
  - 焦点距離
  - ソースプリセット名

を併記する。同じ collection_ref を 2 つ以上の Instance が指している場合は警告
アイコンを出す（Load 時のバグの早期検知）。
"""

from __future__ import annotations

import bpy

from ..utils import refs


class KINEMA_UL_instances(bpy.types.UIList):
    """Instance 一覧 UIList。"""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):  # noqa: ARG002
        cam = refs.safe_object(item.camera_ref)
        coll = refs.safe_collection(item.collection_ref)

        # 重複参照チェック（このリスト内で同じ collection_ref を持つ他 Instance がいるか）
        dup = False
        if coll is not None:
            for i, other in enumerate(data.instances):
                if i == index:
                    continue
                if refs.safe_collection(other.collection_ref) is coll:
                    dup = True
                    break

        row = layout.row(align=True)

        # index 番号（同名 Instance でも識別できるように）
        row.label(text=f"#{index + 1}")

        row.prop(
            item, "enabled",
            text="", icon="HIDE_OFF" if item.enabled else "HIDE_ON",
            emboss=False,
        )

        if coll is None and cam is None:
            row.label(text=f"{item.name} (Missing)", icon="ERROR")
            return

        # メイン: コレクション名（実体）
        main = coll.name if coll is not None else item.name
        row.label(text=main, icon="OUTLINER_COLLECTION")

        # ソースプリセット（複製元）
        if item.source_preset and item.source_preset != main:
            row.label(text=f"← {item.source_preset}")

        # 重複警告
        if dup:
            row.label(text="DUP", icon="ERROR")

        # カメラ + lens
        if cam is None:
            row.label(text="No camera", icon="ERROR")
        else:
            row.label(text=cam.name, icon="OUTLINER_OB_CAMERA")
            if cam.data is not None:
                row.label(text=f"{cam.data.lens:.0f}mm")

        # ショートカット: Preview
        op = row.operator("kinema.preview_instance", text="", icon="RESTRICT_VIEW_OFF")
        op.index = index
        # ショートカット: Duplicate
        op = row.operator("kinema.duplicate_instance", text="", icon="DUPLICATE")
        op.index = index
        # ショートカット: Unload
        op = row.operator("kinema.unload_instance", text="", icon="X")
        op.index = index
