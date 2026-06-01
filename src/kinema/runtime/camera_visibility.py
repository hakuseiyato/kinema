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


def _collect_kinema_managed_cameras(scene) -> set[str]:
    """kinema.instances[] が camera_ref で参照している全カメラ名集合。

    これが「kinema が管理対象とするカメラ」。非 kinema カメラ（手動配置 / 別
    アドオン管理 / 他用途のカメラ）は触らない（auto-hide の対象外）。
    """
    st = getattr(scene, "kinema", None)
    if st is None:
        return set()
    managed: set[str] = set()
    for inst in st.instances:
        try:
            cam = refs.safe_object(inst.camera_ref)
            if cam is not None and cam.type == "CAMERA":
                managed.add(cam.name)
        except Exception:
            continue
    return managed


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

    `auto_hide_unused_cameras` トグルの挙動:
      ON  → 使用してないカメラを hide
      OFF → **全 Camera を show（kinema が hide していたカメラを復元）**
    OFF にしたとき何もしないと「hide のまま戻せない」状態になるため、
    明示的に show する。
    """
    st = getattr(scene, "kinema", None)
    if st is None:
        return (0, 0)
    auto_hide_on = bool(getattr(st, "auto_hide_unused_cameras", False))

    # 対象は **kinema 管理下のカメラのみ**。手動配置 / 他用途のカメラは触らない
    managed_names = _collect_kinema_managed_cameras(scene)

    if not auto_hide_on:
        # OFF: 管理対象カメラを全て show 状態に戻す
        shown = 0
        for cam_name in managed_names:
            obj = bpy.data.objects.get(cam_name)
            if obj is None:
                continue
            try:
                if obj.hide_viewport:
                    obj.hide_viewport = False
                    shown += 1
            except Exception:
                continue
        if shown:
            print(f"[kinema:cam_vis] auto-hide OFF → restored {shown} kinema-managed cameras")
        return (0, shown)

    # ON: 使用してないカメラを hide（管理下のみ対象）
    used_names = _collect_used_camera_names(scene)
    hidden = 0
    shown = 0
    for cam_name in managed_names:
        obj = bpy.data.objects.get(cam_name)
        if obj is None:
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
    print(
        f"[kinema:cam_vis] auto-hide ON: {hidden} hidden, {shown} shown "
        f"(managed={len(managed_names)}, used={len(used_names)})"
    )
    return (hidden, shown)
