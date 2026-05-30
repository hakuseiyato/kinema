"""Scene 健全化 Operator。

過去の kinema クラッシュで scene に残った orphan データを掃除する。
症状: 「Blender 標準レンダーでもクラッシュ」「.blend を開くと不安定」
原因の典型例:
  1. 親 Camera を失った LookAt Proxy Empty (`*_KnLookatProxy`)
  2. Object に紐付いた dead Constraint（target が削除済み）
  3. Instance の dead PointerProperty（camera_ref / collection_ref / follow_target /
     lookat_target が deleted ID を指している）
  4. Instance 用 Collection 内に dead member 参照
  5. Driver の dead ID 参照（kinema が driver を作っていない範囲では稀）

設計方針:
  - 削除前に dry-run でリスト表示
  - 何を消すか報告し、ユーザーの明示同意（dialog OK）で実行
"""

from __future__ import annotations

import bpy

from ..config import constants as C
from ..utils import refs
from ._base import KinemaOperator


# ---------------------------------------------------------------------------
# 検査ロジック
# ---------------------------------------------------------------------------

def _scan_orphan_proxies() -> list[bpy.types.Object]:
    """親 Camera を失った LookAt Proxy Empty を列挙。

    Proxy 名は `<camera_name>_KnLookatProxy` なので、対応 camera が
    `bpy.data.objects` に存在しなければ orphan とみなす。
    """
    suffix = C.KN_LOOKAT_PROXY_SUFFIX
    orphans: list = []
    for obj in bpy.data.objects:
        try:
            name = obj.name
        except Exception:
            continue
        if not name.endswith(suffix):
            continue
        cam_name = name[: -len(suffix)]
        if cam_name not in bpy.data.objects:
            orphans.append(obj)
            continue
        # 親と紐付くが Camera じゃないケース（型変化）
        cam = bpy.data.objects.get(cam_name)
        if cam is None or cam.type != "CAMERA":
            orphans.append(obj)
    return orphans


def _scan_dead_track_to_constraints() -> list[tuple[bpy.types.Object, "bpy.types.Constraint"]]:
    """Track-To 制約で target が dead なものを列挙。

    過去の自前 LookAt 撤去ロジックで Track-To 制約が残ってる可能性。
    """
    suffix = C.KN_LOOKAT_PROXY_SUFFIX
    pairs: list = []
    for obj in bpy.data.objects:
        try:
            cons = list(obj.constraints)
        except Exception:
            continue
        for con in cons:
            if con.type != "TRACK_TO":
                continue
            tgt = getattr(con, "target", None)
            try:
                if tgt is None:
                    # target が消えた = dead
                    if hasattr(con, "name") and (
                        suffix in con.name or "Kn" in con.name
                    ):
                        pairs.append((obj, con))
                    continue
                # target name に kinema 由来 suffix がついててかつ bpy.data.objects に居ない
                if tgt.name.endswith(suffix) and tgt.name not in bpy.data.objects:
                    pairs.append((obj, con))
            except ReferenceError:
                pairs.append((obj, con))
            except Exception:
                pass
    return pairs


def _scan_dead_instance_refs(scene) -> list[tuple[int, str, str]]:
    """Instance のうち camera_ref / collection_ref が両方とも dead な行を列挙。

    Returns: [(index, instance_name, reason), ...]
    """
    st = getattr(scene, "kinema", None)
    if st is None:
        return []
    broken: list = []
    for i, inst in enumerate(st.instances):
        coll = refs.safe_collection(inst.collection_ref)
        cam = refs.safe_object(inst.camera_ref)
        if coll is None and cam is None:
            broken.append((i, inst.name or "(unnamed)", "both refs dead"))
    return broken


# ---------------------------------------------------------------------------
# Operator
# ---------------------------------------------------------------------------

