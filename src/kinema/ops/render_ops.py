"""Camera Marker ベースのバッチレンダー Operator。

Timeline 上の `scene.timeline_markers` のうち `marker.camera` が set されている
ものを「カメラ切替ポイント」として読み、各カメラのフレーム範囲ごとに別ファイル
（サブフォルダ `<base>/<cam_name>/`）として出力する。

仕組み:
  1. timeline_markers から (frame, camera) を抽出して frame 昇順で並べる
  2. 各 marker の frame 〜 次 marker の (frame - 1) を「そのカメラの担当範囲」と
     見做す。最後の marker は scene.frame_end まで
  3. scene.frame_start 未満 / scene.frame_end 超過の範囲はクリップ
  4. 各範囲について:
       - scene.render.filepath を `<base>/<cam_name>/` に書き換え
       - scene.frame_start / frame_end を範囲に
       - scene.camera を切替
       - bpy.ops.render.render(animation=True) を呼ぶ
     終わったら元の設定を全て復元

MP4 (FFmpeg) と PNG 連番のどちらでも動く。Blender が出力フォーマットに
従ってファイル名を付ける（連番 / 範囲付きファイル名）。
"""

from __future__ import annotations

import os

import bpy

from ._base import KinemaOperator


def _extract_camera_ranges(scene):
    """timeline_markers からカメラ担当範囲を抽出する。

    返値: [(camera_obj, frame_start, frame_end, marker_name), ...]
    範囲は [frame_start, frame_end] の閉区間。
    """
    markers = sorted(
        [m for m in scene.timeline_markers if m.camera is not None],
        key=lambda m: m.frame,
    )
    if not markers:
        return []
    s_min = scene.frame_start
    s_max = scene.frame_end

    ranges = []
    for i, m in enumerate(markers):
        cam = m.camera
        fs = m.frame
        fe = markers[i + 1].frame - 1 if (i + 1) < len(markers) else s_max
        # クリップ
        fs = max(fs, s_min)
        fe = min(fe, s_max)
        if fe < fs:
            continue
        ranges.append((cam, fs, fe, m.name))
    return ranges


def _normalize_dir(path: str) -> str:
    """末尾に / を付与してディレクトリ扱いにする。

    Blender の render.filepath は末尾が `/` or `\\` だと「ディレクトリ + 連番」、
    そうでないと「ファイル名のベース」として解釈される。
    """
    if not path:
        return path
    if path.endswith(("/", "\\", os.sep)):
        return path
    return path + os.sep


class KINEMA_OT_render_by_markers(KinemaOperator):
    """Timeline の Camera Marker ごとに別フォルダへバッチレンダーする。

    出力先: `<scene.render.filepath>/<cam_name>/` (各 marker のフレーム範囲)。
    MP4 / 静止画連番のどちらでも動作する。
    """
    bl_idname = "kinema.render_by_markers"
    bl_label = "Render by Camera Markers"
    bl_description = (
        "Timeline の Camera Marker でカメラ別に範囲を分け、"
        "<base>/<cam_name>/ サブフォルダへバッチレンダー"
    )

    def invoke(self, context, event):  # noqa: ARG002
        return context.window_manager.invoke_props_dialog(self, width=480)

    def draw(self, context):
        scene = context.scene
        layout = self.layout
        layout.label(text="Render by Camera Markers", icon="RENDER_ANIMATION")
        layout.separator()
        ranges = _extract_camera_ranges(scene)
        if not ranges:
            layout.label(
                text="Camera Marker が見つかりません。",
                icon="ERROR",
            )
            layout.label(
                text="Timeline で M キーで marker を打ち、",
            )
            layout.label(
                text="Ctrl+B でアクティブカメラを Bind してください",
            )
            return

        base = _normalize_dir(bpy.path.abspath(scene.render.filepath))
        layout.label(text=f"Base: {scene.render.filepath}")
        layout.label(
            text=f"Format: {scene.render.image_settings.file_format}",
        )
        layout.separator()
        layout.label(text=f"対象 {len(ranges)} レンジ:")
        col = layout.column(align=True)
        col.scale_y = 0.85
        for cam, fs, fe, mname in ranges[:10]:
            col.label(
                text=f"  F{fs:04d}-{fe:04d}  →  {cam.name}/  (marker '{mname}')",
            )
        if len(ranges) > 10:
            col.label(text=f"  ... and {len(ranges) - 10} more ranges")
        layout.separator()
        layout.label(
            text="OK で順次レンダー実行。中断は Esc",
            icon="INFO",
        )

    def run(self, context):
        scene = context.scene
        ranges = _extract_camera_ranges(scene)
        if not ranges:
            self.report({"WARNING"}, "Camera Marker がありません")
            return {"CANCELLED"}

        # 元設定を保存
        orig_filepath = scene.render.filepath
        orig_fstart = scene.frame_start
        orig_fend = scene.frame_end
        orig_camera = scene.camera

        base_dir = _normalize_dir(orig_filepath)
        rendered = 0
        try:
            for cam, fs, fe, mname in ranges:
                # 出力パスをカメラ別サブフォルダに切替
                out_dir = base_dir + cam.name + os.sep
                scene.render.filepath = out_dir
                scene.frame_start = fs
                scene.frame_end = fe
                scene.camera = cam

                print(
                    f"[kinema:render] {cam.name}  F{fs}-{fe}  → {out_dir}"
                )
                try:
                    bpy.ops.render.render(animation=True)
                    rendered += 1
                except Exception as exc:
                    self.report(
                        {"WARNING"},
                        f"レンダー失敗 ({cam.name} F{fs}-{fe}): {exc}",
                    )
                    # 失敗しても他の範囲は続行
        finally:
            # 元設定を必ず復元
            scene.render.filepath = orig_filepath
            scene.frame_start = orig_fstart
            scene.frame_end = orig_fend
            scene.camera = orig_camera

        self.report(
            {"INFO"},
            f"Rendered {rendered}/{len(ranges)} ranges from camera markers",
        )
        return {"FINISHED"}


