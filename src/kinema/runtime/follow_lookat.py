"""Follow / LookAt の更新ロジック。

旧 cineflow `runtime.py:_update_follow / _update_lookat` を移植 + 拡張。
設計ポイント:
  - Follow は **球面座標 (yaw / pitch / distance)** で target の周りに配置
    - yaw=0 が target.matrix_world の +Y（正面）、180 で背後（旧 TPS 動作）
    - pitch で見下ろし / 見上げ
  - LookAt は中継 Empty (LookatProxy) を介してラグ追従
  - Damping は fps 非依存 `alpha = 1 - exp(-dt/tau)`（damping.py に分離）
"""

from __future__ import annotations

import math

import bpy
from mathutils import Vector

from ..config import constants as C
from ..utils import refs
from . import damping as damping_mod


# ---------------------------------------------------------------------------
# Damping math は damping.py に切り出してテスト容易にした。
# 後方互換のため、本モジュールからも同じシンボルを再エクスポートする。
# ---------------------------------------------------------------------------

reset_frame_cache = damping_mod.reset_frame_cache
damping_alpha = damping_mod.damping_alpha


def compute_dt(scene) -> float:
    """Scene から fps/frame を取り出して damping.compute_dt を呼ぶ。"""
    return damping_mod.compute_dt(
        scene.name,
        scene.frame_current,
        float(scene.render.fps),
        float(scene.render.fps_base),
    )


# ---------------------------------------------------------------------------
# Follow
# ---------------------------------------------------------------------------

def update_follow(cam_obj, params, dt: float) -> None:
    """カメラを follow_target の周りに **球面座標** で配置する。

    params に以下の属性を要求:
      follow_target, follow_distance, follow_yaw, follow_pitch,
      follow_height, follow_side, follow_damping

    球面座標 (target ローカル空間):
      - yaw=0   → +Y 方向 (target の正面、こちら向き)
      - yaw=90  → +X 方向 (target の右)
      - yaw=180 → -Y 方向 (target の背後、旧 TPS の挙動)
      - yaw=-90 → -X 方向 (target の左)
      - pitch>0 → 上から見下ろし
      - pitch<0 → 下から見上げ
    """
    target = refs.safe_object(getattr(params, "follow_target", None))
    if target is None or cam_obj is None:
        return

    dist = float(params.follow_distance)
    yaw_rad = math.radians(float(getattr(params, "follow_yaw", 0.0)))
    pitch_rad = math.radians(float(getattr(params, "follow_pitch", 0.0)))
    height = float(params.follow_height)
    side = float(params.follow_side)

    # target ローカル空間での方向ベクトル
    cos_pitch = math.cos(pitch_rad)
    dir_local = Vector((
        math.sin(yaw_rad) * cos_pitch,
        math.cos(yaw_rad) * cos_pitch,
        math.sin(pitch_rad),
    ))

    # target の rotation 部分でワールド空間に変換
    rot_3x3 = target.matrix_world.to_3x3()
    dir_world = rot_3x3 @ dir_local

    # 接線右方向（カメラ視線と直交、ワールド上向きと外積）
    world_up = Vector((0.0, 0.0, 1.0))
    if abs(dir_world.dot(world_up)) > 0.999:
        # 真上/真下を向いている場合は別の基準で右方向を決める
        tangent_right = (rot_3x3 @ Vector((1.0, 0.0, 0.0))).normalized()
    else:
        tangent_right = dir_world.cross(world_up).normalized()

    ideal = (
        target.matrix_world.translation
        + dir_world * dist
        + world_up * height
        + tangent_right * side
    )

    alpha = damping_alpha(params.follow_damping, dt)
    if alpha >= 0.999:
        cam_obj.location = ideal
    else:
        cam_obj.location = Vector(cam_obj.location).lerp(ideal, alpha)


# ---------------------------------------------------------------------------
# LookAt
# ---------------------------------------------------------------------------

def _ensure_lookat_proxy(cam_obj, target) -> bpy.types.Object:
    """LookAt 用の中継 Empty を取得 or 作成。"""
    proxy_name = cam_obj.name + C.KN_LOOKAT_PROXY_SUFFIX
    proxy = bpy.data.objects.get(proxy_name)
    if proxy is None:
        proxy = bpy.data.objects.new(proxy_name, None)
        proxy.empty_display_type = "PLAIN_AXES"
        proxy.empty_display_size = 0.2
        for coll in cam_obj.users_collection:
            coll.objects.link(proxy)
            break
        else:
            bpy.context.scene.collection.objects.link(proxy)
        proxy.location = target.matrix_world.translation
    return proxy


def _find_or_set_track_to(cam_obj, proxy) -> bpy.types.Constraint:
    """カメラの Track To 制約を取得 or 作成し、target を proxy にする。"""
    track_to = None
    for con in cam_obj.constraints:
        if con.type == "TRACK_TO":
            track_to = con
            break
    if track_to is None:
        track_to = cam_obj.constraints.new("TRACK_TO")
        track_to.track_axis = "TRACK_NEGATIVE_Z"
        track_to.up_axis = "UP_Y"
    track_to.target = proxy
    track_to.influence = 1.0
    return track_to


def update_lookat(cam_obj, params, dt: float) -> None:
    """LookAt Proxy を `params.lookat_target` にラグ追従させる（後方互換用）。"""
    target = refs.safe_object(getattr(params, "lookat_target", None))
    if target is None:
        return
    update_lookat_with_target(cam_obj, target, params.lookat_damping, dt)


def update_lookat_with_target(cam_obj, target, damping: float, dt: float) -> None:
    """target を明示指定して LookAt 追従させる。

    Follow Target を自動 LookAt する場合などで Instance Item のスキーマに
    縛られず使えるようにした版。
    """
    if target is None or cam_obj is None:
        return

    proxy = _ensure_lookat_proxy(cam_obj, target)
    _find_or_set_track_to(cam_obj, proxy)

    alpha = damping_alpha(damping, dt)
    target_pos = target.matrix_world.translation
    if alpha >= 0.999:
        proxy.location = target_pos
    else:
        proxy.location = Vector(proxy.location).lerp(target_pos, alpha)


def cleanup_lookat_proxy(cam_obj) -> None:
    """LookAt Proxy を削除（lookat_target=None / unload 時）。"""
    if cam_obj is None:
        return
    proxy_name = cam_obj.name + C.KN_LOOKAT_PROXY_SUFFIX
    proxy = bpy.data.objects.get(proxy_name)
    if proxy is None:
        return
    for con in list(cam_obj.constraints):
        if con.type == "TRACK_TO" and con.target == proxy:
            cam_obj.constraints.remove(con)
    for coll in list(proxy.users_collection):
        coll.objects.unlink(proxy)
    if proxy.users == 0:
        bpy.data.objects.remove(proxy, do_unlink=True)
