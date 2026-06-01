"""Shot 系 Operator。

Phase 1 提供分:
  - KINEMA_OT_migrate_to_shots: 旧 cuts[] + yato_vis.groups[].cast_markers から
    新 shots[] へワンクリック移行（旧データは保持、Phase 2 で削除予定）
  - KINEMA_OT_sync_shots_from_markers: Marker 走査して shots[] を整合
  - KINEMA_OT_jump_to_shot: Shot 選択時の frame jump + camera 切替（ボタン版）
  - KINEMA_OT_add_shot / remove_shot / move_shot
  - KINEMA_OT_rename_shot: cascade rename（Marker / Instance / Cast 参照名すべて）
  - KINEMA_OT_diagnose_shots: System Console に詳細ダンプ
"""

from __future__ import annotations

import bpy
from bpy.props import BoolProperty, IntProperty, StringProperty

from ..utils import refs
from ..utils import visibility_kit_bridge as _vkb
from ._base import KinemaOperator


# ---------------------------------------------------------------------------
# 内部ヘルパ
# ---------------------------------------------------------------------------

def _sorted_markers(scene):
    """Timeline Marker を frame 昇順で返す（同 frame は name 順）。"""
    return sorted(
        list(scene.timeline_markers),
        key=lambda m: (m.frame, m.name),
    )


def _resolve_shot_frame_range(scene, shot, sorted_markers) -> tuple[int, int]:
    """Shot の実効フレーム範囲を返す。"""
    if shot.frame_override:
        return int(shot.frame_start_override), int(shot.frame_end_override)
    m = scene.timeline_markers.get(shot.marker_name)
    if m is None:
        return int(scene.frame_start), int(scene.frame_end)
    fs = m.frame
    fe = scene.frame_end
    for nm in sorted_markers:
        if nm.frame > m.frame:
            fe = nm.frame - 1
            break
    return int(fs), int(fe)


def _find_instance_name_by_camera(st, camera_obj) -> str:
    """Instance リストから camera_ref が一致するものの name を返す。

    マッチング順: identity → name 比較（ラッパー差に強い）。
    """
    if camera_obj is None:
        return ""
    try:
        target_name = camera_obj.name
    except Exception:
        return ""
    for inst in st.instances:
        cam = refs.safe_object(inst.camera_ref)
        if cam is None:
            continue
        if cam is camera_obj:
            return inst.name
        try:
            if cam.name == target_name:
                return inst.name
        except Exception:
            continue
    return ""


def _find_instance_by_name(st, name: str) -> str:
    """同名 Instance を返す（最終 fallback）。"""
    if not name:
        return ""
    for inst in st.instances:
        try:
            if inst.name == name:
                return inst.name
        except Exception:
            continue
    return ""


# ---------------------------------------------------------------------------
# Migrate Operator（Phase 1 の中核）
# ---------------------------------------------------------------------------

