"""shot_dispatcher — frame_change_pre で Shot から scene.camera を切替える。

v2.0 では Shot がまだタイムラインから生成されない可能性があるため、
Shot が空の場合は Instance ベースの Follow/LookAt/Noise 適用にフォールバックする。
"""

from __future__ import annotations

import time
from bisect import bisect_right
from typing import Optional

import bpy

from ..utils import refs
from . import follow_lookat, noise as noise_mod


# 再帰防止フラグ
_in_dispatch = False

# 前フレーム同 Shot キャッシュ（scene.name -> shot uid）
_last_shot_per_scene: dict[str, str] = {}

# バースト抑制用: 直近の dispatch 時刻
_last_dispatch_time: dict[str, float] = {}

# バースト抑制閾値（秒）。これより短い間隔の連続呼び出しは skip し、
# 前回の damping 結果を保持する。スライダー連打などで dispatch が
# 秒間数百回呼ばれても安定して追従させる。
# 240Hz まで通す（4ms 間隔）→ 通常のディスプレイ更新より速いので、
# 視覚的なカクつきはほぼ起きない。
_BURST_MIN_INTERVAL = 1.0 / 240.0


def reset_state() -> None:
    """`.blend` 読込時に呼ぶ。"""
    global _in_dispatch
    _in_dispatch = False
    _last_shot_per_scene.clear()
    _last_dispatch_time.clear()
    follow_lookat.reset_frame_cache()


def _pick_active_shot(scene) -> Optional[object]:
    """全 Track を走査して、現在フレームでアクティブな Shot を返す。

    Track 評価ルール（プラン v7 docs/tracks_spec.md）:
      1. Solo が立った Track が 1 つでもあればそのトラック群のみ対象
      2. 評価対象のうち最も order が高い Track の Shot を採用
      3. mute=True の Track / Shot は skip
      4. lock は無視（評価には含む）
      5. 該当 Shot が無いフレームは None を返す（呼び出し側で前 Shot 継続）
    """
    st = getattr(scene, "kinema", None)
    if st is None:
        return None

    tracks = list(st.tracks)
    if not tracks:
        return None

    solo_tracks = [t for t in tracks if t.solo]
    pool = solo_tracks if solo_tracks else tracks
    pool = [t for t in pool if not t.mute]
    if not pool:
        return None
    pool.sort(key=lambda t: t.order, reverse=True)  # order 大が優先

    cur = scene.frame_current

    # uid → shots
    by_track: dict[str, list] = {}
    for clip in st.shot_clips:
        if clip.mute:
            continue
        by_track.setdefault(clip.track_uid, []).append(clip)

    for trk in pool:
        clips = by_track.get(trk.uid, [])
        if not clips:
            continue
        clips_sorted = sorted(clips, key=lambda c: c.frame_start)
        starts = [c.frame_start for c in clips_sorted]
        # bisect_right で「frame_start <= cur」を満たす最大 index を探す
        idx = bisect_right(starts, cur) - 1
        if idx < 0:
            continue
        cand = clips_sorted[idx]
        if cand.frame_start <= cur < cand.frame_end:
            return cand
    return None


def _apply_shot(scene, clip) -> None:
    cam = refs.safe_object(clip.camera)
    if not refs.is_camera_object(cam):
        return
    if scene.camera is not cam:
        scene.camera = cam
    if clip.lens_override and clip.lens_override > 0.001:
        try:
            cam.data.lens = clip.lens_override
        except Exception:
            pass
    if clip.dof_override and cam.data:
        try:
            cam.data.dof.use_dof = True
            cam.data.dof.focus_distance = clip.dof_focus_distance
            cam.data.dof.aperture_fstop = clip.dof_fstop
        except Exception:
            pass

    dt = follow_lookat.compute_dt(scene)
    if refs.safe_object(clip.follow_target):
        follow_lookat.update_follow(cam, clip, dt)
    if refs.safe_object(clip.lookat_target):
        follow_lookat.update_lookat(cam, clip, dt)
    if clip.noise_enabled:
        noise_mod.apply_noise_frame(cam, clip, scene.frame_current)


def _apply_instances_fallback(scene) -> None:
    """Shot が定義されていない時の互換動作。Instance に対して Follow/LookAt/Noise を適用。"""
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
        if refs.safe_object(inst.lookat_target):
            follow_lookat.update_lookat(cam, inst, dt)
        if inst.noise_enabled:
            noise_mod.apply_noise_frame(cam, inst, frame)


def dispatch(scene, force: bool = False) -> None:
    """frame_change_pre / depsgraph_update_post / update callback から呼ばれる。

    force=False のとき、直近 `_BURST_MIN_INTERVAL` 以内の連続呼び出しは抑制する。
    スライダー連打や depsgraph の連続発火で毎回 dispatch を走らせると、
    follow/lookat の damping 計算が「短時間 dt」を繰り返してジャンプ気味になる
    ことがあるため。

    force=True は frame_change_pre 経由のように「絶対に取りこぼせない」場合に使う。
    """
    global _in_dispatch
    if _in_dispatch:
        return
    if not hasattr(scene, "kinema"):
        return

    # バースト抑制
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
        clip = _pick_active_shot(scene)
        if clip is not None:
            cached = _last_shot_per_scene.get(scene.name)
            _last_shot_per_scene[scene.name] = clip.uid
            # 同 Shot 連続フレームでも camera 切替コストはかからないが、
            # follow/lookat/noise は毎フレーム評価する必要がある（追従するため）
            _apply_shot(scene, clip)
        else:
            # Shot が無い → 旧 cineflow ライクに Instance ベースで Follow/LookAt/Noise 適用
            _apply_instances_fallback(scene)
    finally:
        _in_dispatch = False
