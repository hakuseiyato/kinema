"""バッチレンダー Operator（同期型・安定優先）。

設計方針 (2026-05 改定):
  - **同期 1 件ずつレンダー**。timer + INVOKE_DEFAULT 方式は Blender 内部の
    depsgraph rebuild と render thread の競合で NULL deref クラッシュを
    起こしたため廃止
  - 各レンダーは `bpy.ops.render.render(write_still=False, animation=True)`
    を直接呼ぶ。Blender はモーダルウィンドウを開かず、内部 progress bar
    で進行する。UI はブロックされるがクラッシュは回避できる
  - クラッシュリスクを最小化するため、Object 参照は name で保持し、
    使う直前に bpy.data.objects.get() で解決する

出力ファイル名は Blender の `scene.render.file_extension` に従う:
  - PNG / JPEG / EXR 等の静止画: `<base>/<inst_name>/####.<ext>` (連番)
  - FFMPEG / AVI 等の動画: `<base>/<inst_name>/####-####.<ext>` (範囲付き)
"""

from __future__ import annotations

import os

import bpy
from bpy.app.handlers import persistent

from ..utils import refs
from ._base import KinemaOperator


# ---------------------------------------------------------------------------
# 実行中フラグ（UI 状態表示用）
# ---------------------------------------------------------------------------

_render_active: bool = False


def is_queue_active() -> bool:
    # モーダル方式: _modal_state が IDLE 以外なら active 扱い
    return _modal_state != "IDLE" or _render_active


def queue_size() -> int:
    return len(_modal_queue)


# ---------------------------------------------------------------------------
# 拡張子 / フォーマット解決ヘルパ
# ---------------------------------------------------------------------------

def _normalize_dir(path: str) -> str:
    if not path:
        return path
    if path.endswith(("/", "\\", os.sep)):
        return path
    return path + os.sep


def _is_movie_format(file_format: str) -> bool:
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
    """(表示用 format ラベル, 動画フラグ) を返す。"""
    ims = scene.render.image_settings
    fmt = ims.file_format
    media_type = getattr(ims, "media_type", None)
    if media_type == "MOVIE":
        try:
            container = scene.render.ffmpeg.format
            return f"FFMPEG ({container})", True
        except Exception:
            return "FFMPEG", True
    return fmt, _is_movie_format(fmt)


def _resolve_extension(scene) -> str:
    """実際に出力されるファイル拡張子を返す。

    `scene.render.frame_path(frame=N)` が最も信頼できる API（Blender 自身が
    決めた拡張子を返す）。フォールバックとして ffmpeg コンテナマップ。
    """
    r = scene.render
    try:
        sample_path = r.frame_path(frame=scene.frame_start)
        ext = os.path.splitext(sample_path)[1]
        if ext:
            return ext
    except Exception:
        pass

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

    return r.file_extension or ""


def _sample_output_path(scene, base_dir: str, inst_name: str) -> str:
    """UI 表示用のサンプル出力パス。"""
    ext = _resolve_extension(scene)
    _label, is_movie = _resolve_format_label(scene)
    fs = scene.frame_start
    fe = scene.frame_end
    sub = base_dir + inst_name + os.sep
    if is_movie:
        return f"{sub}{fs:04d}-{fe:04d}{ext}"
    return f"{sub}{fs:04d}{ext}  ...  {fe:04d}{ext}"


# ---------------------------------------------------------------------------
# 同期レンダー実行ヘルパ
# ---------------------------------------------------------------------------

def _render_one_item(scene, sub_dir: str, camera_name: str, label: str,
                     fs=None, fe=None) -> tuple[bool, str]:
    """1 item を同期レンダーする。

    Returns (success, message)。例外を投げず Boolean で返す。
    """
    camera = bpy.data.objects.get(camera_name) if camera_name else None
    if camera is None or getattr(camera, "type", None) != "CAMERA":
        return False, f"skip '{label}': camera '{camera_name}' missing"
    try:
        scene.render.filepath = sub_dir
        scene.camera = camera
        if fs is not None and fe is not None:
            scene.frame_start = int(fs)
            scene.frame_end = int(fe)
        print(f"[kinema:render] rendering: {label}  →  {sub_dir}")
        bpy.ops.render.render(animation=True)
        return True, f"done: {label}"
    except Exception as exc:
        return False, f"error '{label}': {exc}"


