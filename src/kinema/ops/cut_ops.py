"""Cut Operator 群。

Timeline Marker をマスターとして Cut の整合を取る。Sync は明示操作（自動同期はしない）。

カット運用フロー:
  1. Timeline に Camera Marker を打つ（Blender 標準: M キー / Ctrl+B etc.）
  2. kinema パネル「Sync from Markers」で Cut を生成 / 整合
  3. 各 Cut の Instance / enabled / notes を編集
  4. 「Render Cuts」で enabled な Cut を一括レンダー
"""

from __future__ import annotations

import os

import bpy
from bpy.props import IntProperty, StringProperty

from ..utils import refs
from ._base import KinemaOperator


# ---------------------------------------------------------------------------
# 内部ヘルパ
# ---------------------------------------------------------------------------

def _sorted_markers(scene):
    """Timeline Marker を frame 昇順で返す（同frame は name 順）。"""
    return sorted(
        list(scene.timeline_markers),
        key=lambda m: (m.frame, m.name),
    )


def _resolve_cut_frame_range(scene, cut, sorted_markers) -> tuple[int, int]:
    """Cut の実効フレーム範囲を返す。

    優先順位:
      1. frame_override=True → frame_start_override / frame_end_override
      2. Marker から計算（marker.frame .. 次 marker.frame - 1）
      3. Marker が見つからない（orphan）→ scene.frame_start / scene.frame_end
    """
    if cut.frame_override:
        return int(cut.frame_start_override), int(cut.frame_end_override)
    # Marker を marker_name で照合
    m = scene.timeline_markers.get(cut.marker_name)
    if m is None:
        return int(scene.frame_start), int(scene.frame_end)
    # frame_start = この marker の frame
    fs = m.frame
    # frame_end = 次 marker.frame - 1（同じ frame の Marker は除外）
    fe = scene.frame_end
    for nm in sorted_markers:
        if nm.frame > m.frame:
            fe = nm.frame - 1
            break
    return int(fs), int(fe)


def _find_instance_by_camera(st, camera_obj):
    """Instance リストから camera_ref が一致するものの name を返す。無ければ ""。"""
    if camera_obj is None:
        return ""
    for inst in st.instances:
        if refs.safe_object(inst.camera_ref) is camera_obj:
            return inst.name
    return ""


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------

class KINEMA_OT_sync_cuts_from_markers(KinemaOperator):
    """Timeline Marker を走査して Cut を整合する。

    挙動:
      - Marker は存在するが Cut が無い → 新規 Cut を末尾に追加
      - Cut.marker_name の Marker が存在しない → orphan=True を立てるが削除はしない
      - 既存 Cut の name / instance_name / enabled / notes は保持
      - marker.camera が設定されていて、対応 Instance があれば instance_name を補完
    """
    bl_idname = "kinema.sync_cuts_from_markers"
    bl_label = "Sync Cuts from Markers"
    bl_description = (
        "Timeline Marker を Cut に同期する。新規 Marker は新規 Cut として追加、"
        "Marker が消えた Cut は orphan としてマークし保持"
    )

    def run(self, context):
        scene = context.scene
        st = scene.kinema
        sorted_ms = _sorted_markers(scene)

        # 既存 Cut を marker_name でマッピング
        cut_by_marker = {c.marker_name: c for c in st.cuts if c.marker_name}

        added = 0
        adopted = 0
        orphaned = 0

        # 1) 全 Cut を一旦 orphan 候補にする → 後で Marker が見つかった Cut だけ復帰
        for c in st.cuts:
            c.orphan = True

        # 2) Marker を走査し、対応 Cut を更新 or 新規作成
        for m in sorted_ms:
            c = cut_by_marker.get(m.name)
            if c is None:
                # marker_name が一致するものが無い → name で再照合（古いデータ救済）
                c = next(
                    (x for x in st.cuts if x.name == m.name and not x.marker_name),
                    None,
                )
                if c is not None:
                    c.marker_name = m.name
                    adopted += 1
            if c is None:
                # 新規 Cut を末尾に作成
                c = st.cuts.add()
                c.name = m.name
                c.marker_name = m.name
                added += 1
            c.orphan = False
            # instance_name 未設定で marker.camera が指定されていれば補完
            if not c.instance_name:
                try:
                    cam_obj = getattr(m, "camera", None)
                except Exception:
                    cam_obj = None
                if cam_obj is not None:
                    inst_name = _find_instance_by_camera(st, cam_obj)
                    if inst_name:
                        c.instance_name = inst_name

        # 3) orphan の残りをカウント（削除はしない）
        orphaned = sum(1 for c in st.cuts if c.orphan)

        # active_cut_index を範囲内に
        if st.active_cut_index >= len(st.cuts):
            st.active_cut_index = max(0, len(st.cuts) - 1)

        parts = []
        if added:
            parts.append(f"+{added} added")
        if adopted:
            parts.append(f"{adopted} adopted")
        if orphaned:
            parts.append(f"{orphaned} orphan")
        msg = ", ".join(parts) if parts else "no change"
        self.report({"INFO"}, f"Cuts sync: {msg}")
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Add / Remove / Move
# ---------------------------------------------------------------------------

