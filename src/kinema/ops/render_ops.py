"""バッチレンダー Operator（シンプル handler chain 方式）。

設計方針 (2026-05 再々改定):
  - **modal Operator を使わない**。modal-in-modal だと Blender 標準の render
    モーダルが衝突して 0% で固まる事象を起こした
  - **`bpy.ops.render.render('INVOKE_DEFAULT', animation=True)` を直接呼出**
    する。Blender の標準 render UI が開き、進行表示も正しく出る
  - **複数 item は `render_complete` handler で chain**:
      1. Operator が item 0 を設定 → INVOKE_DEFAULT で render 起動 → 即終了
      2. Blender が render を実行（標準モーダル）
      3. 完了 → `render_complete` handler 発火 → timer で次 item を起動
      4. 全 item 終わるまで繰り返し
  - **Object 参照は必ず name (str) で保持**（過去の stale pointer crash 対策）
  - **render 中の scene 構造変更は禁止**（過去の depsgraph rebuild crash 対策、
    cleanup_lookat_proxy / _ensure_lookat_proxy / _apply_dof_focus に guard 済み）
"""

from __future__ import annotations

import os

import bpy
from bpy.app.handlers import persistent

from ..utils import refs
from ._base import KinemaOperator


# ---------------------------------------------------------------------------
# Chain 状態（render_complete handler で next item を起動）
# ---------------------------------------------------------------------------

_chain_queue: list = []
_chain_scene_name: str = ""
_chain_active: bool = False
_chain_saved: dict = {}


def is_queue_active() -> bool:
    return _chain_active


def queue_size() -> int:
    return len(_chain_queue)


# ---------------------------------------------------------------------------
# 拡張子 / フォーマット解決
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
    "MPEG1": ".mpg", "MPEG2": ".dvd", "MPEG4": ".mp4",
    "AVI": ".avi", "QUICKTIME": ".mov", "DV": ".dv",
    "OGG": ".ogv", "MKV": ".mkv", "FLASH": ".flv", "WEBM": ".webm",
}


def _resolve_format_label(scene) -> tuple[str, bool]:
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
    ext = _resolve_extension(scene)
    _label, is_movie = _resolve_format_label(scene)
    fs = scene.frame_start
    fe = scene.frame_end
    sub = base_dir + inst_name + os.sep
    if is_movie:
        return f"{sub}{fs:04d}-{fe:04d}{ext}"
    return f"{sub}{fs:04d}{ext}  ...  {fe:04d}{ext}"


# ---------------------------------------------------------------------------
# Handler chain
# ---------------------------------------------------------------------------

def _normalize_item(item) -> tuple | None:
    """camera は必ず name (str) で保持、validate して返す。"""
    try:
        if len(item) == 5:
            sub_dir, cam, label, fs, fe = item
        else:
            sub_dir, cam, label = item
            fs, fe = None, None
        cam_name = cam if isinstance(cam, str) else getattr(cam, "name", "")
        if not cam_name:
            return None
        return (sub_dir, cam_name, label, fs, fe)
    except Exception:
        return None


def _setup_scene_for_item(scene, item) -> bool:
    """item の設定を scene に書き込む。失敗時は False を返して skip 推奨。"""
    sub_dir, cam_name, label, fs, fe = item
    camera = bpy.data.objects.get(cam_name)
    if camera is None or camera.type != "CAMERA":
        print(f"[kinema:render] skip '{label}': camera '{cam_name}' missing")
        return False
    try:
        scene.render.filepath = sub_dir
        scene.camera = camera
        if fs is not None and fe is not None:
            scene.frame_start = int(fs)
            scene.frame_end = int(fe)
        if fs is not None:
            print(f"[kinema:render] item: {label}  F{fs}-{fe}  →  {sub_dir}")
        else:
            print(f"[kinema:render] item: {label}  →  {sub_dir}")
        return True
    except Exception as exc:
        print(f"[kinema:render] setup error '{label}': {exc}")
        return False


def _trigger_render():
    """timer から呼ばれて INVOKE_DEFAULT で render を起動。"""
    if not _chain_active:
        return None
    print("[kinema:render] invoking render...")
    try:
        bpy.ops.render.render("INVOKE_DEFAULT", animation=True)
    except Exception as exc:
        print(f"[kinema:render] invoke failed: {exc}")
        _chain_finalize("invoke error")
    return None  # timer 1 度きり


