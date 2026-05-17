"""Instance dispatcher — frame_change / depsgraph_update_post から呼ばれ、
Instance に設定された Follow / LookAt / Noise を毎フレーム適用する。

旧 `shot_dispatcher` から Shot Clip 関連を取り除き、Instance ベースの追従だけに
責務を絞ったもの。Blender 標準の Timeline / VSE / Marker と組み合わせて運用する。
"""

from __future__ import annotations

import math
import time

from ..utils import refs
from . import follow_lookat, noise as noise_mod


# 再帰防止フラグ
_in_dispatch = False

# バースト抑制用: 直近の dispatch 時刻
_last_dispatch_time: dict[str, float] = {}

# バースト抑制閾値（秒）。240Hz 上限。
_BURST_MIN_INTERVAL = 1.0 / 240.0


def reset_state() -> None:
    """`.blend` 読込時に呼ぶ。"""
    global _in_dispatch
    _in_dispatch = False
    _last_dispatch_time.clear()
    follow_lookat.reset_frame_cache()


def _resolve_lookat_target(inst):
    """LookAt Target を決定。明示指定優先 / 未指定なら Follow Target を自動採用。

    follow_auto_lookat が True (デフォルト) なら、LookAt Target が空でも
    Follow Target を見るようにする。「変な方向を見る」事故防止。
    """
    explicit = refs.safe_object(inst.lookat_target)
    if explicit is not None:
        return explicit
    if getattr(inst, "follow_auto_lookat", True):
        return refs.safe_object(inst.follow_target)
    return None


def _apply_instances(scene) -> None:
    """Instance に対して Follow/LookAt/Noise を 1 ステップ適用。

    Roll (follow_rot_y) は:
      - LookAt が active → update_lookat_with_target に roll を渡して
        rotation 計算の最終段で local Z 軸回転として加える
      - LookAt が無い → cam.rotation_euler[2] に直接書込
    """
    st = getattr(scene, "kinema", None)
    if st is None:
        return
    dt = follow_lookat.compute_dt(scene)
    frame = scene.frame_current

    # Solo: solo フラグの立った Instance があればそれだけ評価
    solo_set = [i for i in st.instances if getattr(i, "solo", False)]
    pool = solo_set if solo_set else list(st.instances)

    for inst in pool:
        if not inst.enabled:
            continue
        cam = refs.safe_object(inst.camera_ref)
        if not refs.is_camera_object(cam):
            continue
        if refs.safe_object(inst.follow_target):
            follow_lookat.update_follow(cam, inst, dt)
        # LookAt は明示指定 > Follow Target 自動採用
        effective_lookat = _resolve_lookat_target(inst)
        roll_deg = float(getattr(inst, "follow_rot_y", 0.0))
        if effective_lookat is not None:
            follow_lookat.update_lookat_with_target(
                cam, effective_lookat, inst.lookat_damping, dt, roll_deg=roll_deg,
            )
        else:
            # 何も注視するものがない → 既存の Proxy を掃除
            follow_lookat.cleanup_lookat_proxy(cam)
            # LookAt 無し時の Roll: rotation_euler に直接書く
            if abs(roll_deg) > 0.001:
                try:
                    cam.rotation_euler[2] = math.radians(roll_deg)
                except Exception:
                    pass
        if inst.noise_enabled:
            noise_mod.apply_noise_frame(cam, inst, frame)


def dispatch(scene, force: bool = False) -> None:
    """frame_change_pre / depsgraph_update_post / update callback のエントリ。

    force=False 時はバースト抑制（240Hz 上限）を効かせる。
    """
    global _in_dispatch
    if _in_dispatch:
        return
    if not hasattr(scene, "kinema"):
        return

    if not force:
        now = time.monotonic()
        last = _last_dispatch_time.get(scene.name, 0.0)
        if now - last < _BURST_MIN_INTERVAL:
            return
        _last_dispatch_time[scene.name] = now
    else:
        _last_dispatch_time[scene.name] = time.monotonic()

    _in_dispatch = True
    try:
        _apply_instances(scene)
    finally:
        _in_dispatch = False