def run_render_queue(scene, items) -> dict:
    """items を順次同期レンダーする。

    items 各要素: 3-tuple `(sub_dir, camera_name_or_obj, label)` または
                 5-tuple `(sub_dir, camera_name_or_obj, label, fs, fe)`

    呼出側 Operator から使う公開エントリ。元の filepath / camera /
    frame range を try/finally で復元する。

    Returns: {"rendered": N, "skipped": M, "errors": [...]}
    """
    global _render_active
    if _render_active:
        return {"rendered": 0, "skipped": 0, "errors": ["already rendering"]}
    if not items:
        return {"rendered": 0, "skipped": 0, "errors": ["no items"]}

    # 状態保存（camera は name で）
    saved_filepath = scene.render.filepath
    saved_cam_name = scene.camera.name if scene.camera is not None else ""
    saved_fs = scene.frame_start
    saved_fe = scene.frame_end

    _render_active = True
    # dispatcher にも render 中と伝える（depsgraph_update_post 抑制）
    try:
        from ..runtime import instance_dispatcher as _id
        _id.set_rendering(True)
    except Exception:
        pass

    rendered = 0
    skipped = 0
    errors: list[str] = []

    try:
        for item in items:
            try:
                if len(item) == 5:
                    sub_dir, cam, label, fs, fe = item
                else:
                    sub_dir, cam, label = item
                    fs, fe = None, None
                cam_name = cam if isinstance(cam, str) else getattr(cam, "name", "")
            except Exception as exc:
                errors.append(f"malformed item: {exc}")
                skipped += 1
                continue

            ok, msg = _render_one_item(scene, sub_dir, cam_name, label, fs, fe)
            if ok:
                rendered += 1
            else:
                skipped += 1
                errors.append(msg)
                print(f"[kinema:render] {msg}")
    finally:
        # 復元
        try:
            scene.render.filepath = saved_filepath
            if saved_cam_name:
                cam = bpy.data.objects.get(saved_cam_name)
                if cam is not None and cam.type == "CAMERA":
                    scene.camera = cam
            scene.frame_start = saved_fs
            scene.frame_end = saved_fe
        except Exception:
            pass
        _render_active = False
        try:
            from ..runtime import instance_dispatcher as _id
            _id.set_rendering(False)
        except Exception:
            pass

    return {"rendered": rendered, "skipped": skipped, "errors": errors}


# 旧 API 互換: cut_ops から `kickoff_queue_with_ranges` を呼んでいる
def kickoff_queue_with_ranges(scene, items) -> bool:
    """旧 async API の互換ラッパ。今は同期実行する。"""
    result = run_render_queue(scene, items)
    return result["rendered"] > 0


# ---------------------------------------------------------------------------
# モーダル方式のバッチレンダー（Blender 標準の render ウィンドウを開く）
# ---------------------------------------------------------------------------
#
# 設計:
#   - kinema.render が items を _modal_queue に積み、kinema.render_modal を
#     INVOKE_DEFAULT で起動
#   - kinema.render_modal が timer (0.5s) で modal ループし、_modal_state を
#     見て次の render を INVOKE_DEFAULT で起動
#   - 各 render 完了時に Blender の render_complete handler が _modal_state
#     を IDLE に戻す → 次の timer tick で次の item へ
#   - キュー枯渇 / Esc / cancel で modal を終了し、scene state を復元
#
# 安定化のポイント:
#   - items は事前に厳密にバリデート（camera 存在チェック）
#   - 各 render 起動前に scene を更新するが、INVOKE_DEFAULT は async なので
#     ネスト context の問題を回避できる
#   - 各 render 間に 0.5s 以上の余白があるので depsgraph が落ち着く時間がある

