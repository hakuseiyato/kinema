"""Self-diagnostic Operator。

UI から押せる「健全性チェック」。kinema が依存する handler / PropertyGroup の
登録状況・参照切れ・cineflow 共存・Workspace 状態を Info Area に出力する。
"""

from __future__ import annotations

import bpy

from ..config import constants as C
from ..utils import refs
from ._base import KinemaOperator


_KINEMA_HANDLER_NAMES = (
    "kinema_frame_change_pre",
    "kinema_depsgraph_update_post",
    "kinema_load_post",
)


class KINEMA_OT_run_diagnostics(KinemaOperator):
    """kinema の登録状況・重複・参照切れを点検し Info に出力する。"""
    bl_idname = "kinema.run_diagnostics"
    bl_label = "Run Diagnostics"
    bl_description = "kinema の登録状況・重複・参照切れを点検し Info に出力"

    def run(self, context):
        lines: list[str] = []

        # --- handler 数チェック ---
        for hook_name in ("frame_change_pre", "depsgraph_update_post", "load_post"):
            hook_list = getattr(bpy.app.handlers, hook_name)
            kinema_count = sum(
                1 for fn in hook_list
                if getattr(fn, "__name__", "") in _KINEMA_HANDLER_NAMES
            )
            cineflow_count = sum(
                1 for fn in hook_list
                if getattr(fn, "__module__", "").endswith("cineflow.runtime")
                or getattr(fn, "__module__", "").endswith("cineflow")
            )
            tag = "OK" if kinema_count <= 1 else "DUPLICATE"
            lines.append(
                f"[{tag}] {hook_name}: kinema={kinema_count}, cineflow={cineflow_count}"
            )

        # --- cineflow アドオン状態 ---
        addons = bpy.context.preferences.addons
        cineflow_enabled = (
            "cineflow" in addons.keys() or "bl_ext.user_default.cineflow" in addons.keys()
        )
        lines.append(
            f"[{'WARN' if cineflow_enabled else 'OK'}] cineflow: "
            f"{'enabled (要無効化)' if cineflow_enabled else 'disabled'}"
        )

        # --- Instance 重複 collection_ref チェック ---
        st = context.scene.kinema
        seen_colls: dict[str, int] = {}
        broken = 0
        for inst in st.instances:
            coll = refs.safe_collection(inst.collection_ref)
            if coll is None:
                broken += 1
                continue
            seen_colls[coll.name] = seen_colls.get(coll.name, 0) + 1
        dup_colls = [(n, c) for n, c in seen_colls.items() if c > 1]
        if dup_colls:
            lines.append(f"[NG] Instance 重複参照: {dup_colls}")
        else:
            lines.append(f"[OK] Instance 重複参照: なし（合計 {len(st.instances)}）")
        if broken:
            lines.append(f"[NG] 参照切れ Instance: {broken} 件 → Refresh Instances 推奨")
        else:
            lines.append("[OK] 参照切れ Instance: なし")

        # --- Preset Root / Instances Root の存在 ---
        for root_name in (st.preset_root_name, st.instances_root_name):
            coll = bpy.data.collections.get(root_name)
            in_scene = coll is not None and any(
                c == coll for c in context.scene.collection.children
            )
            tag = "OK" if in_scene else "--"
            lines.append(f"[{tag}] Collection '{root_name}': "
                         f"{'存在' if in_scene else '未作成'}")

        # --- Workspace 確認 ---
        ws = bpy.data.workspaces.get(C.KN_WORKSPACE_NAME)
        lines.append(
            f"[{'OK' if ws else '--'}] Workspace '{C.KN_WORKSPACE_NAME}': "
            f"{'作成済み' if ws else '未作成'}"
        )

        # --- Keying Set 確認 ---
        from ..ops.keyframe_ops import KEYING_SET_LABEL  # noqa: PLC0415
        ks = context.scene.keying_sets.get(KEYING_SET_LABEL)
        if ks is None:
            lines.append(f"[--] Keying Set '{KEYING_SET_LABEL}': 未生成")
        else:
            lines.append(
                f"[OK] Keying Set '{KEYING_SET_LABEL}': {len(ks.paths)} paths"
            )

        for line in lines:
            print(f"[kinema:diagnostics] {line}")
            self.report({"INFO"}, line)
        return {"FINISHED"}
