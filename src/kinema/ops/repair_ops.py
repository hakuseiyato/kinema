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


def _scan_all_dead_constraints() -> list[tuple[bpy.types.Object, "bpy.types.Constraint", str]]:
    """**全種類の制約**で target が dead (ReferenceError) なものを列挙。

    kinema 起因とは限らないが、depsgraph crash の典型原因なので Repair 対象。
    """
    pairs: list = []
    for obj in bpy.data.objects:
        try:
            cons = list(obj.constraints)
        except Exception:
            continue
        for con in cons:
            # target を持つ制約だけ検査（Limit Rotation 等は target 無し）
            target = getattr(con, "target", None)
            try:
                # ReferenceError trigger or None check
                if target is not None:
                    _ = target.name  # 死活確認
            except ReferenceError:
                pairs.append((obj, con, f"{con.type}: dead target"))
                continue
            except Exception as exc:
                pairs.append((obj, con, f"{con.type}: {exc}"))
                continue
    return pairs


def _scan_dead_modifier_refs() -> list[tuple[bpy.types.Object, "bpy.types.Modifier", str]]:
    """Modifier の Object / Collection 参照で dead なものを列挙。"""
    pairs: list = []
    for obj in bpy.data.objects:
        try:
            mods = list(obj.modifiers)
        except Exception:
            continue
        for mod in mods:
            # Modifier の代表的な ref 属性
            for attr in ("object", "target", "mirror_object", "origin",
                         "deform_target", "object_from", "object_to",
                         "collection"):
                if not hasattr(mod, attr):
                    continue
                try:
                    ref = getattr(mod, attr)
                except Exception:
                    continue
                if ref is None:
                    continue
                try:
                    _ = ref.name
                except ReferenceError:
                    pairs.append((obj, mod, f"{mod.type}.{attr}: dead"))
                except Exception:
                    pass
    return pairs


def _check_drivers_on(id_block, label_prefix: str, found: list) -> None:
    """与えられた id_block の driver をスキャンして found に追記する。"""
    try:
        ad = id_block.animation_data
    except Exception:
        return
    if ad is None:
        return
    try:
        drivers = list(ad.drivers)
    except Exception:
        return
    for fc in drivers:
        try:
            drv = fc.driver
        except Exception:
            continue
        dead = False
        for var in drv.variables:
            for tgt in var.targets:
                try:
                    obj_ref = tgt.id
                except ReferenceError:
                    dead = True
                    break
                except Exception:
                    continue
                if obj_ref is None:
                    continue
                try:
                    _ = obj_ref.name
                except ReferenceError:
                    dead = True
                    break
                except Exception:
                    pass
            if dead:
                break
        if dead:
            found.append((label_prefix, fc.data_path, "dead driver var"))


