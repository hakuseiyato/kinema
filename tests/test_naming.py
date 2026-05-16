"""utils/naming.py の純粋ロジックテスト。bpy 非依存。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from kinema.utils import naming


def test_split_no_suffix():
    assert naming.split_base_and_index("Shot") == ("Shot", 0)


def test_split_with_suffix():
    assert naming.split_base_and_index("Shot_001") == ("Shot", 1)
    assert naming.split_base_and_index("Shot_042") == ("Shot", 42)


def test_split_short_suffix_ignored():
    # 桁数 < 3 は採番扱いしない
    assert naming.split_base_and_index("Cam_2") == ("Cam_2", 0)


def test_unique_name_no_conflict():
    assert naming.next_unique_name("Shot", []) == "Shot"


def test_unique_name_with_conflict():
    existing = {"Shot", "Shot_001"}
    assert naming.next_unique_name("Shot", existing) == "Shot_002"


def test_unique_name_many_conflicts():
    existing = {"Shot"} | {f"Shot_{n:03d}" for n in range(1, 11)}
    assert naming.next_unique_name("Shot", existing) == "Shot_011"


if __name__ == "__main__":
    test_split_no_suffix()
    test_split_with_suffix()
    test_split_short_suffix_ignored()
    test_unique_name_no_conflict()
    test_unique_name_with_conflict()
    test_unique_name_many_conflicts()
    print("OK")