class KINEMA_OT_migrate_to_shots(KinemaOperator):
    """旧 cuts[] と yato_vis.groups[].cast_markers から shots[] へ移行する。

    Phase 1 の中核 Operator。設定を 1 つも失わずに移行する：

      - kinema.cuts[]:
          name / marker_name / instance_name / enabled / frame_override /
          frame_start_override / frame_end_override / notes / orphan
        → shots[] の同名フィールドへコピー
      - yato_vis.groups[].cast_markers:
          各 Group が cast_markers にマーカー名を持つ → そのマーカーに対応する
          shot の cast に { group_name, solo_target_name } エントリ追加
      - Marker は存在するが Cut が無い → 新規 shot を作成
      - Cut は存在するが Marker が無い → orphan=True で shot 作成

    旧データは Phase 1 では削除しない。Phase 2 で読出を切替えた後、
    `KINEMA_OT_cleanup_legacy_data` で削除する流れにする。
    """
    bl_idname = "kinema.migrate_to_shots"
    bl_label = "Migrate to Shots"
    bl_description = (
        "kinema.cuts[] と yato_vis.groups[].cast_markers から "
        "新 scene.kinema.shots[] へ移行（旧データは保持、Phase 2 で削除）"
    )

    clear_existing_shots: BoolProperty(
        name="Clear Existing Shots First",
        description="既に shots[] にデータがあれば全クリアしてから移行",
        default=True,
    )
    inherit_cast: BoolProperty(
        name="Import Cast from visibility_kit",
        description="yato_vis.groups[].cast_markers を読み込んで shot.cast へ反映",
        default=True,
    )

    def invoke(self, context, event):  # noqa: ARG002
        return context.window_manager.invoke_props_dialog(self, width=520)

    def draw(self, context):
        layout = self.layout
        try:
            scene = context.scene
            st = scene.kinema
            n_cuts = len(st.cuts) if hasattr(st, "cuts") else 0
            n_markers = len([m for m in scene.timeline_markers])
            n_groups = len(_vkb.list_groups(scene))
            n_shots = len(st.shots)
            layout.label(text="Migrate to Shots", icon="MOD_TIME")
            layout.separator()
            box = layout.box()
            box.label(text="検査結果", icon="VIEWZOOM")
            box.label(text=f"  既存 Cut: {n_cuts} 件")
            box.label(text=f"  Timeline Marker: {n_markers} 件")
            box.label(text=f"  yato_vis Group: {n_groups} 件")
            box.label(text=f"  既存 shots[]: {n_shots} 件")
            if not _vkb.is_available(scene):
                warn = layout.row()
                warn.alert = True
                warn.label(
                    text="yato_visibility_kit が未登録です。Cast はインポートしません",
                    icon="ERROR",
                )
            layout.separator()
            layout.prop(self, "clear_existing_shots")
            if _vkb.is_available(scene):
                layout.prop(self, "inherit_cast")
            layout.separator()
            info = layout.row()
            info.label(
                text="旧 cuts[] / cast_markers は保持されます（Phase 2 で削除）",
                icon="INFO",
            )
        except Exception as exc:
            layout.label(text=f"描画エラー: {exc}", icon="ERROR")

    def run(self, context):
        scene = context.scene
        st = scene.kinema

        if self.clear_existing_shots:
            st.shots.clear()

        # 1. 既存 Cut を marker_name で索引化
        cut_by_marker: dict = {}
        cut_by_name: dict = {}
        if hasattr(st, "cuts"):
            for c in st.cuts:
                try:
                    if c.marker_name:
                        cut_by_marker[c.marker_name] = c
                    if c.name:
                        cut_by_name.setdefault(c.name, c)
                except Exception:
                    continue

        # 2. yato_vis.groups[] を marker → group リストに索引化（高速化）
        cast_by_marker: dict[str, list[dict]] = {}
        if self.inherit_cast and _vkb.is_available(scene):
            for g in _vkb.list_groups(scene):
                try:
                    gname = g.name
                except Exception:
                    continue
                solo_name = _vkb.resolve_solo_target(g) or ""
                try:
                    for cm in g.cast_markers:
                        cast_by_marker.setdefault(cm.marker_name, []).append({
                            "group_name": gname,
                            "solo_target_name": solo_name,
                        })
                except Exception:
                    continue

        sorted_ms = _sorted_markers(scene)
        added_from_marker = 0
        added_orphan = 0
        cast_entries_total = 0
        instance_resolved = 0

        # 3. Marker 1 つ = Shot 1 つ
        seen_markers = set()
        for m in sorted_ms:
            seen_markers.add(m.name)
            shot = st.shots.add()
            shot.marker_name = m.name
            # 既存 Cut から設定をコピー
            cut = cut_by_marker.get(m.name) or cut_by_name.get(m.name)
            if cut is not None:
                shot.name = cut.name or m.name
                shot.instance_name = getattr(cut, "instance_name", "") or ""
                shot.enabled = bool(getattr(cut, "enabled", True))
                shot.frame_override = bool(getattr(cut, "frame_override", False))
                shot.frame_start_override = int(getattr(cut, "frame_start_override", 1))
                shot.frame_end_override = int(getattr(cut, "frame_end_override", 250))
                shot.notes = getattr(cut, "notes", "") or ""
            else:
                shot.name = m.name
                shot.enabled = True

            # Instance 未解決ならカメラから推定
            if not shot.instance_name:
                try:
                    cam_obj = getattr(m, "camera", None)
                except Exception:
                    cam_obj = None
                if cam_obj is not None:
                    resolved = _find_instance_name_by_camera(st, cam_obj)
                    if not resolved:
                        resolved = _find_instance_by_name(st, m.name)
                    if resolved:
                        shot.instance_name = resolved
                        instance_resolved += 1

            # Cast 移行
            for entry in cast_by_marker.get(m.name, []):
                ce = shot.cast.add()
                ce.group_name = entry["group_name"]
                ce.enabled = True
                ce.solo_target_name = entry["solo_target_name"]
                cast_entries_total += 1
            shot.orphan = False
            added_from_marker += 1

        # 4. Marker が消えた orphan Cut も保持
        if hasattr(st, "cuts"):
            for c in st.cuts:
                try:
                    mn = c.marker_name or c.name
                    if mn in seen_markers:
                        continue
                except Exception:
                    continue
                shot = st.shots.add()
                shot.name = c.name or "(orphan)"
                shot.marker_name = c.marker_name
                shot.instance_name = getattr(c, "instance_name", "") or ""
                shot.enabled = bool(getattr(c, "enabled", True))
                shot.frame_override = bool(getattr(c, "frame_override", False))
                shot.frame_start_override = int(getattr(c, "frame_start_override", 1))
                shot.frame_end_override = int(getattr(c, "frame_end_override", 250))
                shot.notes = getattr(c, "notes", "") or ""
                shot.orphan = True
                added_orphan += 1

        # 5. データフォーマットバージョンを 2 に昇格
        try:
            st.data_format_version = 2
        except Exception:
            pass

        st.active_shot_index = 0

        msg = (
            f"Migrate: +{added_from_marker} shots from markers, "
            f"+{added_orphan} orphan, "
            f"+{cast_entries_total} cast entries, "
            f"+{instance_resolved} instances auto-resolved"
        )
        self.report({"INFO"}, msg)
        print(f"[kinema:migrate] {msg}")
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Shot Sync / CRUD / Jump
# ---------------------------------------------------------------------------