_modal_queue: list = []
_modal_state: str = "IDLE"   # IDLE | RENDERING | DONE | ABORT
_modal_scene_name: str = ""
_modal_saved: dict = {}
_modal_current_label: str = ""


def _modal_resolve_scene():
    return bpy.data.scenes.get(_modal_scene_name)


def _modal_validate_item(item) -> tuple | None:
    """item を name 形式に正規化し、camera 存在を検証。失敗なら None。"""
    try:
        if len(item) == 5:
            sub_dir, cam, label, fs, fe = item
        else:
            sub_dir, cam, label = item
            fs, fe = None, None
        cam_name = cam if isinstance(cam, str) else getattr(cam, "name", "")
        if not cam_name:
            return None
        camera = bpy.data.objects.get(cam_name)
        if camera is None or getattr(camera, "type", None) != "CAMERA":
            return None
        return (sub_dir, cam_name, label, fs, fe)
    except Exception:
        return None


@persistent
def _modal_on_render_complete(*args):
    """render 1 件完了 → modal を IDLE に戻す。modal timer が次を起動する。"""
    global _modal_state
    if _modal_state == "RENDERING":
        print(f"[kinema:render] item complete: {_modal_current_label}")
        _modal_state = "IDLE"


@persistent
def _modal_on_render_cancel(*args):
    """Esc 等でキャンセル → キュー破棄"""
    global _modal_state
    if _modal_state == "RENDERING":
        print("[kinema:render] cancel detected, aborting queue")
        _modal_state = "ABORT"


def _modal_register_handlers():
    for hooks, fn in (
        (bpy.app.handlers.render_complete, _modal_on_render_complete),
        (bpy.app.handlers.render_cancel, _modal_on_render_cancel),
    ):
        if fn not in hooks:
            hooks.append(fn)


def _modal_unregister_handlers():
    for hooks, fn in (
        (bpy.app.handlers.render_complete, _modal_on_render_complete),
        (bpy.app.handlers.render_cancel, _modal_on_render_cancel),
    ):
        try:
            if fn in hooks:
                hooks.remove(fn)
        except Exception:
            pass


def _modal_save_scene_state(scene):
    _modal_saved.clear()
    _modal_saved["filepath"] = scene.render.filepath
    _modal_saved["camera_name"] = scene.camera.name if scene.camera is not None else ""
    _modal_saved["frame_start"] = scene.frame_start
    _modal_saved["frame_end"] = scene.frame_end


def _modal_restore_scene_state(scene):
    if not _modal_saved or scene is None:
        return
    try:
        scene.render.filepath = _modal_saved.get("filepath", scene.render.filepath)
        cam_name = _modal_saved.get("camera_name", "")
        if cam_name:
            cam = bpy.data.objects.get(cam_name)
            if cam is not None and cam.type == "CAMERA":
                scene.camera = cam
        scene.frame_start = _modal_saved.get("frame_start", scene.frame_start)
        scene.frame_end = _modal_saved.get("frame_end", scene.frame_end)
    except Exception:
        pass
    _modal_saved.clear()


def _modal_start_item(scene, item) -> bool:
    """次の item の render を INVOKE_DEFAULT で起動。"""
    global _modal_state, _modal_current_label
    sub_dir, cam_name, label, fs, fe = item
    camera = bpy.data.objects.get(cam_name)
    if camera is None or camera.type != "CAMERA":
        print(f"[kinema:render] skip '{label}': camera missing")
        return False
    try:
        scene.render.filepath = sub_dir
        scene.camera = camera
        if fs is not None and fe is not None:
            scene.frame_start = int(fs)
            scene.frame_end = int(fe)
        _modal_current_label = label
        _modal_state = "RENDERING"
        if fs is not None:
            print(f"[kinema:render] starting: {label}  F{fs}-{fe}  →  {sub_dir}")
        else:
            print(f"[kinema:render] starting: {label}  →  {sub_dir}")
        bpy.ops.render.render("INVOKE_DEFAULT", animation=True)
        return True
    except Exception as exc:
        print(f"[kinema:render] error starting '{label}': {exc}")
        _modal_state = "IDLE"
        return False


