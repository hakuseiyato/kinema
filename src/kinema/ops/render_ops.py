"""バッチレンダー Operator。

非同期キュー方式: `bpy.ops.render.render('INVOKE_DEFAULT', animation=True)` で
モーダルウィンドウを開いてレンダーし、`render_complete` handler で次のキューを
進める。これにより Blender がブロックされず、Esc キャンセルも効く。

設計:
  1. Operator は「キューを積んで最初の 1 件を起動するだけ」で即 FINISHED を返す
  2. 各 render が完了すると `_on_render_complete` が呼ばれ、次のキューを timer
     で再起動（同期スタックを一度抜けてから）
  3. キューが空になったら `render.filepath` / `scene.camera` を復元 + handler を解除
  4. ユーザーが Esc キャンセルしたら `render_cancel` handler でキュー破棄 + 復元

出力ファイル名は Blender の `scene.render.file_extension` に従う:
  - PNG / JPEG / EXR 等の静止画: `<base>/<inst_name>/####.<ext>` (連番)
  - FFMPEG / AVI 等の動画: `<base>/<inst_name>/####-####.<ext>` (範囲付き)
"""

from __future__ import annotations

import os
from typing import Optional

import bpy
from bpy.app.handlers import persistent

from ..utils import refs
from ._base import KinemaOperator


# ---------------------------------------------------------------------------
# キュー状態（モジュールレベル）
# ---------------------------------------------------------------------------

# キュー要素: (subfolder_path, camera_obj, label[, frame_start, frame_end])
_render_queue: list = []
# 元の設定を保存（キュー終了時に復元）
_render_saved: dict = {}
# 現在キュー実行中フラグ
_render_active: bool = False
# キュー対象 Scene 名（timer 内で bpy.context.scene を使うとクラッシュリスクが
# 高いので、名前で保持して bpy.data.scenes.get() で解決する）
_render_scene_name: str = ""


def _normalize_dir(path: str) -> str:
    """末尾を OS 区切りでディレクトリ形式にする。"""
    if not path:
        return path
    if path.endswith(("/", "\\", os.sep)):
        return path
    return path + os.sep


def _is_movie_format(file_format: str) -> bool:
    """動画形式かどうか（1 ファイルにまとまる）。"""
    return file_format in {"FFMPEG", "AVI_JPEG", "AVI_RAW"}


_FFMPEG_CONTAINER_EXT = {
    "MPEG1": ".mpg",
    "MPEG2": ".dvd",
    "MPEG4": ".mp4",
    "AVI": ".avi",
    "QUICKTIME": ".mov",
    "DV": ".dv",
    "OGG": ".ogv",
    "MKV": ".mkv",
    "FLASH": ".flv",
    "WEBM": ".webm",
}


def _resolve_format_label(scene) -> tuple[str, bool]:
    """(表示用 format ラベル, 動画フラグ) を返す。

    Blender 4.5+ で `image_settings.media_type` が追加され、MOVIE のときは
    file_format が PNG 等のままでも実際は FFMPEG で出力される。
    """
    ims = scene.render.image_settings
    fmt = ims.file_format
    media_type = getattr(ims, "media_type", None)
    if media_type == "MOVIE":
        # ffmpeg 設定から container を読む
        try:
            container = scene.render.ffmpeg.format
            return f"FFMPEG ({container})", True
        except Exception:
            return "FFMPEG", True
    return fmt, _is_movie_format(fmt)


