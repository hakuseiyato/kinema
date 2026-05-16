"""Noise — フレームごとの delta_location / delta_rotation_euler 書込。

旧 cineflow `runtime.py:_apply_noise_frame / _reset_noise` を移植。
driver 経由ではなく `frame_change_post` の中で直接書込する方式。
"""

from __future__ import annotations

import math

from mathutils import Vector, noise as mu_noise


def _eval_noise(frame: int, frequency: float, seed: int, axis: int) -> float:
    """-1..1 の擬似ノイズ。frame + 軸 + シードで一意。"""
    t = frame * frequency + seed + axis * 137.531
    return mu_noise.noise(Vector((t, axis * 73.17, seed * 0.37))) * 2.0


def apply_noise_frame(cam_obj, params, frame: int) -> None:
    """1 フレーム分の Noise オフセットを delta_* に書き込む。

    params に以下の属性を要求:
      noise_strength_pos, noise_strength_rot (deg), noise_frequency, noise_seed
    """
    if cam_obj is None:
        return
    freq = params.noise_frequency
    seed = params.noise_seed
    s_pos = params.noise_strength_pos
    s_rot_rad = math.radians(params.noise_strength_rot)
    cam_obj.delta_location = (
        _eval_noise(frame, freq, seed, 0) * s_pos,
        _eval_noise(frame, freq, seed, 1) * s_pos,
        _eval_noise(frame, freq, seed, 2) * s_pos,
    )
    cam_obj.delta_rotation_euler = (
        _eval_noise(frame, freq, seed, 3) * s_rot_rad,
        _eval_noise(frame, freq, seed, 4) * s_rot_rad,
        _eval_noise(frame, freq, seed, 5) * s_rot_rad,
    )


def reset_noise(cam_obj) -> None:
    """Noise OFF 時に delta_* を 0 に戻す。"""
    if cam_obj is None:
        return
    cam_obj.delta_location = (0.0, 0.0, 0.0)
    cam_obj.delta_rotation_euler = (0.0, 0.0, 0.0)