class KINEMA_OT_render_active_instance(KinemaOperator):
    """Active Instance のカメラ単体でレンダー（サブフォルダ分け）。

    Marker を使わず、現在 Active な Instance のカメラだけを scene.frame_start〜
    frame_end で `<base>/<cam_name>/` にレンダー出力する。
    """
    bl_idname = "kinema.render_active_instance"
    bl_label = "Render Active Instance"
    bl_description = (
        "Active Instance のカメラを scene.frame_start〜end で"
        " <base>/<cam_name>/ にレンダー"
    )

    def invoke(self, context, event):  # noqa: ARG002
        return context.window_manager.invoke_props_dialog(self, width=420)

    def draw(self, context):
        scene = context.scene
        st = scene.kinema
        layout = self.layout
        layout.label(text="Render Active Instance", icon="RENDER_ANIMATION")
        layout.separator()
        idx = st.active_instance_index
        if not (0 <= idx < len(st.instances)):
            layout.label(text="Instance が選択されていません", icon="ERROR")
            return
        cam = st.instances[idx].camera_ref
        cam_name = cam.name if cam is not None else "(none)"
        layout.label(text=f"対象: {cam_name}")
        layout.label(text=f"範囲: F{scene.frame_start}-{scene.frame_end}")
        layout.label(
            text=f"出力: {scene.render.filepath}/{cam_name}/",
        )
        layout.label(
            text=f"Format: {scene.render.image_settings.file_format}",
        )

    def run(self, context):
        from ..utils import refs  # noqa: PLC0415
        scene = context.scene
        st = scene.kinema
        idx = st.active_instance_index
        if not (0 <= idx < len(st.instances)):
            self.report({"WARNING"}, "Instance が選択されていません")
            return {"CANCELLED"}
        cam = refs.safe_object(st.instances[idx].camera_ref)
        if not refs.is_camera_object(cam):
            self.report({"ERROR"}, "Active Instance にカメラがありません")
            return {"CANCELLED"}

        orig_filepath = scene.render.filepath
        orig_camera = scene.camera
        base_dir = _normalize_dir(orig_filepath)
        try:
            scene.render.filepath = base_dir + cam.name + os.sep
            scene.camera = cam
            print(
                f"[kinema:render] {cam.name}  F{scene.frame_start}-{scene.frame_end}"
                f"  → {scene.render.filepath}"
            )
            bpy.ops.render.render(animation=True)
        except Exception as exc:
            self.report({"ERROR"}, f"レンダー失敗: {exc}")
            return {"CANCELLED"}
        finally:
            scene.render.filepath = orig_filepath
            scene.camera = orig_camera
        self.report({"INFO"}, f"Rendered {cam.name}")
        return {"FINISHED"}