def schedule_render(scene, items) -> int:
    """items を modal queue に積んで kinema.render_modal を invoke する。"""
    global _modal_queue, _modal_state, _modal_scene_name
    if _modal_state != "IDLE" and _modal_state != "DONE":
        print(f"[kinema:render] schedule rejected: state={_modal_state}")
        return 0
    if not items:
        return 0

    # 全 item をバリデート
    normalized = []
    for item in items:
        norm = _modal_validate_item(item)
        if norm is not None:
            normalized.append(norm)
    if not normalized:
        print("[kinema:render] all items invalid")
        return 0

    _modal_queue[:] = normalized
    _modal_scene_name = scene.name
    _modal_save_scene_state(scene)
    _modal_register_handlers()

    # dispatcher にも render 中と伝える
    try:
        from ..runtime import instance_dispatcher as _id
        _id.set_rendering(True)
    except Exception:
        pass

    # modal Operator を起動
    print(f"[kinema:render] starting modal queue: {len(normalized)} item(s)")
    try:
        bpy.ops.kinema.render_modal("INVOKE_DEFAULT")
    except Exception as exc:
        print(f"[kinema:render] failed to invoke modal: {exc}")
        _modal_queue.clear()
        _modal_unregister_handlers()
        return 0
    return len(normalized)


# ---------------------------------------------------------------------------
# 統一 Render Operator（単一ボタン）
# ---------------------------------------------------------------------------

def _resolve_render_items(scene) -> tuple[list, str]:
    """`scene.kinema.render_source` / `render_mode` に従って items を構築。

    Returns (items, label)。label は UI / report 用。
    """
    st = scene.kinema
    source = getattr(st, "render_source", "CUTS")
    mode = getattr(st, "render_mode", "ACTIVE")

    base_dir = _normalize_dir(scene.render.filepath)
    items: list = []
    label = ""

    if source == "INSTANCES":
        # Instance ベース
        if mode == "ACTIVE":
            idx = st.active_instance_index
            pool = [st.instances[idx]] if 0 <= idx < len(st.instances) else []
        else:  # ENABLED
            pool = [i for i in st.instances if i.enabled]
        for inst in pool:
            cam = refs.safe_object(inst.camera_ref)
            if not refs.is_camera_object(cam):
                continue
            sub = base_dir + inst.name + os.sep
            items.append((sub, cam.name, inst.name))
        label = f"Instance:{mode}"
    else:
        # Cut ベース（cut_ops の helper を再利用）
        from . import cut_ops as _cut_ops
        if mode == "ACTIVE":
            idx = st.active_cut_index
            cuts = [st.cuts[idx]] if 0 <= idx < len(st.cuts) else []
        else:  # ENABLED
            cuts = [c for c in st.cuts if c.enabled and not c.orphan]
        if cuts:
            items, _skipped = _cut_ops._build_cut_queue_items(scene, cuts)
        label = f"Cut:{mode}"

    return items, label


class KINEMA_OT_render(KinemaOperator):
    """統一 Render Operator。`scene.kinema.render_source` と `render_mode` を見て
    実際の対象を決定して同期レンダーする。

    Single-button 設計の中心。UI 側で source / mode をトグルしておけば、
    Render ボタンは 1 つで全パターンを実行できる。
    """
    bl_idname = "kinema.render"
    bl_label = "Render"
    bl_description = "Render Source / Mode の設定に従って同期レンダーを実行"

    def run(self, context):
        scene = context.scene
        items, label = _resolve_render_items(scene)
        if not items:
            self.report({"WARNING"}, f"対象なし ({label})")
            return {"CANCELLED"}
        if _modal_state not in ("IDLE", "DONE"):
            self.report({"WARNING"}, f"既にレンダリング中です ({_modal_state})")
            return {"CANCELLED"}

        n = schedule_render(scene, items)
        if n > 0:
            self.report({"INFO"}, f"Started: {n} item(s) ({label})")
            return {"FINISHED"}
        self.report({"ERROR"}, "起動失敗（System Console にログ）")
        return {"CANCELLED"}


