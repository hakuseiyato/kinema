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


def _apply_roll(cam_obj, roll_deg: float) -> None:
    """Y 軸回転（ロール = 視線軸まわりの傾き）をカメラに適用する。

    Track To 制約がカメラの向きを完全に支配している場合、`rotation_euler` への
    書込みは上書きされて効かない。そのため Track To が無効 / 非存在の時のみ
    `cam.rotation_euler[2]` を書込んでロールを与える。
    Track To が有る場合の roll 実装は LookAt 経路の見直しと合わせて将来対応。
    """
    if cam_obj is None:
        return
    has_active_track_to = any(
        c.type == "TRACK_TO" and c.influence > 0.001 for c in cam_obj.constraints
    )
    if has_active_track_to:
        # Track To が効いている → roll は上書きされるのでスキップ
        return
    try:
        cam_obj.rotation_euler[2] = math.radians(roll_deg)
    except Exception:
        pass


def _apply_instances(scene) -> None:
    """Instance に対して Follow/LookAt/Noise を 1 ステップ適用。"""
    st = getattr(scene, "kinema", None)
    if st is None:
        return
    dt = follow_lookat.compute_dt(scene)
    frame = scene.frame_current
    for inst in st.instances:
        if not inst.enabled:
            continue
        cam = refs.safe_object(inst.camera_ref)
        if not refs.is_camera_object(cam):
            continue
        if refs.safe_object(inst.follow_target):
            follow_lookat.update_follow(cam, inst, dt)
        # LookAt は明示指定 > Follow Target 自動採用
        effective_lookat = _resolve_lookat_target(inst)
        if effective_lookat is not None:
            follow_lookat.update_lookat_with_target(cam, effective_lookat, inst.lookat_damping, dt)
        else:
            # 何も注視するものがない → 既存の Proxy を掃除
            follow_lookat.cleanup_lookat_proxy(cam)
        # Y 軸回転 (ロール) を最後に適用（Track To 後のカメラ視線軸を回す）
        roll_deg = float(getattr(inst, "follow_rot_y", 0.0))
        if abs(roll_deg) > 0.001:
            _apply_roll(cam, roll_deg)
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