class KINEMA_OT_sync_shots_from_markers(KinemaOperator):
    """Marker を走査して shots[] を整合する（Migrate 後の継続運用）。

    挙動:
      - 新規 Marker → 新規 Shot 追加
      - Marker が消えた Shot → orphan=True
      - 既存設定（name / instance / cast / enabled / notes 等）は保持
    """
    bl_idname = "kinema.sync_shots_from_markers"
    bl_label = "Sync Shots from Markers"
    bl_description = (
        "Timeline Marker と shots[] を同期。新規 Marker は新規 Shot として追加、"
        "Marker が消えた Shot は orphan としてマーク（削除はユーザー判断）"
    )

    force_rebind_instance: BoolProperty(
        name="Force Rebind Instance",
        description="既存 instance_name も Marker.camera から再解決",
        default=False,
    )
    inherit_cast_from_visibility_kit: BoolProperty(
        name="Re-import Cast from visibility_kit",
        description="yato_vis.groups[].cast_markers から cast を再 import（既存は置換）",
        default=False,
    )

    def invoke(self, context, event):  # noqa: ARG002
        return context.window_manager.invoke_props_dialog(self, width=460)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "force_rebind_instance")
        if _vkb.is_available(context.scene):
            layout.prop(self, "inherit_cast_from_visibility_kit")

    def run(self, context):
        scene = context.scene
        st = scene.kinema
        sorted_ms = _sorted_markers(scene)

        shot_by_marker = {s.marker_name: s for s in st.shots if s.marker_name}
        added = 0
        bound = 0
        rebound = 0
        no_marker_cam = 0
        unresolved = 0
        cast_imported = 0

        # 全 Shot を一旦 orphan 候補に
        for s in st.shots:
            s.orphan = True

        # cast 再 import 準備
        cast_by_marker: dict[str, list[dict]] = {}
        if self.inherit_cast_from_visibility_kit and _vkb.is_available(scene):
            for g in _vkb.list_groups(scene):
                try:
                    gname = g.name
                except Exception:
                    continue
                solo_name = _vkb.resolve_solo_target(g) or ""
                try:
                    for cm in g.cast_markers:
                        cast_by_marker.setdefault(cm.marker_name, []).append({
                            "group_name": gname,
                            "solo_target_name": solo_name,
                        })
                except Exception:
                    continue

        for m in sorted_ms:
            shot = shot_by_marker.get(m.name)
            if shot is None:
                shot = st.shots.add()
                shot.name = m.name
                shot.marker_name = m.name
                added += 1
            shot.orphan = False

            # Instance 解決
            need_bind = self.force_rebind_instance or not shot.instance_name
            if need_bind:
                try:
                    cam_obj = getattr(m, "camera", None)
                except Exception:
                    cam_obj = None
                resolved = ""
                if cam_obj is not None:
                    resolved = _find_instance_name_by_camera(st, cam_obj)
                    if not resolved:
                        unresolved += 1
                else:
                    no_marker_cam += 1
                if not resolved:
                    resolved = _find_instance_by_name(st, m.name)
                if resolved:
                    was = shot.instance_name
                    shot.instance_name = resolved
                    if was and was != resolved:
                        rebound += 1
                    else:
                        bound += 1

            # Cast 再 import（オプション）
            if self.inherit_cast_from_visibility_kit:
                shot.cast.clear()
                for entry in cast_by_marker.get(m.name, []):
                    ce = shot.cast.add()
                    ce.group_name = entry["group_name"]
                    ce.enabled = True
                    ce.solo_target_name = entry["solo_target_name"]
                    cast_imported += 1

        if st.active_shot_index >= len(st.shots):
            st.active_shot_index = max(0, len(st.shots) - 1)

        parts = []
        if added:
            parts.append(f"+{added} added")
        if bound:
            parts.append(f"{bound} bound")
        if rebound:
            parts.append(f"{rebound} rebound")
        if no_marker_cam:
            parts.append(f"{no_marker_cam} marker w/o camera")
        if unresolved:
            parts.append(f"{unresolved} unresolved")
        orphaned = sum(1 for s in st.shots if s.orphan)
        if orphaned:
            parts.append(f"{orphaned} orphan")
        if cast_imported:
            parts.append(f"{cast_imported} cast imported")
        # Phase B: 使用カメラ集合が変わった可能性が高いので可視性更新
        try:
            from ..runtime import camera_visibility  # noqa: PLC0415
            camera_visibility.apply_camera_visibility(scene)
        except Exception:
            pass
        self.report({"INFO"}, "Sync: " + (", ".join(parts) if parts else "no change"))
        return {"FINISHED"}