class KINEMA_OT_add_cut(KinemaOperator):
    """Cut を新規追加（Marker は生成しない、純粋な kinema 側エントリ）。"""
    bl_idname = "kinema.add_cut"
    bl_label = "Add Cut"
    bl_description = "Cut を末尾に追加。Marker は生成しないので必要なら Sync 前に Marker を打つ"

    def run(self, context):
        st = context.scene.kinema
        c = st.cuts.add()
        c.name = f"Cut_{len(st.cuts):03d}"
        c.marker_name = ""  # 未紐付
        c.orphan = True  # Marker と紐付くまでは orphan 扱い
        st.active_cut_index = len(st.cuts) - 1
        return {"FINISHED"}


class KINEMA_OT_remove_cut(KinemaOperator):
    """Active Cut を削除（Marker 自体は触らない）。"""
    bl_idname = "kinema.remove_cut"
    bl_label = "Remove Cut"
    bl_description = "Active Cut を削除（Timeline Marker は影響を受けない）"

    def run(self, context):
        st = context.scene.kinema
        idx = st.active_cut_index
        if not (0 <= idx < len(st.cuts)):
            return {"CANCELLED"}
        st.cuts.remove(idx)
        st.active_cut_index = max(0, min(idx, len(st.cuts) - 1))
        return {"FINISHED"}


class KINEMA_OT_move_cut(KinemaOperator):
    """Cut の表示順を入れ替える（Marker frame には影響しない）。"""
    bl_idname = "kinema.move_cut"
    bl_label = "Move Cut"
    bl_description = "Cut リスト内での順序を入れ替える"

    direction: IntProperty(default=0)  # -1=up, 1=down

    def run(self, context):
        st = context.scene.kinema
        idx = st.active_cut_index
        if not (0 <= idx < len(st.cuts)):
            return {"CANCELLED"}
        new_idx = idx + int(self.direction)
        if not (0 <= new_idx < len(st.cuts)):
            return {"CANCELLED"}
        st.cuts.move(idx, new_idx)
        st.active_cut_index = new_idx
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Rename cascade
# ---------------------------------------------------------------------------

class KINEMA_OT_rename_cut(KinemaOperator):
    """Cut を rename し、Marker / Instance / Collection / Camera を連動 rename。

    Cut.name は update callback を持たない（無限再帰 / 副作用を避けるため）。
    UI で rename したい時はこの Operator を経由する。
    """
    bl_idname = "kinema.rename_cut"
    bl_label = "Rename Cut"
    bl_description = (
        "Cut 名を変更し、対応する Marker / Instance / Collection / Camera も同名に "
        "カスケード rename する"
    )

    new_name: StringProperty(name="New Name")
    cascade_marker: bpy.props.BoolProperty(name="Rename Marker", default=True)
    cascade_instance: bpy.props.BoolProperty(name="Rename Instance", default=True)

    def invoke(self, context, event):  # noqa: ARG002
        st = context.scene.kinema
        idx = st.active_cut_index
        if not (0 <= idx < len(st.cuts)):
            self.report({"WARNING"}, "Cut が選択されていません")
            return {"CANCELLED"}
        self.new_name = st.cuts[idx].name
        return context.window_manager.invoke_props_dialog(self, width=360)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "new_name", text="New Name")
        layout.prop(self, "cascade_marker")
        layout.prop(self, "cascade_instance")

    def run(self, context):
        scene = context.scene
        st = scene.kinema
        idx = st.active_cut_index
        if not (0 <= idx < len(st.cuts)):
            return {"CANCELLED"}
        cut = st.cuts[idx]
        new_name = self.new_name.strip()
        if not new_name or new_name == cut.name:
            return {"CANCELLED"}

        old_marker = cut.marker_name
        old_instance = cut.instance_name

        # 1) Marker を rename（cascade_marker ON のとき）
        if self.cascade_marker and old_marker:
            m = scene.timeline_markers.get(old_marker)
            if m is not None:
                try:
                    m.name = new_name
                    cut.marker_name = m.name  # Blender が衝突回避で別名になる可能性
                except Exception:
                    pass

        # 2) Instance を rename（cascade_instance ON のとき）
        if self.cascade_instance and old_instance:
            inst = next((i for i in st.instances if i.name == old_instance), None)
            if inst is not None:
                try:
                    inst.name = new_name  # Instance 側の update callback が
                    cut.instance_name = inst.name  # collection/camera を rename
                except Exception:
                    pass

        # 3) Cut 名を最後に変える
        cut.name = new_name
        self.report({"INFO"}, f"Renamed → {new_name}")
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Cut → Camera / Frame ジャンプ
# ---------------------------------------------------------------------------