def _resolve_extension(scene) -> str:
    """実際に出力されるファイル拡張子を返す（Blender 標準より正確）。

    `scene.render.frame_path(frame=N)` は Blender が実際にそのフレームで
    書き込むフルパス（拡張子込み）を返してくれる最も信頼できる API。
    `image_settings.file_format` / `media_type` / `ffmpeg.format` の組合せに
    関係なく、Blender 自身が決めた実拡張子をそのまま使える。

    フォールバック: API が失敗した場合のみ `scene.render.file_extension` と
    ffmpeg コンテナマップから推定する。
    """
    r = scene.render
    # 一次: frame_path() から拡張子を取る（Blender 自身の解決を信頼）
    try:
        sample_path = r.frame_path(frame=scene.frame_start)
        ext = os.path.splitext(sample_path)[1]
        if ext:
            return ext
    except Exception:
        pass

    # フォールバック: media_type=MOVIE なら ffmpeg.format から推定
    ims = r.image_settings
    media_type = getattr(ims, "media_type", None)
    if media_type == "MOVIE":
        try:
            container = r.ffmpeg.format
            ext = _FFMPEG_CONTAINER_EXT.get(container)
            if ext:
                return ext
        except Exception:
            pass

    # 最終フォールバック: Blender 標準
    return r.file_extension or ""


def _sample_output_path(scene, base_dir: str, inst_name: str) -> str:
    """Instance ごとの出力サンプルパスを文字列で生成（UI 表示用）。"""
    ext = _resolve_extension(scene)
    _label, is_movie = _resolve_format_label(scene)
    fs = scene.frame_start
    fe = scene.frame_end
    sub = base_dir + inst_name + os.sep
    if is_movie:
        return f"{sub}{fs:04d}-{fe:04d}{ext}"
    return f"{sub}{fs:04d}{ext}  ...  {fe:04d}{ext}"


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------

@persistent
def _on_render_complete(scene):
    """1 件の render 終了 → 次のキューを timer で起動。"""
    if not _render_active:
        return  # kinema 由来でないレンダー完了は無視
    if not _render_queue:
        # 全部完了 → 復元 & handler 解除
        _finalize(scene, reason="complete")
        return
    bpy.app.timers.register(_start_next_render, first_interval=0.2)


@persistent
def _on_render_cancel(scene):
    """ユーザーが Esc 等でキャンセルしたら キュー全破棄 + 復元。"""
    if not _render_active:
        return
    _render_queue.clear()
    _finalize(scene, reason="cancel")


def _finalize(scene, reason: str) -> None:
    """キュー終了処理。"""
    global _render_active, _render_scene_name
    # Scene が None のことがある（_force_clear_state 経由 / Scene 削除済み）
    if scene is None:
        scene = _resolve_queue_scene()
    if scene is not None:
        try:
            if "filepath" in _render_saved:
                scene.render.filepath = _render_saved["filepath"]
            if "camera" in _render_saved:
                scene.camera = _render_saved["camera"]
            if "frame_start" in _render_saved:
                scene.frame_start = _render_saved["frame_start"]
            if "frame_end" in _render_saved:
                scene.frame_end = _render_saved["frame_end"]
        except Exception:
            pass
    _render_saved.clear()
    _render_active = False
    _render_scene_name = ""
    # handler を外す
    for hook_list, fn in (
        (bpy.app.handlers.render_complete, _on_render_complete),
        (bpy.app.handlers.render_cancel, _on_render_cancel),
    ):
        try:
            if fn in hook_list:
                hook_list.remove(fn)
        except Exception:
            pass
    # dispatcher の render モードも明示解除（取りこぼし防止）
    try:
        from ..runtime import instance_dispatcher as _id
        _id.set_rendering(False)
    except Exception:
        pass
    print(f"[kinema:render] queue finalized ({reason})")


def _resolve_queue_scene():
    """キュー対象 Scene を名前で安全に解決する。

    timer / handler context で `bpy.context.scene` を参照すると、context が
    無効な瞬間に触れてクラッシュする可能性がある。`bpy.data.scenes.get()`
    なら安全。Scene が消えていたら None を返す。
    """
    if not _render_scene_name:
        return None
    return bpy.data.scenes.get(_render_scene_name)