class KINEMA_OT_add_shot(KinemaOperator):
    bl_idname = "kinema.add_shot"
    bl_label = "Add Shot"
    bl_description = "Shot を末尾に追加（Marker は別途用意が必要）"

    def run(self, context):
        st = context.scene.kinema
        s = st.shots.add()
        s.name = f"Shot_{len(st.shots):03d}"
        s.orphan = True
        st.active_shot_index = len(st.shots) - 1
        return {"FINISHED"}


class KINEMA_OT_remove_shot(KinemaOperator):
    bl_idname = "kinema.remove_shot"
    bl_label = "Remove Shot"
    bl_description = "Active Shot を削除（Timeline Marker は影響なし）"

    def run(self, context):
        st = context.scene.kinema
        idx = st.active_shot_index
        if not (0 <= idx < len(st.shots)):
            return {"CANCELLED"}
        st.shots.remove(idx)
        st.active_shot_index = max(0, min(idx, len(st.shots) - 1))
        return {"FINISHED"}


class KINEMA_OT_move_shot(KinemaOperator):
    bl_idname = "kinema.move_shot"
    bl_label = "Move Shot"
    bl_description = "Shot の表示順を入れ替える"

    direction: IntProperty(default=0)

    def run(self, context):
        st = context.scene.kinema
        idx = st.active_shot_index
        if not (0 <= idx < len(st.shots)):
            return {"CANCELLED"}
        new_idx = idx + int(self.direction)
        if not (0 <= new_idx < len(st.shots)):
            return {"CANCELLED"}
        st.shots.move(idx, new_idx)
        st.active_shot_index = new_idx
        return {"FINISHED"}