class KINEMA_OT_repair_scene(KinemaOperator):
    """Scene の orphan データを掃除する。

    Blender 標準レンダーがクラッシュする等、scene が壊れた状態の救出用。
    """
    bl_idname = "kinema.repair_scene"
    bl_label = "Repair Scene"
    bl_description = (
        "過去のクラッシュで scene に残った orphan データを検出して掃除する。"
        "Blender 標準レンダーが落ちる場合の救出に使う"
    )

    remove_orphan_proxies: bpy.props.BoolProperty(
        name="Remove Orphan LookAt Proxies",
        description="親 Camera を失った *_KnLookatProxy Empty を削除",
        default=True,
    )
    remove_dead_constraints: bpy.props.BoolProperty(
        name="Remove Dead Track-To Constraints",
        description="target が dead な Track-To 制約を削除",
        default=True,
    )
    remove_dead_instances: bpy.props.BoolProperty(
        name="Remove Dead Instance Entries",
        description="camera と collection が両方 dead な Instance 行を削除",
        default=False,
    )
    purge_orphan_data: bpy.props.BoolProperty(
        name="Purge Orphan Data",
        description="掃除後に Blender 標準の Purge Orphan Data を呼んで未使用 ID を片付け",
        default=True,
    )

    def invoke(self, context, event):  # noqa: ARG002
        return context.window_manager.invoke_props_dialog(self, width=560)

    def draw(self, context):
        layout = self.layout
        try:
            scene = context.scene
            layout.label(text="Repair Scene", icon="MODIFIER")
            layout.separator()

            # 検査結果を表示
            orphans = _scan_orphan_proxies() if self.remove_orphan_proxies else []
            dead_cons = _scan_dead_track_to_constraints() if self.remove_dead_constraints else []
            dead_inst = _scan_dead_instance_refs(scene) if self.remove_dead_instances else []

            box = layout.box()
            box.label(text="検出結果", icon="VIEWZOOM")
            box.label(
                text=f"Orphan LookAt Proxies: {len(orphans)} 件",
                icon="ERROR" if orphans else "CHECKMARK",
            )
            if orphans:
                col = box.column(align=True)
                col.scale_y = 0.85
                for o in orphans[:8]:
                    col.label(text=f"  - {o.name}")
                if len(orphans) > 8:
                    col.label(text=f"  ... and {len(orphans) - 8} more")

            box.label(
                text=f"Dead Track-To Constraints: {len(dead_cons)} 件",
                icon="ERROR" if dead_cons else "CHECKMARK",
            )
            if dead_cons:
                col = box.column(align=True)
                col.scale_y = 0.85
                for owner, con in dead_cons[:8]:
                    col.label(text=f"  - {owner.name} / {con.name}")
                if len(dead_cons) > 8:
                    col.label(text=f"  ... and {len(dead_cons) - 8} more")

            box.label(
                text=f"Dead Instance Entries: {len(dead_inst)} 件",
                icon="ERROR" if dead_inst else "CHECKMARK",
            )
            if dead_inst:
                col = box.column(align=True)
                col.scale_y = 0.85
                for i, name, reason in dead_inst[:8]:
                    col.label(text=f"  - #{i+1} {name} ({reason})")

            layout.separator()
            layout.label(text="削除対象:", icon="TRASH")
            layout.prop(self, "remove_orphan_proxies")
            layout.prop(self, "remove_dead_constraints")
            layout.prop(self, "remove_dead_instances")
            layout.separator()
            layout.prop(self, "purge_orphan_data")
            layout.separator()
            warn = layout.row()
            warn.alert = True
            warn.label(
                text="Undo で巻き戻せます。実行前に .blend を保存推奨",
                icon="INFO",
            )
        except Exception as exc:
            layout.label(text=f"描画エラー: {exc}", icon="ERROR")
            print(f"[kinema:repair] draw error: {exc}")

    def run(self, context):
        scene = context.scene
        report_lines: list[str] = []
        total_removed = 0

        # 1. Orphan LookAt Proxies
        if self.remove_orphan_proxies:
            orphans = _scan_orphan_proxies()
            removed = 0
            for proxy in orphans:
                try:
                    # まず collection からも unlink（do_unlink=True で十分だがダブル防御）
                    for coll in list(proxy.users_collection):
                        try:
                            coll.objects.unlink(proxy)
                        except Exception:
                            pass
                    bpy.data.objects.remove(proxy, do_unlink=True)
                    removed += 1
                except Exception as exc:
                    print(f"[kinema:repair] failed to remove {proxy.name}: {exc}")
            report_lines.append(f"Removed {removed} orphan proxies")
            total_removed += removed

        # 2. Dead Track-To Constraints
        if self.remove_dead_constraints:
            dead_cons = _scan_dead_track_to_constraints()
            removed = 0
            for owner, con in dead_cons:
                try:
                    owner.constraints.remove(con)
                    removed += 1
                except Exception as exc:
                    print(f"[kinema:repair] failed to remove constraint: {exc}")
            report_lines.append(f"Removed {removed} dead constraints")
            total_removed += removed

        # 3. Dead Instance Entries
        if self.remove_dead_instances:
            dead_inst = _scan_dead_instance_refs(scene)
            st = scene.kinema
            # 高い index から削除（index ずれ回避）
            for idx, _name, _reason in sorted(dead_inst, key=lambda x: -x[0]):
                try:
                    st.instances.remove(idx)
                    total_removed += 1
                except Exception as exc:
                    print(f"[kinema:repair] failed to remove instance #{idx}: {exc}")
            # active_instance_index をレンジ内に
            if st.active_instance_index >= len(st.instances):
                st.active_instance_index = max(0, len(st.instances) - 1)
            report_lines.append(f"Removed {len(dead_inst)} dead instance entries")

        # 4. Purge Orphan Data（Blender 標準）
        if self.purge_orphan_data:
            try:
                bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=True,
                                               do_recursive=True)
                report_lines.append("Purged orphan data (Blender standard)")
            except Exception as exc:
                print(f"[kinema:repair] orphan purge failed: {exc}")
                report_lines.append(f"Purge failed: {exc}")

        msg = " | ".join(report_lines) if report_lines else "Nothing to repair"
        self.report({"INFO"}, f"Repair: {msg}")
        print(f"[kinema:repair] {msg}")
        return {"FINISHED"}
