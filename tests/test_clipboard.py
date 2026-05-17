"""utils/clipboard.py の純粋ロジックテスト（bpy 非依存）。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from kinema.utils import clipboard as cb


class FakeObj:
    """属性アクセスで getattr/setattr する単純な箱。"""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class FakeNamed:
    def __init__(self, name):
        self.name = name


def test_copy_fields_basic():
    src = FakeObj(lens_mm=50.0, follow_distance=5.0)
    targets = {"inst": src}
    fields = (("inst", "lens_mm"), ("inst", "follow_distance"))
    out = cb.copy_fields(fields, targets)
    assert out == {"inst.lens_mm": 50.0, "inst.follow_distance": 5.0}


def test_copy_fields_skips_missing_target():
    targets = {"inst": FakeObj(lens_mm=1.0), "dof": None}
    fields = (("inst", "lens_mm"), ("dof", "focus_distance"))
    out = cb.copy_fields(fields, targets)
    assert out == {"inst.lens_mm": 1.0}


def test_copy_fields_serializes_iterable():
    src = FakeObj(color=(0.1, 0.2, 0.3))
    out = cb.copy_fields((("inst", "color"),), {"inst": src})
    assert out == {"inst.color": [0.1, 0.2, 0.3]}


def test_paste_fields_basic():
    dst = FakeObj()
    fields = (("inst", "lens_mm"), ("inst", "follow_distance"))
    data = {"inst.lens_mm": 35.0, "inst.follow_distance": 8.0}
    count = cb.paste_fields(fields, {"inst": dst}, data)
    assert count == 2
    assert dst.lens_mm == 35.0
    assert dst.follow_distance == 8.0


def test_paste_fields_skips_missing_key():
    dst = FakeObj()
    fields = (("inst", "lens_mm"), ("inst", "shift_x"))
    data = {"inst.lens_mm": 50.0}
    count = cb.paste_fields(fields, {"inst": dst}, data)
    assert count == 1
    assert dst.lens_mm == 50.0
    assert not hasattr(dst, "shift_x")


def test_copy_object_ref_to_name():
    src = FakeObj(follow_target=FakeNamed("Suzanne"))
    out = cb.copy_object_ref(("inst", "follow_target"), {"inst": src})
    assert out == {"inst.follow_target__name": "Suzanne"}


def test_copy_object_ref_none_to_empty_string():
    src = FakeObj(follow_target=None)
    out = cb.copy_object_ref(("inst", "follow_target"), {"inst": src})
    assert out == {"inst.follow_target__name": ""}


def test_paste_object_ref_resolves_name():
    dst = FakeObj()
    sentinel = FakeNamed("Suzanne")
    resolve = lambda name: sentinel if name == "Suzanne" else None
    data = {"inst.follow_target__name": "Suzanne"}
    count = cb.paste_object_ref(("inst", "follow_target"), {"inst": dst}, data, resolve)
    assert count == 1
    assert dst.follow_target is sentinel


def test_paste_object_ref_empty_name_sets_none():
    dst = FakeObj()
    resolve = lambda name: None
    data = {"inst.follow_target__name": ""}
    count = cb.paste_object_ref(("inst", "follow_target"), {"inst": dst}, data, resolve)
    assert count == 1
    assert dst.follow_target is None


def test_roundtrip_full():
    """copy → paste で値が完全に復元される。"""
    src = FakeObj(lens_mm=85.0, follow_distance=4.0, color=(1.0, 0.5, 0.0))
    fields = (("inst", "lens_mm"), ("inst", "follow_distance"), ("inst", "color"))
    data = cb.copy_fields(fields, {"inst": src})

    dst = FakeObj()
    count = cb.paste_fields(fields, {"inst": dst}, data)
    assert count == 3
    assert dst.lens_mm == src.lens_mm
    assert dst.follow_distance == src.follow_distance
    assert dst.color == [1.0, 0.5, 0.0]  # list 化されている


if __name__ == "__main__":
    for fn in [v for k, v in dict(globals()).items() if k.startswith("test_")]:
        fn()
    print("OK")