class KINEMA_OT_rename_shot(KinemaOperator):
    """Shot 名を変更し、Marker / Instance を連動 rename。"""
    bl_idname = "kinema.rename_shot"
    bl_label = "Rename Shot"
    bl_description = "Shot 名 + Marker + Instance を連動 rename"

    new_name: StringProperty(name="New Name")
    cascade_marker: BoolProperty(name="Rename Marker", default=True)
    cascade_instance: BoolProperty(name="Rename Instance", default=True)

    def invoke(self, context, event):  # noqa: ARG002
        st = context.scene.kinema
        idx = st.active_shot_index
        if not (0 <= idx < len(st.shots)):
            self.report({"WARNING"}, "Shot が選択されていません")
            return {"CANCELLED"}
        self.new_name = st.shots[idx].name
        return context.window_manager.invoke_props_dialog(self, width=360)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "new_name", text="New Name")
        layout.prop(self, "cascade_marker")
        layout.prop(self, "cascade_instance")

    def run(self, context):
        scene = context.scene
        st = scene.kinema
        idx = st.active_shot_index
        if not (0 <= idx < len(st.shots)):
            return {"CANCELLED"}
        shot = st.shots[idx]
        new_name = self.new_name.strip()
        if not new_name or new_name == shot.name:
            return {"CANCELLED"}

        old_marker = shot.marker_name
        old_instance = shot.instance_name

        if self.cascade_marker and old_marker:
            m = scene.timeline_markers.get(old_marker)
            if m is not None:
                try:
                    m.name = new_name
                    shot.marker_name = m.name
                except Exception:
                    pass

        if self.cascade_instance and old_instance:
            inst = next((i for i in st.instances if i.name == old_instance), None)
            if inst is not None:
                try:
                    inst.name = new_name
                    shot.instance_name = inst.name
                except Exception:
                    pass

        shot.name = new_name
        self.report({"INFO"}, f"Renamed → {new_name}")
        return {"FINISHED"}


class KINEMA_OT_jump_to_shot(KinemaOperator):
    """Active Shot の frame_start に jump + カメラ切替（ボタン版）。"""
    bl_idname = "kinema.jump_to_shot"
    bl_label = "Jump to Shot"
    bl_description = "Shot の開始フレームに移動し、紐付き Instance のカメラに切替"

    def run(self, context):
        scene = context.scene
        st = scene.kinema
        idx = st.active_shot_index
        if not (0 <= idx < len(st.shots)):
            return {"CANCELLED"}
        shot = st.shots[idx]
        sorted_ms = _sorted_markers(scene)
        fs, _fe = _resolve_shot_frame_range(scene, shot, sorted_ms)
        scene.frame_current = fs
        if shot.instance_name:
            inst = next((i for i in st.instances if i.name == shot.instance_name), None)
            if inst is not None:
                cam = refs.safe_object(inst.camera_ref)
                if cam is not None and cam.type == "CAMERA":
                    scene.camera = cam
                    try:
                        st.active_instance_index = list(st.instances).index(inst)
                    except ValueError:
                        pass
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Cast 操作
# ---------------------------------------------------------------------------

class KINEMA_OT_shot_cast_toggle(KinemaOperator):
    """Active Shot の cast に対し group_name のエントリを ON/OFF。

    リアルタイム bake: toggle 後に visibility_kit へ bake 依頼を出し、
    viewport を即座に再評価して結果を反映する。
    """
    bl_idname = "kinema.shot_cast_toggle"
    bl_label = "Toggle Cast Entry"
    bl_description = "Active Shot に対する Group の出演フラグをトグル（即時 bake）"

    group_name: StringProperty()

    def run(self, context):
        scene = context.scene
        st = scene.kinema
        idx = st.active_shot_index
        if not (0 <= idx < len(st.shots)):
            return {"CANCELLED"}
        shot = st.shots[idx]
        existing_idx = -1
        for i, ce in enumerate(shot.cast):
            if ce.group_name == self.group_name:
                existing_idx = i
                break
        if existing_idx >= 0:
            shot.cast.remove(existing_idx)
            action = "OFF"
        else:
            ce = shot.cast.add()
            ce.group_name = self.group_name
            ce.enabled = True
            action = "ON"
        # **全 Group bake**: toggle した group だけ bake すると、cast に未登録の
        # 他 group が hide されないまま残る（shot 切替時に居座る）。
        try:
            _vkb.request_bake_all_groups(scene, force=True)
        except Exception as exc:
            print(f"[kinema:shot_cast] bake_all failed: {exc}")
        # viewport 即時反映（複合 refresh）
        _vkb.force_viewport_refresh(scene)
        self.report({"INFO"}, f"Cast '{self.group_name}' → {action}")
        return {"FINISHED"}