class KINEMA_OT_jump_to_cut(KinemaOperator):
    """Active Cut の frame_start に jump し、紐付き Instance のカメラに切替。"""
    bl_idname = "kinema.jump_to_cut"
    bl_label = "Jump to Cut"
    bl_description = "Cut の開始フレームに移動し、紐付け Instance のカメラを scene.camera に設定"

    def run(self, context):
        scene = context.scene
        st = scene.kinema
        idx = st.active_cut_index
        if not (0 <= idx < len(st.cuts)):
            return {"CANCELLED"}
        cut = st.cuts[idx]
        sorted_ms = _sorted_markers(scene)
        fs, _fe = _resolve_cut_frame_range(scene, cut, sorted_ms)
        scene.frame_current = fs
        # Instance が紐付いていればそのカメラを scene.camera に
        if cut.instance_name:
            inst = next((i for i in st.instances if i.name == cut.instance_name), None)
            if inst is not None:
                cam = refs.safe_object(inst.camera_ref)
                if cam is not None and cam.type == "CAMERA":
                    scene.camera = cam
                    # active_instance_index も連動
                    try:
                        st.active_instance_index = list(st.instances).index(inst)
                    except ValueError:
                        pass
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Render Cuts （render_ops の非同期キューを再利用）
# ---------------------------------------------------------------------------

class KINEMA_OT_render_cuts(KinemaOperator):
    """enabled な Cut を順に <base>/<cut_name>/ にキューでレンダー。

    各 Cut の frame_start / frame_end / camera は Cut 設定 + Marker から解決して
    一時的に scene にセット → 非同期キュー（render_ops）にバトンタッチ。
    """
    bl_idname = "kinema.render_cuts"
    bl_label = "Render Cuts"
    bl_description = (
        "enabled が ON の Cut を順に <base>/<cut_name>/ サブフォルダに "
        "非同期キューでバッチレンダー"
    )

    def invoke(self, context, event):  # noqa: ARG002
        return context.window_manager.invoke_props_dialog(self, width=600)

    def draw(self, context):
        from ..ops import render_ops as _ro
        scene = context.scene
        st = scene.kinema
        sorted_ms = _sorted_markers(scene)
        targets = [c for c in st.cuts if c.enabled and not c.orphan]
        layout = self.layout
        layout.label(text="Render Cuts", icon="RENDER_ANIMATION")
        layout.separator()
        if _ro.is_queue_active():
            layout.label(text="既にレンダリングキューが実行中です", icon="ERROR")
            return
        if not targets:
            layout.label(text="enabled かつ orphan でない Cut がありません", icon="ERROR")
            return

        ext = _ro._resolve_extension(scene) or "(none)"
        fmt, _is_movie = _ro._resolve_format_label(scene)
        base_dir = _ro._normalize_dir(bpy.path.abspath(scene.render.filepath))

        box = layout.box()
        box.label(text="出力設定", icon="OUTPUT")
        box.label(text=f"Base: {scene.render.filepath}")
        box.label(text=f"Format: {fmt}   Extension: {ext}")

        layout.separator()
        layout.label(text=f"対象 {len(targets)} Cuts:")
        col = layout.column(align=True)
        col.scale_y = 0.85
        for cut in targets[:12]:
            fs, fe = _resolve_cut_frame_range(scene, cut, sorted_ms)
            inst_label = cut.instance_name or "(no instance)"
            sub = base_dir + cut.name + os.sep
            col.label(
                text=f"  🎬 {cut.name}  F{fs}-{fe}  →  {inst_label}  ({sub})",
            )
        if len(targets) > 12:
            col.label(text=f"  ... and {len(targets) - 12} more")

    def run(self, context):
        from ..ops import render_ops as _ro
        scene = context.scene
        st = scene.kinema

        if _ro.is_queue_active():
            self.report({"WARNING"}, "既にレンダリングキューが実行中です")
            return {"CANCELLED"}

        targets = [c for c in st.cuts if c.enabled and not c.orphan]
        if not targets:
            self.report({"WARNING"}, "enabled かつ orphan でない Cut がありません")
            return {"CANCELLED"}

        sorted_ms = _sorted_markers(scene)
        base_dir = _ro._normalize_dir(scene.render.filepath)
        items: list = []
        skipped = 0
        for cut in targets:
            if not cut.instance_name:
                skipped += 1
                continue
            inst = next((i for i in st.instances if i.name == cut.instance_name), None)
            if inst is None:
                skipped += 1
                continue
            cam = refs.safe_object(inst.camera_ref)
            if not refs.is_camera_object(cam):
                skipped += 1
                continue
            fs, fe = _resolve_cut_frame_range(scene, cut, sorted_ms)
            sub = base_dir + cut.name + os.sep
            items.append((sub, cam, cut.name, fs, fe))

        if not items:
            self.report({"WARNING"}, "Render 可能な Cut がありません（Instance 未紐付？）")
            return {"CANCELLED"}

        if _ro.kickoff_queue_with_ranges(scene, items):
            self.report(
                {"INFO"},
                f"Queued {len(items)} cuts"
                + (f" ({skipped} skipped)" if skipped else ""),
            )
            return {"FINISHED"}
        self.report({"ERROR"}, "キューの起動に失敗")
        return {"CANCELLED"}