@persistent
def _chain_on_render_complete(*args):
    """1 item 完了 → 次の item を準備して起動。"""
    if not _chain_active:
        return
    if not _chain_queue:
        print("[kinema:render] chain complete (all items rendered)")
        _chain_finalize("complete")
        return
    # 次 item を設定して timer で起動（depsgraph が落ち着くまで 0.5s 待つ）
    scene = bpy.data.scenes.get(_chain_scene_name)
    if scene is None:
        print(f"[kinema:render] scene '{_chain_scene_name}' missing during chain")
        _chain_finalize("scene missing")
        return
    while _chain_queue:
        item = _chain_queue.pop(0)
        if _setup_scene_for_item(scene, item):
            bpy.app.timers.register(_trigger_render, first_interval=0.5)
            return
    # 全部 skip された
    _chain_finalize("all items skipped")


@persistent
def _chain_on_render_cancel(*args):
    """Esc 等でキャンセル → chain 中断。"""
    if not _chain_active:
        return
    print("[kinema:render] cancelled by user")
    _chain_queue.clear()
    _chain_finalize("cancel")


def _chain_register_handlers():
    for hooks, fn in (
        (bpy.app.handlers.render_complete, _chain_on_render_complete),
        (bpy.app.handlers.render_cancel, _chain_on_render_cancel),
    ):
        if fn not in hooks:
            hooks.append(fn)


def _chain_unregister_handlers():
    for hooks, fn in (
        (bpy.app.handlers.render_complete, _chain_on_render_complete),
        (bpy.app.handlers.render_cancel, _chain_on_render_cancel),
    ):
        try:
            if fn in hooks:
                hooks.remove(fn)
        except Exception:
            pass


def _chain_save_scene_state(scene):
    _chain_saved.clear()
    _chain_saved["filepath"] = scene.render.filepath
    _chain_saved["camera_name"] = scene.camera.name if scene.camera is not None else ""
    _chain_saved["frame_start"] = scene.frame_start
    _chain_saved["frame_end"] = scene.frame_end


def _chain_restore_scene_state():
    scene = bpy.data.scenes.get(_chain_scene_name)
    if scene is None or not _chain_saved:
        return
    try:
        scene.render.filepath = _chain_saved.get("filepath", scene.render.filepath)
        cam_name = _chain_saved.get("camera_name", "")
        if cam_name:
            cam = bpy.data.objects.get(cam_name)
            if cam is not None and cam.type == "CAMERA":
                scene.camera = cam
        scene.frame_start = _chain_saved.get("frame_start", scene.frame_start)
        scene.frame_end = _chain_saved.get("frame_end", scene.frame_end)
    except Exception:
        pass
    _chain_saved.clear()


def _chain_finalize(reason: str):
    """chain 終了処理。"""
    global _chain_active, _chain_scene_name
    print(f"[kinema:render] finalize ({reason})")
    _chain_restore_scene_state()
    _chain_unregister_handlers()
    _chain_queue.clear()
    _chain_active = False
    _chain_scene_name = ""
    try:
        from ..runtime import instance_dispatcher as _id
        _id.set_rendering(False)
    except Exception:
        pass


def schedule_render(scene, items) -> int:
    """items を chain queue に積んで先頭から render 起動。

    Returns: 起動した item 数（残りは render_complete で chain される）。
    """
    global _chain_active, _chain_scene_name
    if _chain_active:
        print(f"[kinema:render] schedule rejected: already active")
        return 0
    if not items:
        return 0

    normalized = []
    for item in items:
        norm = _normalize_item(item)
        if norm is not None:
            normalized.append(norm)
    if not normalized:
        print("[kinema:render] all items invalid")
        return 0

    # 状態保存 + handler 登録
    _chain_save_scene_state(scene)
    _chain_register_handlers()
    _chain_scene_name = scene.name
    _chain_active = True

    # dispatcher にも render 中フラグを立てる
    try:
        from ..runtime import instance_dispatcher as _id
        _id.set_rendering(True)
    except Exception:
        pass

    # 最初の item を setup して timer で render 起動
    print(f"[kinema:render] chain start: {len(normalized)} item(s)")
    while normalized:
        item = normalized.pop(0)
        _chain_queue[:] = normalized  # 残りを queue へ
        if _setup_scene_for_item(scene, item):
            bpy.app.timers.register(_trigger_render, first_interval=0.1)
            return 1 + len(normalized)
        # setup 失敗 → 次へ
    # 全部失敗
    _chain_finalize("setup failure")
    return 0


# 互換 alias
def kickoff_queue_with_ranges(scene, items) -> bool:
    return schedule_render(scene, items) > 0


# ---------------------------------------------------------------------------
# 統一 Render Operator
# ---------------------------------------------------------------------------