def _start_next_render():
    """timer から呼ばれて、INVOKE_DEFAULT で render を開始。

    キューアイテム形式は次の 2 種類をサポート:
      - (sub_dir, camera, label)                          : 既定 frame range を使う
      - (sub_dir, camera, label, frame_start, frame_end)  : 当該レンダーだけ範囲上書き
    """
    if not _render_queue:
        return None
    scene = _resolve_queue_scene()
    if scene is None:
        # Scene が消えた → キューを破棄して終了（context.scene へのフォールバック
        # は危険なのでしない）
        print("[kinema:render] target scene missing, aborting queue")
        _render_queue.clear()
        # finalize は scene が無いと一部復元できないが、フラグ解除だけ確実に
        _force_clear_state()
        return None
    item = _render_queue.pop(0)
    try:
        if len(item) == 5:
            sub_dir, camera, label, fs, fe = item
        else:
            sub_dir, camera, label = item
            fs, fe = None, None
    except Exception as exc:
        print(f"[kinema:render] malformed queue item: {exc}")
        _force_clear_state()
        return None
    try:
        # Camera が削除されていないか / Camera 型かを再確認
        if camera is None or getattr(camera, "type", None) != "CAMERA":
            print(f"[kinema:render] skipping '{label}': camera invalid")
            # 次のキューを試す
            bpy.app.timers.register(_start_next_render, first_interval=0.1)
            return None
        scene.render.filepath = sub_dir
        scene.camera = camera
        if fs is not None and fe is not None:
            scene.frame_start = int(fs)
            scene.frame_end = int(fe)
            print(f"[kinema:render] starting: {label}  F{fs}-{fe}  →  {sub_dir}")
        else:
            print(f"[kinema:render] starting: {label}  →  {sub_dir}")
        bpy.ops.render.render("INVOKE_DEFAULT", animation=True)
    except Exception as exc:
        print(f"[kinema:render] error starting render: {exc}")
        # エラーで次が動かないと困るので強制完了扱い
        _finalize(scene, reason=f"error: {exc}")
    return None  # timer は一度きり


def _force_clear_state() -> None:
    """Scene 不在等の異常系で、状態だけは確実に解除する。"""
    global _render_active, _render_scene_name
    _render_active = False
    _render_scene_name = ""
    _render_saved.clear()
    for hook_list, fn in (
        (bpy.app.handlers.render_complete, _on_render_complete),
        (bpy.app.handlers.render_cancel, _on_render_cancel),
    ):
        try:
            if fn in hook_list:
                hook_list.remove(fn)
        except Exception:
            pass
    # dispatcher の render モードも解除しておく（取りこぼし防止）
    try:
        from ..runtime import instance_dispatcher as _id
        _id.set_rendering(False)
    except Exception:
        pass


def _register_handlers():
    """重複なく handler を登録。"""
    for hook_list, fn in (
        (bpy.app.handlers.render_complete, _on_render_complete),
        (bpy.app.handlers.render_cancel, _on_render_cancel),
    ):
        if fn not in hook_list:
            hook_list.append(fn)


def _kickoff_queue(scene, queue_items: list) -> bool:
    """キューを積んで最初の render を起動。

    queue_items の各要素は 3-tuple か 5-tuple:
      - (sub_dir, camera, label)
      - (sub_dir, camera, label, frame_start, frame_end)
    戻り値: 起動できたら True。
    """
    global _render_active, _render_scene_name
    if _render_active:
        return False
    if not queue_items:
        return False

    _render_saved.clear()
    _render_saved["filepath"] = scene.render.filepath
    _render_saved["camera"] = scene.camera
    _render_saved["frame_start"] = scene.frame_start
    _render_saved["frame_end"] = scene.frame_end

    _render_queue.clear()
    _render_queue.extend(queue_items)
    _register_handlers()
    _render_active = True
    _render_scene_name = scene.name  # timer 内では名前で解決する

    # 最初のレンダーを起動
    bpy.app.timers.register(_start_next_render, first_interval=0.1)
    return True