def _scan_dead_drivers() -> list[tuple[str, str, str]]:
    """全 ID + その node_tree の driver で dead variable target を列挙。

    **重要**: scene.node_tree（Compositor）/ material.node_tree / world.node_tree
    の driver もスキャンする。Compositor の broken driver が render hang の
    典型原因だった事例（2026-05）への対策。

    Returns: [(label, datapath, reason), ...]
    """
    found: list = []
    # 1. 通常 ID の direct animation_data
    for collection_attr in ("objects", "scenes", "cameras", "materials",
                            "meshes", "worlds", "lights"):
        try:
            data_iter = getattr(bpy.data, collection_attr)
        except Exception:
            continue
        for id_block in data_iter:
            try:
                name = id_block.name
            except Exception:
                continue
            _check_drivers_on(id_block, f"{collection_attr}:{name}", found)

    # 2. node_tree を持つもの (Compositor / Material nodes / World nodes / Geometry Nodes)
    #    これが今回の Compositor broken driver を検出するキモ
    for collection_attr in ("scenes", "materials", "worlds", "lights",
                            "node_groups"):
        try:
            data_iter = getattr(bpy.data, collection_attr)
        except Exception:
            continue
        for id_block in data_iter:
            try:
                name = id_block.name
            except Exception:
                continue
            tree = getattr(id_block, "node_tree", None)
            if tree is None:
                continue
            _check_drivers_on(tree, f"{collection_attr}:{name}/node_tree", found)
    return found


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
    remove_all_dead_constraints: bpy.props.BoolProperty(
        name="Remove ALL Dead Constraints (any type)",
        description=(
            "kinema 起因以外も含めて、全種類の制約のうち target が dead な"
            "ものをスキャンして削除。depsgraph crash の典型原因対策"
        ),
        default=False,
    )
    remove_dead_modifier_refs: bpy.props.BoolProperty(
        name="Clear Dead Modifier References",
        description="Modifier の Object/Collection 参照のうち dead なものを None に",
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
            all_dead_cons = _scan_all_dead_constraints() if self.remove_all_dead_constraints else []
            dead_mods = _scan_dead_modifier_refs() if self.remove_dead_modifier_refs else []
            # Driver の dead は情報表示のみ（自動削除は副作用が大きすぎる）
            dead_drv = _scan_dead_drivers()

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

            # 拡張検査結果
            if self.remove_all_dead_constraints:
                box.label(
                    text=f"ALL Dead Constraints: {len(all_dead_cons)} 件",
                    icon="ERROR" if all_dead_cons else "CHECKMARK",
                )
                if all_dead_cons:
                    col = box.column(align=True)
                    col.scale_y = 0.85
                    for owner, con, reason in all_dead_cons[:8]:
                        col.label(text=f"  - {owner.name} / {reason}")
            if self.remove_dead_modifier_refs:
                box.label(
                    text=f"Dead Modifier Refs: {len(dead_mods)} 件",
                    icon="ERROR" if dead_mods else "CHECKMARK",
                )
                if dead_mods:
                    col = box.column(align=True)
                    col.scale_y = 0.85
                    for owner, mod, reason in dead_mods[:8]:
                        col.label(text=f"  - {owner.name} / {reason}")
            # Driver は情報表示のみ
            box.label(
                text=f"Dead Drivers (info only): {len(dead_drv)} 件",
                icon="INFO" if dead_drv else "CHECKMARK",
            )
            if dead_drv:
                col = box.column(align=True)
                col.scale_y = 0.85
                for id_name, dp, reason in dead_drv[:5]:
                    col.label(text=f"  - {id_name}.{dp}: {reason}")
                col.label(
                    text="※ Driver は自動削除しません。Outliner > Drivers Editor で手動削除推奨",
                    icon="INFO",
                )

            layout.separator()
            layout.label(text="削除対象:", icon="TRASH")
            layout.prop(self, "remove_orphan_proxies")
            layout.prop(self, "remove_dead_constraints")
            layout.prop(self, "remove_dead_instances")
            layout.separator()
            layout.label(text="拡張検査（kinema 起因以外も含む）:", icon="ZOOM_ALL")
            layout.prop(self, "remove_all_dead_constraints")
            layout.prop(self, "remove_dead_modifier_refs")
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

        # 4. ALL Dead Constraints
        if self.remove_all_dead_constraints:
            all_dead = _scan_all_dead_constraints()
            removed = 0
            for owner, con, _reason in all_dead:
                try:
                    owner.constraints.remove(con)
                    removed += 1
                except Exception as exc:
                    print(f"[kinema:repair] failed to remove constraint on {owner.name}: {exc}")
            report_lines.append(f"Removed {removed} all-type dead constraints")
            total_removed += removed

        # 5. Dead Modifier Refs（参照を None に）
        if self.remove_dead_modifier_refs:
            dead_mods = _scan_dead_modifier_refs()
            cleared = 0
            for owner, mod, reason in dead_mods:
                # reason は "Type.attr: dead" 形式。attr を抽出
                try:
                    attr_part = reason.split(".", 1)[1].split(":", 1)[0]
                    setattr(mod, attr_part, None)
                    cleared += 1
                except Exception as exc:
                    print(f"[kinema:repair] failed to clear modifier ref: {exc}")
            report_lines.append(f"Cleared {cleared} dead modifier refs")
            total_removed += cleared

        # 6. Purge Orphan Data（Blender 標準）
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