class KINEMA_OT_shot_bake_cast_now(KinemaOperator):
    """Active Shot に紐づく全 Group を bake し直す（明示）。

    `yato_vis.cast_auto_bake` が OFF の人や、cast 設定を一括変更した後の
    強制再 bake に使う。
    """
    bl_idname = "kinema.shot_bake_cast_now"
    bl_label = "Bake Cast Now"
    bl_description = "Active Shot の cast に基づき、全 Group の hide キーを今すぐ bake"

    def run(self, context):
        scene = context.scene
        st = scene.kinema
        if not _vkb.is_available(scene):
            self.report({"WARNING"}, "yato_visibility_kit が登録されていません")
            return {"CANCELLED"}
        # 全 Group を bake（Extensions / legacy 両対応の動的 import 経由）
        cast_ops_mod = _vkb.import_vk_cast_ops()
        if cast_ops_mod is None or not hasattr(cast_ops_mod, "bake_group_cast"):
            self.report({"ERROR"}, "yato_visibility_kit.ops.cast_ops が import 不能")
            return {"CANCELLED"}
        bake_group_cast = cast_ops_mod.bake_group_cast
        baked = 0
        for g in _vkb.list_groups(scene):
            try:
                bake_group_cast(scene, g)
                baked += 1
            except Exception as exc:
                print(f"[kinema:shot_cast] bake_all error on '{g.name}': {exc}")
        # viewport refresh
        _vkb.force_viewport_refresh(scene)
        self.report({"INFO"}, f"Baked {baked} group(s)")
        return {"FINISHED"}


class KINEMA_OT_shot_cast_clear(KinemaOperator):
    """Active Shot の cast を空にする（全 OFF）。"""
    bl_idname = "kinema.shot_cast_clear"
    bl_label = "Clear Cast"
    bl_description = "Active Shot のキャストを全 OFF にして即 bake"

    def run(self, context):
        scene = context.scene
        st = scene.kinema
        idx = st.active_shot_index
        if not (0 <= idx < len(st.shots)):
            return {"CANCELLED"}
        shot = st.shots[idx]
        # 削除対象 group_name を控えてから clear
        affected_groups = [ce.group_name for ce in shot.cast]
        shot.cast.clear()
        # 全 group bake（clear した group も、他で関係する group も一括反映）
        try:
            _vkb.request_bake_all_groups(scene, force=True)
        except Exception as exc:
            print(f"[kinema:shot_cast] bake_all failed: {exc}")
        _vkb.force_viewport_refresh(scene)
        self.report({"INFO"}, f"Cleared {len(affected_groups)} cast entries")
        return {"FINISHED"}


class KINEMA_OT_shot_cast_all(KinemaOperator):
    """Active Shot に全 Group を ON で乗せる。"""
    bl_idname = "kinema.shot_cast_all"
    bl_label = "All Groups On Stage"
    bl_description = "Active Shot に全 Group を出演 ON で追加して即 bake"

    def run(self, context):
        scene = context.scene
        st = scene.kinema
        idx = st.active_shot_index
        if not (0 <= idx < len(st.shots)):
            return {"CANCELLED"}
        shot = st.shots[idx]
        existing = {ce.group_name for ce in shot.cast}
        added = 0
        for gname in _vkb.all_group_names(scene):
            if gname in existing:
                continue
            ce = shot.cast.add()
            ce.group_name = gname
            ce.enabled = True
            added += 1
        # 一括 bake は最後に 1 回（per-group ループを廃止して全体 1 回）
        try:
            _vkb.request_bake_all_groups(scene, force=True)
        except Exception as exc:
            print(f"[kinema:shot_cast] bake_all failed: {exc}")
        _vkb.force_viewport_refresh(scene)
        self.report({"INFO"}, f"Added {added} groups to stage")
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# 診断
# ---------------------------------------------------------------------------

