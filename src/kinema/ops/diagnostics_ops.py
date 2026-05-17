"""Self-diagnostic Operator。

UI から押せる「健全性チェック」。何が何個ぶら下がっているかを可視化する。
"""

from __future__ import annotations

import bpy

from ..utils import refs
from ._base import KinemaOperator


class KINEMA_OT_run_diagnostics(KinemaOperator):
    """frame_change_pre / depsgraph_update_post / load_post に kinema 関数が
    何個登録されているか、Instance 配列に重複参照があるか等を Info Area に出力する。
    """
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
                if getattr(fn, "__name__", "").startswith("kinema_")
            )
            cineflow_count = sum(
                1 for fn in hook_list
                if getattr(fn, "__name__", "").startswith("_on_")
                and getattr(fn, "__module__", "").startswith("cineflow")
            )
            tag = "OK" if kinema_count <= 1 else "DUPLICATE"
            line = f"[{tag}] {hook_name}: kinema={kinema_count}, cineflow={cineflow_count}"
            lines.append(line)

        # --- Instance 重複 collection_ref チェック ---
        st = context.scene.kinema
        seen_colls: dict[str, int] = {}
        for inst in st.instances:
            coll = refs.safe_collection(inst.collection_ref)
            if coll is None:
                continue
            seen_colls[coll.name] = seen_colls.get(coll.name, 0) + 1
        dup_colls = [(n, c) for n, c in seen_colls.items() if c > 1]
        if dup_colls:
            lines.append(f"[NG] Instance 重複参照: {dup_colls}")
        else:
            lines.append(f"[OK] Instance 重複参照: なし（合計 {len(st.instances)}）")

        # --- 参照切れチェック ---
        broken = 0
        for inst in st.instances:
            if refs.safe_collection(inst.collection_ref) is None:
                broken += 1
        if broken:
            lines.append(f"[NG] 参照切れ Instance: {broken} 件 → Refresh Instances 推奨")
        else:
            lines.append(f"[OK] 参照切れ Instance: なし")

        # --- Workspace 確認 ---
        from ..config import constants as C
        ws = bpy.data.workspaces.get(C.KN_WORKSPACE_NAME)
        lines.append(f"[{'OK' if ws else '--'}] Workspace '{C.KN_WORKSPACE_NAME}': "
                     f"{'作成済み' if ws else '未作成'}")

        for line in lines:
            print(f"[kinema:diagnostics] {line}")
            self.report({"INFO"}, line)
        return {"FINISHED"}