def kickoff_queue_with_ranges(scene, items) -> bool:
    """外部 (cut_ops 等) から呼ぶ公開ラッパ。5-tuple 形式の items を直接渡す。"""
    return _kickoff_queue(scene, items)


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

class KINEMA_OT_render_selected_instances(KinemaOperator):
    """`enabled` チェックが入った Instance をキューに積んでバッチレンダー。

    非同期キュー方式: Blender はブロックされず、Esc でキャンセル可能。
    """
    bl_idname = "kinema.render_selected_instances"
    bl_label = "Render Selected Instances"
    bl_description = (
        "enabled が ON の Instance を順に <base>/<instance_name>/ "
        "サブフォルダへ非同期キューでバッチレンダー"
    )

    def invoke(self, context, event):  # noqa: ARG002
        return context.window_manager.invoke_props_dialog(self, width=560)

    def draw(self, context):
        scene = context.scene
        st = scene.kinema
        targets = [i for i in st.instances if i.enabled]
        layout = self.layout
        layout.label(text="Render Selected Instances", icon="RENDER_ANIMATION")
        layout.separator()
        if _render_active:
            layout.label(
                text="既にレンダリングキューが実行中です",
                icon="ERROR",
            )
            layout.label(
                text="Esc でキャンセル後に再実行してください",
            )
            return
        if not targets:
            layout.label(text="enabled な Instance がありません", icon="ERROR")
            layout.label(text="Instance リストの目アイコンで ON にしてください")
            return

        ext = _resolve_extension(scene) or "(none)"
        fmt, _is_movie = _resolve_format_label(scene)
        base_dir = _normalize_dir(bpy.path.abspath(scene.render.filepath))

        # メタ情報
        box = layout.box()
        box.label(text="出力設定", icon="OUTPUT")
        box.label(text=f"Base: {scene.render.filepath}")
        box.label(text=f"Format: {fmt}   Extension: {ext}")
        box.label(
            text=f"Frame range: F{scene.frame_start} – {scene.frame_end} "
                 f"({scene.frame_end - scene.frame_start + 1} frames)",
        )

        # 対象一覧
        layout.separator()
        layout.label(text=f"対象 {len(targets)} Instance:")
        col = layout.column(align=True)
        col.scale_y = 0.85
        for inst in targets[:10]:
            cam = refs.safe_object(inst.camera_ref)
            cam_name = cam.name if cam is not None else "(no cam)"
            sample = _sample_output_path(scene, base_dir, inst.name)
            col.label(text=f"  📷 {cam_name}  →  {sample}")
        if len(targets) > 10:
            col.label(text=f"  ... and {len(targets) - 10} more")
        layout.separator()
        layout.label(
            text="OK で非同期キューを起動。Esc で中断可能",
            icon="INFO",
        )

    def run(self, context):
        scene = context.scene
        st = scene.kinema

        if _render_active:
            self.report({"WARNING"}, "既にレンダリングキューが実行中です")
            return {"CANCELLED"}

        targets = [i for i in st.instances if i.enabled]
        if not targets:
            self.report({"WARNING"}, "enabled な Instance がありません")
            return {"CANCELLED"}

        base_dir = _normalize_dir(scene.render.filepath)
        items: list = []
        skipped = 0
        for inst in targets:
            cam = refs.safe_object(inst.camera_ref)
            if not refs.is_camera_object(cam):
                skipped += 1
                continue
            sub = base_dir + inst.name + os.sep
            items.append((sub, cam, inst.name))

        if not items:
            self.report({"WARNING"}, "有効なカメラを持つ Instance がありません")
            return {"CANCELLED"}

        if _kickoff_queue(scene, items):
            self.report(
                {"INFO"},
                f"Queued {len(items)} instances "
                + (f"({skipped} skipped: no camera)" if skipped else ""),
            )
            return {"FINISHED"}
        self.report({"ERROR"}, "キューの起動に失敗")
        return {"CANCELLED"}


