"""utils/json_io.py の純粋ロジックテスト（bpy 非依存）。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from kinema.utils import json_io


class FakeNamed:
    def __init__(self, name):
        self.name = name


class FakeInstance:
    """Instance Item のスタブ。フィールドアクセスのみシミュレート。"""

    def __init__(self, **kwargs):
        # 安全なデフォルト
        defaults = {
            "name": "Inst",
            "source_preset": "",
            "enabled": True,
            "solo": False,
            "locked": False,
            "lens_mm": 50.0,
            "follow_distance": 5.0,
            "follow_rot_x": 0.0,
            "follow_rot_y": 0.0,
            "follow_rot_z": 0.0,
            "follow_height": 0.0,
            "follow_side": 0.0,
            "follow_damping": 0.3,
            "follow_auto_lookat": True,
            "lookat_damping": 0.3,
            "noise_enabled": False,
            "noise_strength_pos": 0.05,
            "noise_strength_rot": 0.5,
            "noise_frequency": 0.5,
            "noise_seed": 0,
            "collection_ref": None,
            "camera_ref": None,
            "follow_target": None,
            "lookat_target": None,
        }
        defaults.update(kwargs)
        for k, v in defaults.items():
            setattr(self, k, v)


def test_serialize_basic():
    inst = FakeInstance(name="Test1", lens_mm=85.0, follow_distance=10.0)
    d = json_io.serialize_instance(inst)
    assert d["name"] == "Test1"
    assert d["lens_mm"] == 85.0
    assert d["follow_distance"] == 10.0
    # pointer は名前で
    assert d["follow_target__name"] == ""


def test_serialize_with_pointers():
    inst = FakeInstance(
        follow_target=FakeNamed("Suzanne"),
        lookat_target=FakeNamed("Empty"),
    )
    d = json_io.serialize_instance(inst)
    assert d["follow_target__name"] == "Suzanne"
    assert d["lookat_target__name"] == "Empty"


def test_deserialize_roundtrip():
    src = FakeInstance(
        name="Hero", lens_mm=35.0, follow_rot_z=90.0, noise_enabled=True,
        follow_target=FakeNamed("Tgt"),
    )
    data = json_io.serialize_instance(src)

    dst = FakeInstance()
    sentinel = FakeNamed("Tgt")
    json_io.deserialize_instance(
        dst, data,
        resolve_object=lambda name: sentinel if name == "Tgt" else None,
        resolve_collection=lambda name: None,
    )
    assert dst.name == "Hero"
    assert dst.lens_mm == 35.0
    assert dst.follow_rot_z == 90.0
    assert dst.noise_enabled is True
    assert dst.follow_target is sentinel


def test_schema_version_check():
    """スキーマバージョン不一致でエラー扱い。"""

    class FakeScene:
        instances = []

    bad_data = {"kinema_schema": 99, "instances": []}
    result = json_io.deserialize_scene(
        FakeScene(), bad_data,
        resolve_object=lambda n: None,
        resolve_collection=lambda n: None,
        add_instance=lambda: None,
    )
    assert result["ok"] is False


def test_serialize_scene_structure():
    class FakeScene:
        preset_root_name = "Kinema_Presets"
        instances_root_name = "Kinema_Instances"
        instances = [FakeInstance(name="A"), FakeInstance(name="B")]

    data = json_io.serialize_scene(FakeScene())
    assert data["kinema_schema"] == 1
    assert data["preset_root_name"] == "Kinema_Presets"
    assert len(data["instances"]) == 2
    assert data["instances"][0]["name"] == "A"
    assert data["instances"][1]["name"] == "B"


if __name__ == "__main__":
    for fn in [v for k, v in dict(globals()).items() if k.startswith("test_")]:
        fn()
    print("OK")