def _build_items_from_shots(scene, shots) -> list:
    """shots[] から render queue items を構築する。

    Phase 2 で cut_ops._build_cut_queue_items から置き換え。
    items 形式: [(sub_dir, camera_name, label, frame_start, frame_end), ...]
    """
    from ..ops.shot_ops import _resolve_shot_frame_range, _sorted_markers
    st = scene.kinema
    sorted_ms = _sorted_markers(scene)
    base_dir = _normalize_dir(scene.render.filepath)
    items: list = []
    for shot in shots:
        if shot.orphan and not shot.frame_override:
            continue
        if not shot.instance_name:
            continue
        inst = next((i for i in st.instances if i.name == shot.instance_name), None)
        if inst is None:
            continue
        cam = refs.safe_object(inst.camera_ref)
        if not refs.is_camera_object(cam):
            continue
        fs, fe = _resolve_shot_frame_range(scene, shot, sorted_ms)
        sub = base_dir + shot.name + os.sep
        items.append((sub, cam.name, shot.name, fs, fe))
    return items


def _resolve_render_items(scene) -> tuple[list, str]:
    """`scene.kinema.render_source` / `render_mode` に従って items を組立。

    Phase 2: source=CUTS は **shots[]** を読む（旧 cuts[] は使わない）。
    UI 上のラベルは互換のため "Cut" を残す（次バージョンで "Shot" にリネーム予定）。
    """
    st = scene.kinema
    source = getattr(st, "render_source", "CUTS")
    mode = getattr(st, "render_mode", "ACTIVE")

    base_dir = _normalize_dir(scene.render.filepath)
    items: list = []

    if source == "INSTANCES":
        if mode == "ACTIVE":
            idx = st.active_instance_index
            pool = [st.instances[idx]] if 0 <= idx < len(st.instances) else []
        else:
            pool = [i for i in st.instances if i.enabled]
        for inst in pool:
            cam = refs.safe_object(inst.camera_ref)
            if not refs.is_camera_object(cam):
                continue
            sub = base_dir + inst.name + os.sep
            items.append((sub, cam.name, inst.name))
        label = f"Instance:{mode}"
    else:
        # CUTS = shots[] を読む（Phase 2）
        if mode == "ACTIVE":
            idx = st.active_shot_index
            shots = [st.shots[idx]] if 0 <= idx < len(st.shots) else []
        else:
            shots = [s for s in st.shots if s.enabled and not s.orphan]
        if shots:
            items = _build_items_from_shots(scene, shots)
        label = f"Shot:{mode}"

    return items, label


class KINEMA_OT_render(KinemaOperator):
    """統一 Render Operator。`scene.kinema.render_source` / `render_mode` を
    見て items を組立て、handler chain で順次レンダー。
    """
    bl_idname = "kinema.render"
    bl_label = "Render"
    bl_description = "Render Source / Mode に従って Blender 標準 render UI でレンダー"

    def run(self, context):
        if _chain_active:
            self.report({"WARNING"}, "既にレンダー中です (Esc で中断)")
            return {"CANCELLED"}
        scene = context.scene
        items, label = _resolve_render_items(scene)
        if not items:
            self.report({"WARNING"}, f"対象なし ({label})")
            return {"CANCELLED"}

        n = schedule_render(scene, items)
        if n > 0:
            self.report({"INFO"}, f"Started: {n} item(s) ({label})")
            return {"FINISHED"}
        self.report({"ERROR"}, "起動失敗 (System Console を確認)")
        return {"CANCELLED"}


# ---------------------------------------------------------------------------
# 旧 Operator は互換のため残置（kinema.render に統合済み）
# ---------------------------------------------------------------------------

class KINEMA_OT_render_selected_instances(KinemaOperator):
    bl_idname = "kinema.render_selected_instances"
    bl_label = "Render Selected Instances"
    bl_description = "enabled Instance を順にレンダー（互換用）"

    def run(self, context):
        scene = context.scene
        st = scene.kinema
        # render_source/mode を一時的に書き換えて kinema.render に委譲
        st.render_source = "INSTANCES"
        st.render_mode = "ENABLED"
        return bpy.ops.kinema.render()


class KINEMA_OT_render_active_instance(KinemaOperator):
    bl_idname = "kinema.render_active_instance"
    bl_label = "Render Active Instance"
    bl_description = "Active Instance だけレンダー（互換用）"

    def run(self, context):
        scene = context.scene
        st = scene.kinema
        st.render_source = "INSTANCES"
        st.render_mode = "ACTIVE"
        return bpy.ops.kinema.render()


class KINEMA_OT_cancel_render_queue(KinemaOperator):
    """進行中のレンダーキューを中断（Esc と等価）。"""
    bl_idname = "kinema.cancel_render_queue"
    bl_label = "Cancel Render Queue"
    bl_description = "進行中のレンダーキューをキャンセル"

    def run(self, context):
        if not _chain_active:
            self.report({"INFO"}, "キューは実行されていません")
            return {"CANCELLED"}
        _chain_queue.clear()
        self.report({"INFO"}, "キューを空にしました。現フレームの完了で停止します")
        return {"FINISHED"}