class KINEMA_OT_render_modal(bpy.types.Operator):
    """バッチレンダーのモーダル進行制御。

    `schedule_render()` が `_modal_queue` を埋めて INVOKE_DEFAULT で起動する。
    timer (0.5s) で modal ループし、`_modal_state` を見て:
      - IDLE: 次の item を INVOKE_DEFAULT で render 起動 → state=RENDERING
      - RENDERING: 何もしない（Blender の render_complete handler が IDLE に戻す）
      - DONE / ABORT: cleanup して終了

    UNDO は付けない（モーダル中の undo は壊れる）。
    """
    bl_idname = "kinema.render_modal"
    bl_label = "Render Modal Queue"
    bl_options = {"INTERNAL"}

    _timer = None

    def invoke(self, context, event):  # noqa: ARG002
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.5, window=context.window)
        wm.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        global _modal_state
        if event.type == "ESC":
            print("[kinema:render] modal: Esc pressed, aborting")
            return self._cleanup(context, "user cancelled")
        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        # 状態遷移
        if _modal_state == "ABORT":
            return self._cleanup(context, "abort")
        if _modal_state == "RENDERING":
            return {"PASS_THROUGH"}
        if _modal_state == "IDLE":
            if not _modal_queue:
                return self._cleanup(context, "complete")
            scene = _modal_resolve_scene()
            if scene is None:
                print("[kinema:render] modal: scene gone, abort")
                return self._cleanup(context, "scene missing")
            item = _modal_queue.pop(0)
            ok = _modal_start_item(scene, item)
            if not ok:
                # 起動失敗 → 次へ
                return {"PASS_THROUGH"}
            return {"PASS_THROUGH"}
        return {"PASS_THROUGH"}

    def _cleanup(self, context, reason: str):
        global _modal_state, _modal_queue
        wm = context.window_manager
        if self._timer is not None:
            try:
                wm.event_timer_remove(self._timer)
            except Exception:
                pass
            self._timer = None
        _modal_queue.clear()
        _modal_state = "IDLE"
        _modal_unregister_handlers()
        try:
            from ..runtime import instance_dispatcher as _id
            _id.set_rendering(False)
        except Exception:
            pass
        scene = _modal_resolve_scene()
        _modal_restore_scene_state(scene)
        print(f"[kinema:render] modal cleanup: {reason}")
        return {"FINISHED" if reason == "complete" else "CANCELLED"}


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

