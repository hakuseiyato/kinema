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
from bpy.props import BoolProperty, IntProperty, StringProperty

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
    """Instance リストから camera_ref が一致するものの name を返す。無ければ ""。

    マッチング順:
      1. Python 識別子 (`is`) — 同じラッパー
      2. **camera.name による比較** — Blender が別ラッパーを返すケースの救済
         （これが今回の「正しくバインド読めない」の主因だった）
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
    """Cut 名や Marker 名に同じ名前の Instance があれば紐付ける（最終フォールバック）。"""
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

    force_rebind: bpy.props.BoolProperty(
        name="Force Rebind (overwrite existing instance_name)",
        description=(
            "既に instance_name がセットされている Cut でも、Marker.camera から"
            "改めてバインドし直す。Cut の Instance 紐付が崩れている時に使う"
        ),
        default=False,
    )

    def invoke(self, context, event):  # noqa: ARG002
        return context.window_manager.invoke_props_dialog(self, width=460)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "force_rebind")
        layout.separator()
        layout.label(text="バインド解決順:", icon="INFO")
        col = layout.column(align=True)
        col.scale_y = 0.85
        col.label(text="  1. Marker.camera → Instance.camera_ref (識別子)")
        col.label(text="  2. Marker.camera.name → Instance.camera_ref.name")
        col.label(text="  3. Marker.name → Instance.name (同名フォールバック)")

    def run(self, context):
        scene = context.scene
        st = scene.kinema
        sorted_ms = _sorted_markers(scene)

        # 既存 Cut を marker_name でマッピング
        cut_by_marker = {c.marker_name: c for c in st.cuts if c.marker_name}

        added = 0
        adopted = 0
        bound = 0
        rebound = 0
        no_marker_cam = 0  # marker.camera が None だった件数
        unresolved = 0     # camera あったが Instance に該当無し

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

            # instance_name の解決（force_rebind ON なら既存も上書き）
            need_bind = self.force_rebind or not c.instance_name
            if not need_bind:
                continue

            try:
                cam_obj = getattr(m, "camera", None)
            except Exception:
                cam_obj = None

            # 解決順 1+2: marker.camera 経由（識別子 → name）
            resolved_inst = ""
            if cam_obj is not None:
                resolved_inst = _find_instance_by_camera(st, cam_obj)
                if not resolved_inst:
                    unresolved += 1
            else:
                no_marker_cam += 1

            # 解決順 3: marker.name と同名の Instance（フォールバック）
            if not resolved_inst:
                resolved_inst = _find_instance_by_name(st, m.name)

            if resolved_inst:
                was = c.instance_name
                c.instance_name = resolved_inst
                if was and was != resolved_inst:
                    rebound += 1
                else:
                    bound += 1

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
        if bound:
            parts.append(f"{bound} bound")
        if rebound:
            parts.append(f"{rebound} rebound")
        if no_marker_cam:
            parts.append(f"{no_marker_cam} marker w/o camera")
        if unresolved:
            parts.append(f"{unresolved} unresolved")
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

class KINEMA_OT_diagnose_cut_binding(KinemaOperator):
    """全 Cut のバインド状態を System Console にダンプ。

    なぜ instance_name が空 / 誤バインドなのかの調査に使う。
    """
    bl_idname = "kinema.diagnose_cut_binding"
    bl_label = "Diagnose Cut Binding"
    bl_description = "全 Cut の Marker / Camera / Instance 紐付け状態を System Console にダンプ"

    def run(self, context):
        scene = context.scene
        st = scene.kinema
        print("=" * 60)
        print(f"[kinema:cut-diag] {len(st.cuts)} cuts")
        print(f"[kinema:cut-diag] {len(st.instances)} instances")
        # Instance name → camera name の表
        print("--- Instances ---")
        for i, inst in enumerate(st.instances):
            cam = refs.safe_object(inst.camera_ref)
            cam_name = cam.name if cam is not None else "(no cam)"
            print(f"  #{i+1} '{inst.name}' → camera='{cam_name}'")
        # Cut 一覧 + Marker.camera 状態
        print("--- Cuts vs Markers ---")
        for i, cut in enumerate(st.cuts):
            marker = scene.timeline_markers.get(cut.marker_name)
            if marker is None:
                marker_info = f"NO MARKER ('{cut.marker_name}')"
            else:
                try:
                    mc = marker.camera
                except Exception:
                    mc = None
                mc_name = mc.name if mc is not None else "(no camera)"
                marker_info = f"marker f{marker.frame} cam='{mc_name}'"
            print(
                f"  #{i+1} cut='{cut.name}' marker='{cut.marker_name}' "
                f"instance='{cut.instance_name or '(empty)'}' orphan={cut.orphan} | {marker_info}"
            )
        print("=" * 60)
        self.report({"INFO"}, "Cut バインド診断を System Console にダンプしました")
        return {"FINISHED"}


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

def _build_cut_queue_items(scene, cuts) -> tuple[list, int]:
    """Cut のリストを render queue items に変換する。

    戻り値: (items, skipped)
    """
    from ..ops import render_ops as _ro
    st = scene.kinema
    sorted_ms = _sorted_markers(scene)
    base_dir = _ro._normalize_dir(scene.render.filepath)
    items: list = []
    skipped = 0
    for cut in cuts:
        if cut.orphan and not cut.frame_override:
            # orphan + frame_override 無し → 範囲が不明なので skip
            skipped += 1
            continue
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
    return items, skipped


def _draw_cut_summary(layout, scene, targets, title: str) -> None:
    """Render ダイアログの共通サマリ描画。"""
    from ..ops import render_ops as _ro
    sorted_ms = _sorted_markers(scene)
    layout.label(text=title, icon="RENDER_ANIMATION")
    layout.separator()
    if _ro.is_queue_active():
        layout.label(text="既にレンダリングキューが実行中です", icon="ERROR")
        return
    if not targets:
        layout.label(text="対象 Cut がありません", icon="ERROR")
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
        try:
            fs, fe = _resolve_cut_frame_range(scene, cut, sorted_ms)
        except Exception:
            fs, fe = scene.frame_start, scene.frame_end
        inst_label = cut.instance_name or "(no instance)"
        sub = base_dir + (cut.name or "?") + os.sep
        # 絵文字を避けて ASCII で表示（古い Blender で稀にクラッシュ報告あり）
        col.label(
            text=f"  [{cut.name}]  F{fs}-{fe}  ->  {inst_label}",
            icon="SEQUENCE",
        )
        # 出力先パスは別行で（短く / clipping 対策）
        col.label(text=f"    {sub}")
    if len(targets) > 12:
        col.label(text=f"  ... and {len(targets) - 12} more")


class KINEMA_OT_render_cuts(KinemaOperator):
    """Cut を同期バッチレンダー。

    `scope` で対象を選択:
      - ACTIVE  : Active Cut 1 個だけ
      - ENABLED : enabled な Cut すべて
    """
    bl_idname = "kinema.render_cuts"
    bl_label = "Render Cuts"
    bl_description = (
        "Cut を <base>/<cut_name>/ サブフォルダに同期バッチレンダー。"
        "対象は Active Cut か Enabled Cuts 全部から選択"
    )

    scope: bpy.props.EnumProperty(
        name="Scope",
        items=(
            ("ACTIVE", "Active Cut", "Active Cut だけ（enabled 無視）"),
            ("ENABLED", "Enabled Cuts", "enabled=ON な Cut をすべて"),
        ),
        default="ACTIVE",
    )

    def invoke(self, context, event):  # noqa: ARG002
        try:
            return context.window_manager.invoke_props_dialog(self, width=560)
        except Exception as exc:
            self.report({"ERROR"}, f"ダイアログ起動失敗: {exc}")
            return {"CANCELLED"}

    def _resolve_targets(self, scene):
        try:
            st = scene.kinema
        except Exception:
            return []
        cuts = list(st.cuts)
        if self.scope == "ACTIVE":
            idx = st.active_cut_index
            if 0 <= idx < len(cuts):
                return [cuts[idx]]
            return []
        # ENABLED
        return [c for c in cuts if c.enabled and not c.orphan]

    def draw(self, context):
        layout = self.layout
        try:
            layout.prop(self, "scope", text="対象", expand=True)
            layout.separator()
            scene = context.scene
            targets = self._resolve_targets(scene)
            _draw_cut_summary(layout, scene, targets, "Render Cuts")
            layout.separator()
            warn = layout.row()
            warn.alert = True
            warn.label(text="同期レンダー: 終了まで Blender はブロック (Esc で中断)",
                       icon="INFO")
        except Exception as exc:
            layout.label(text=f"描画エラー: {exc}", icon="ERROR")
            print(f"[kinema:render_cuts] draw error: {exc}")

    def run(self, context):
        from ..ops import render_ops as _ro
        scene = context.scene

        targets = self._resolve_targets(scene)
        if not targets:
            self.report({"WARNING"}, "対象 Cut がありません")
            return {"CANCELLED"}

        items, skipped = _build_cut_queue_items(scene, targets)
        if not items:
            self.report({"WARNING"}, "Render 可能な Cut がありません（Instance 未紐付？）")
            return {"CANCELLED"}

        result = _ro.run_render_queue(scene, items)
        msg = f"Rendered {result['rendered']} cuts ({self.scope})"
        if result["skipped"] or skipped:
            total_skip = result["skipped"] + skipped
            msg += f", {total_skip} skipped"
        self.report({"INFO"}, msg)
        return {"FINISHED"}
