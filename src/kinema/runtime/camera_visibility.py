"""Timeline で使用されていないカメラを自動非表示にするモジュール。

設計:
  - `scene.kinema.shots[]` で参照されている Instance のカメラを「使用中」とする
  - それ以外の Camera Object は `hide_viewport=True` にする
  - shots[] 変更時 / Instance 変更時 / .blend 読込時に再評価
  - リアルタイム = 明示的に呼ぶ（毎フレーム ではコストが高いので避ける）

トグル:
  - `scene.kinema.auto_hide_unused_cameras` で ON/OFF
  - OFF のときは何もしない（ユーザーが手動管理）
"""

from __future__ import annotations

import bpy

from ..utils import refs


def _collect_used_camera_names(scene) -> set[str]:
    """shots[] が参照する全 Instance の camera_ref から「使用中」カメラ名を集める。"""
    st = getattr(scene, "kinema", None)
    if st is None:
        return set()
    used: set[str] = set()
    # Instance → Camera name の索引を 1 回作って高速化
    inst_to_cam: dict[str, str] = {}
    for inst in st.instances:
        try:
            cam = refs.safe_object(inst.camera_ref)
            if cam is not None and cam.type == "CAMERA":
                inst_to_cam[inst.name] = cam.name
        except Exception:
            continue
    for shot in st.shots:
        try:
            inst_name = shot.instance_name
        except Exception:
            continue
        if not inst_name:
            continue
        cam_name = inst_to_cam.get(inst_name)
        if cam_name:
            used.add(cam_name)
    # 念のため `scene.camera`（現在アクティブ）も使用中扱い
    try:
        if scene.camera is not None and scene.camera.type == "CAMERA":
            used.add(scene.camera.name)
    except Exception:
        pass
    return used


def apply_camera_visibility(scene) -> tuple[int, int]:
    """使用していないカメラを hide_viewport=True にする。

    Returns: (hidden_count, shown_count) — 状態が変わったカメラ数。
    """
    st = getattr(scene, "kinema", None)
    if st is None:
        return (0, 0)
    if not getattr(st, "auto_hide_unused_cameras", False):
        return (0, 0)
    used_names = _collect_used_camera_names(scene)
    hidden = 0
    shown = 0
    for obj in bpy.data.objects:
        try:
            if obj.type != "CAMERA":
                continue
        except Exception:
            continue
        in_use = obj.name in used_names
        want_hidden = not in_use
        try:
            current_hidden = bool(obj.hide_viewport)
        except Exception:
            continue
        if want_hidden == current_hidden:
            continue
        try:
            obj.hide_viewport = want_hidden
            if want_hidden:
                hidden += 1
            else:
                shown += 1
        except Exception:
            pass
    return (hidden, shown)
