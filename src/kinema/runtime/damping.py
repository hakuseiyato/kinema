"""Damping math のみを集めた純粋モジュール（bpy 非依存）。

FPS 非依存の lerp 係数計算と、frame_change の dt 計算（scene 名 -> 前フレーム
キャッシュは module-local）を提供する。テスト容易性のため bpy / mathutils
への依存を持たない。
"""

from __future__ import annotations

import math

# scene.name -> 最後に処理したフレーム
_last_frame_seen: dict[str, int] = {}


def compute_dt(scene_name: str, frame_current: int, fps: float, fps_base: float = 1.0) -> float:
    """前回 frame_change からの実時間秒。

    通常再生時は 1/fps。フレームジャンプ（|Δf|>2）時は 0 を返し、呼び出し側に
    「スナップせよ」と伝える。
    """
    effective_fps = max(1.0, fps / max(1.0, fps_base))
    prev = _last_frame_seen.get(scene_name, frame_current)
    _last_frame_seen[scene_name] = frame_current
    delta_f = frame_current - prev
    if abs(delta_f) > 2 or delta_f == 0:
        return 0.0
    return abs(delta_f) / effective_fps


def reset_frame_cache() -> None:
    """`.blend` 読み込み時に呼ぶ。"""
    _last_frame_seen.clear()


def damping_alpha(damping: float, dt: float) -> float:
    """damping (0..1) と dt から、その 1 ステップで適用すべき lerp 係数を返す。

    damping=0 → 即時 (alpha=1)、damping=1 → 動かない (alpha=0)。
    `alpha = 1 - exp(-dt/tau)`、tau = damping * 0.5（0..0.5 秒の時定数）。
    """
    if dt <= 0.0:
        return 1.0  # スナップ
    if damping <= 0.001:
        return 1.0
    if damping >= 0.999:
        return 0.0
    tau = damping * 0.5
    return 1.0 - math.exp(-dt / tau)