class KINEMA_OT_render_active_instance(KinemaOperator):
    """Active Instance だけをキューに積んでレンダー（単発）。

    非同期キュー方式なので Blender はブロックされない。
    """
    bl_idname = "kinema.render_active_instance"
    bl_label = "Render Active Instance"
    bl_description = (
        "Active Instance のカメラを <base>/<inst_name>/ にレンダー "
        "(非同期、Esc で中断可)"
    )

    def invoke(self, context, event):  # noqa: ARG002
        return context.window_manager.invoke_props_dialog(self, width=480)

    def draw(self, context):
        scene = context.scene
        st = scene.kinema
        layout = self.layout
        layout.label(text="Render Active Instance", icon="RENDER_ANIMATION")
        layout.separator()
        if _render_active:
            layout.label(
                text="既にレンダリングキューが実行中です",
                icon="ERROR",
            )
            return
        idx = st.active_instance_index
        if not (0 <= idx < len(st.instances)):
            layout.label(text="Instance が選択されていません", icon="ERROR")
            return
        inst = st.instances[idx]
        cam = refs.safe_object(inst.camera_ref)
        if not refs.is_camera_object(cam):
            layout.label(text="Camera がありません", icon="ERROR")
            return

        ext = _resolve_extension(scene) or "(none)"
        fmt, _is_movie = _resolve_format_label(scene)
        base_dir = _normalize_dir(bpy.path.abspath(scene.render.filepath))
        sample = _sample_output_path(scene, base_dir, inst.name)

        box = layout.box()
        box.label(text="出力設定", icon="OUTPUT")
        box.label(text=f"Format: {fmt}   Extension: {ext}")
        box.label(
            text=f"Frame range: F{scene.frame_start} – {scene.frame_end}",
        )
        box.label(text=f"対象: 📷 {cam.name}")
        box.label(text=f"出力: {sample}")

    def run(self, context):
        scene = context.scene
        st = scene.kinema

        if _render_active:
            self.report({"WARNING"}, "既にレンダリングキューが実行中です")
            return {"CANCELLED"}

        idx = st.active_instance_index
        if not (0 <= idx < len(st.instances)):
            self.report({"WARNING"}, "Instance が選択されていません")
            return {"CANCELLED"}
        inst = st.instances[idx]
        cam = refs.safe_object(inst.camera_ref)
        if not refs.is_camera_object(cam):
            self.report({"ERROR"}, "Active Instance にカメラがありません")
            return {"CANCELLED"}

        base_dir = _normalize_dir(scene.render.filepath)
        items = [(base_dir + inst.name + os.sep, cam, inst.name)]

        if _kickoff_queue(scene, items):
            self.report({"INFO"}, f"Queued {inst.name}")
            return {"FINISHED"}
        self.report({"ERROR"}, "キューの起動に失敗")
        return {"CANCELLED"}


class KINEMA_OT_cancel_render_queue(KinemaOperator):
    """進行中の kinema レンダーキューを破棄する（次の Instance に進まない）。

    現在レンダリング中の Frame は完了させてから止めるかは Blender 側の挙動次第。
    """
    bl_idname = "kinema.cancel_render_queue"
    bl_label = "Cancel Render Queue"
    bl_description = "kinema レンダーキューを中断（現フレームは完了次第停止）"

    def run(self, context):
        if not _render_active:
            self.report({"INFO"}, "キューは実行されていません")
            return {"CANCELLED"}
        _render_queue.clear()
        self.report({"INFO"}, "キューを空にしました。現フレームの完了で停止します")
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# 公開ヘルパ（UI から状態を見るため）
# ---------------------------------------------------------------------------

def is_queue_active() -> bool:
    return _render_active


def queue_size() -> int:
    return len(_render_queue)
