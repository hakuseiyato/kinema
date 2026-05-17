"""runtime/damping.py の純粋ロジックテスト。bpy 非依存。"""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from kinema.runtime.damping import damping_alpha, compute_dt, reset_frame_cache


def test_no_dt_means_snap():
    assert damping_alpha(0.5, 0.0) == 1.0


def test_zero_damping_means_snap():
    assert damping_alpha(0.0, 0.05) == 1.0


def test_full_damping_means_freeze():
    assert damping_alpha(1.0, 0.05) == 0.0


def test_monotonic_in_dt():
    # dt が大きくなるほど alpha も増える（より追従する）
    a1 = damping_alpha(0.5, 0.01)
    a2 = damping_alpha(0.5, 0.05)
    a3 = damping_alpha(0.5, 0.5)
    assert a1 < a2 < a3


def test_within_bounds():
    for damping in (0.1, 0.3, 0.5, 0.7, 0.9):
        for dt in (0.001, 0.01, 0.05, 0.1, 1.0):
            a = damping_alpha(damping, dt)
            assert 0.0 <= a <= 1.0


def test_formula_consistency():
    # alpha = 1 - exp(-dt/tau), tau = damping * 0.5
    damping = 0.4
    dt = 0.05
    expected = 1.0 - math.exp(-dt / (damping * 0.5))
    assert abs(damping_alpha(damping, dt) - expected) < 1e-9


def test_compute_dt_normal_playback():
    reset_frame_cache()
    # 初回呼び出し: フレームは前回 = 今回扱い、実時間も初回 → dt=0
    assert compute_dt("test", 10, 24.0) == 0.0
    # 1 フレーム進んだ → フレーム差で 1/24 s
    dt = compute_dt("test", 11, 24.0)
    assert abs(dt - 1 / 24) < 1e-9


def test_compute_dt_jump_returns_zero():
    reset_frame_cache()
    compute_dt("test", 10, 24.0)
    # |Δf| > 2 でスナップ扱い
    assert compute_dt("test", 50, 24.0) == 0.0


def test_compute_dt_reset_clears():
    reset_frame_cache()
    compute_dt("scene", 5, 24.0)
    reset_frame_cache()
    # リセット後の最初の呼び出しは dt=0
    assert compute_dt("scene", 5, 24.0) == 0.0


def test_compute_dt_same_frame_uses_elapsed_time():
    """同一フレームで連続呼び出し時に実時間 dt が返ること（停止中の追従シナリオ）。"""
    import time as _time
    reset_frame_cache()
    compute_dt("scene", 5, 24.0)
    # ごく短時間（< 1ms）の連続呼び出し → 0
    dt_burst = compute_dt("scene", 5, 24.0)
    assert dt_burst == 0.0
    # 少し sleep してから呼ぶと実時間 dt > 0
    _time.sleep(0.02)
    dt_after_sleep = compute_dt("scene", 5, 24.0)
    assert 0.001 < dt_after_sleep < 1.0


if __name__ == "__main__":
    for fn in [v for k, v in dict(globals()).items() if k.startswith("test_")]:
        fn()
    print("OK")