class KINEMA_OT_refresh_camera_visibility(KinemaOperator):
    """使ってないカメラを今すぐ hide_viewport=True に。

    `auto_hide_unused_cameras` ON 時、shots[] 編集後などに手動で再評価したい
    場合に使う。
    """
    bl_idname = "kinema.refresh_camera_visibility"
    bl_label = "Refresh Camera Visibility"
    bl_description = "使われていない Camera を hide_viewport=True に（今すぐ評価）"

    def run(self, context):
        from ..runtime import camera_visibility  # noqa: PLC0415
        hidden, shown = camera_visibility.apply_camera_visibility(context.scene)
        st = context.scene.kinema
        if not st.auto_hide_unused_cameras:
            self.report(
                {"INFO"},
                "auto_hide_unused_cameras が OFF です。トグルしてから再実行してください",
            )
            return {"FINISHED"}
        self.report({"INFO"}, f"Camera vis refresh: {hidden} hidden, {shown} shown")
        return {"FINISHED"}


class KINEMA_OT_diagnose_shots(KinemaOperator):
    """全 shots を System Console にダンプ。

    Active Shot については Cast 別の solo_target_name と、現フレームで
    bake が判定するであろう hidden 状態（Group メンバごと）も出力する。
    """
    bl_idname = "kinema.diagnose_shots"
    bl_label = "Diagnose Shots"
    bl_description = "全 shots の Marker / Instance / Cast 状態 + Active Shot の Solo 判定を Console にダンプ"

    def run(self, context):
        scene = context.scene
        st = scene.kinema
        print("=" * 60)
        print(f"[kinema:shot-diag] {len(st.shots)} shots, "
              f"{len(st.instances)} instances, "
              f"data_format_version={getattr(st, 'data_format_version', '?')}")
        print(f"[kinema:shot-diag] yato_vis available: {_vkb.is_available(scene)}")
        print(f"[kinema:shot-diag] yato_vis groups: {len(_vkb.list_groups(scene))}")
        print(f"[kinema:shot-diag] auto_hide_unused_cameras: {st.auto_hide_unused_cameras}")
        print("--- Shots ---")
        for i, s in enumerate(st.shots):
            marker = scene.timeline_markers.get(s.marker_name) if s.marker_name else None
            mk_info = f"f{marker.frame}" if marker else "NO MARKER"
            cast_summary = []
            for c in s.cast:
                if not c.enabled:
                    continue
                solo = f" solo='{c.solo_target_name}'" if c.solo_target_name else ""
                cast_summary.append(f"{c.group_name}{solo}")
            print(
                f"  #{i+1} '{s.name}' marker='{s.marker_name}' ({mk_info}) "
                f"instance='{s.instance_name or '(empty)'}' "
                f"cast=[{', '.join(cast_summary)}] orphan={s.orphan}"
            )
        # Active Shot の Solo 判定詳細
        idx = st.active_shot_index
        if 0 <= idx < len(st.shots):
            shot = st.shots[idx]
            print(f"--- Active Shot Solo Analysis ('{shot.name}', marker='{shot.marker_name}') ---")
            cast_ops_mod = _vkb.import_vk_cast_ops()
            if cast_ops_mod is not None and hasattr(cast_ops_mod, "_resolve_cast_state_at_shot"):
                for ce in shot.cast:
                    if not ce.enabled:
                        continue
                    g = None
                    for gg in _vkb.list_groups(scene):
                        if gg.name == ce.group_name:
                            g = gg
                            break
                    if g is None:
                        print(f"  Group '{ce.group_name}' (NOT FOUND in yato_vis)")
                        continue
                    cast_on, solo_target = cast_ops_mod._resolve_cast_state_at_shot(
                        scene, g, shot.marker_name,
                    )
                    print(f"  Group '{ce.group_name}': cast_on={cast_on}, solo='{solo_target}'")
                    # group_all_objects
                    if hasattr(cast_ops_mod, "group_all_objects"):
                        objs = cast_ops_mod.group_all_objects(g)
                    else:
                        try:
                            from yato_visibility_kit.ops.group_ops import group_all_objects
                            objs = group_all_objects(g)
                        except Exception:
                            objs = []
                    for o in objs:
                        if solo_target:
                            is_solo = (o.name == solo_target)
                            hidden = not (cast_on and is_solo)
                        else:
                            hidden = not cast_on
                        print(f"    obj '{o.name}': hide_viewport will be {hidden} "
                              f"(current={o.hide_viewport})")
            else:
                print("  (cast_ops_mod or _resolve_cast_state_at_shot not available)")
        print("=" * 60)
        self.report({"INFO"}, "Shot 診断を System Console にダンプ")
        return {"FINISHED"}