class KINEMA_OT_render_selected_instances(KinemaOperator):
    """`enabled` チェックが入った Instance を同期バッチレンダー。"""
    bl_idname = "kinema.render_selected_instances"
    bl_label = "Render Selected Instances"
    bl_description = (
        "enabled が ON の Instance を順に <base>/<instance_name>/ サブフォルダへ "
        "同期レンダー（Blender はレンダー中ブロックされます）"
    )

    def invoke(self, context, event):  # noqa: ARG002
        return context.window_manager.invoke_props_dialog(self, width=560)

    def draw(self, context):
        layout = self.layout
        try:
            scene = context.scene
            st = scene.kinema
            targets = [i for i in st.instances if i.enabled]
            layout.label(text="Render Selected Instances", icon="RENDER_ANIMATION")
            layout.separator()
            if not targets:
                layout.label(text="enabled な Instance がありません", icon="ERROR")
                return

            ext = _resolve_extension(scene) or "(none)"
            fmt, _ = _resolve_format_label(scene)
            base_dir = _normalize_dir(bpy.path.abspath(scene.render.filepath))

            box = layout.box()
            box.label(text="出力設定", icon="OUTPUT")
            box.label(text=f"Base: {scene.render.filepath}")
            box.label(text=f"Format: {fmt}   Extension: {ext}")
            box.label(
                text=f"Frame range: F{scene.frame_start} – {scene.frame_end} "
                     f"({scene.frame_end - scene.frame_start + 1} frames)",
            )

            layout.separator()
            layout.label(text=f"対象 {len(targets)} Instance:")
            col = layout.column(align=True)
            col.scale_y = 0.85
            for inst in targets[:10]:
                cam = refs.safe_object(inst.camera_ref)
                cam_name = cam.name if cam is not None else "(no cam)"
                sample = _sample_output_path(scene, base_dir, inst.name)
                col.label(text=f"  [{cam_name}]  ->  {sample}")
            if len(targets) > 10:
                col.label(text=f"  ... and {len(targets) - 10} more")
            layout.separator()
            warn = layout.row()
            warn.alert = True
            warn.label(text="同期レンダー: 終了まで Blender はブロックされます",
                       icon="INFO")
        except Exception as exc:
            layout.label(text=f"描画エラー: {exc}", icon="ERROR")

    def run(self, context):
        scene = context.scene
        st = scene.kinema

        targets = [i for i in st.instances if i.enabled]
        if not targets:
            self.report({"WARNING"}, "enabled な Instance がありません")
            return {"CANCELLED"}

        base_dir = _normalize_dir(scene.render.filepath)
        items: list = []
        for inst in targets:
            cam = refs.safe_object(inst.camera_ref)
            if not refs.is_camera_object(cam):
                continue
            sub = base_dir + inst.name + os.sep
            # camera は name で渡す（stale ポインタ回避）
            items.append((sub, cam.name, inst.name))

        if not items:
            self.report({"WARNING"}, "有効なカメラを持つ Instance がありません")
            return {"CANCELLED"}

        n = schedule_render(scene, items)
        if n > 0:
            self.report({"INFO"}, f"Started: {n} instances")
            return {"FINISHED"}
        self.report({"ERROR"}, "起動失敗")
        return {"CANCELLED"}


class KINEMA_OT_render_active_instance(KinemaOperator):
    """Active Instance を 1 件だけ同期レンダー。"""
    bl_idname = "kinema.render_active_instance"
    bl_label = "Render Active Instance"
    bl_description = (
        "Active Instance のカメラを <base>/<inst_name>/ に同期レンダー"
    )

    def invoke(self, context, event):  # noqa: ARG002
        return context.window_manager.invoke_props_dialog(self, width=480)

    def draw(self, context):
        layout = self.layout
        try:
            scene = context.scene
            st = scene.kinema
            layout.label(text="Render Active Instance", icon="RENDER_ANIMATION")
            layout.separator()
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
            fmt, _ = _resolve_format_label(scene)
            base_dir = _normalize_dir(bpy.path.abspath(scene.render.filepath))
            sample = _sample_output_path(scene, base_dir, inst.name)

            box = layout.box()
            box.label(text="出力設定", icon="OUTPUT")
            box.label(text=f"Format: {fmt}   Extension: {ext}")
            box.label(text=f"Frame range: F{scene.frame_start} – {scene.frame_end}")
            box.label(text=f"対象: [{cam.name}]")
            box.label(text=f"出力: {sample}")
            warn = layout.row()
            warn.alert = True
            warn.label(text="同期レンダー: 終了まで Blender はブロック",
                       icon="INFO")
        except Exception as exc:
            layout.label(text=f"描画エラー: {exc}", icon="ERROR")

    def run(self, context):
        scene = context.scene
        st = scene.kinema

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
        items = [(base_dir + inst.name + os.sep, cam.name, inst.name)]

        n = schedule_render(scene, items)
        if n > 0:
            self.report({"INFO"}, f"Started: {inst.name}")
            return {"FINISHED"}
        self.report({"ERROR"}, "起動失敗")
        return {"CANCELLED"}


class KINEMA_OT_cancel_render_queue(KinemaOperator):
    """互換用 stub。同期実行に切り替えたので意味は無い。"""
    bl_idname = "kinema.cancel_render_queue"
    bl_label = "Cancel Render Queue"
    bl_description = "（同期実行に変更。レンダー中の中断は Blender 標準 Esc を使用）"

    def run(self, context):
        self.report({"INFO"}, "同期レンダーは Esc で中断してください")
        return {"FINISHED"}
