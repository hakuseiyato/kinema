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


def test_serial_from_basic():
    # ベース名重複なし → そのまま
    assert naming.next_serial_from("Hero", set()) == "Hero"


def test_serial_from_base_exists():
    # Hero だけある → Hero_001
    assert naming.next_serial_from("Hero", {"Hero"}) == "Hero_001"


def test_serial_from_numbered_input():
    # Hero_001 を元にして次の連番
    existing = {"Hero", "Hero_001"}
    assert naming.next_serial_from("Hero_001", existing) == "Hero_002"


def test_serial_from_skips_holes():
    # Hero, Hero_001, Hero_005 → 次は Hero_006（max+1）
    existing = {"Hero", "Hero_001", "Hero_005"}
    assert naming.next_serial_from("Hero_001", existing) == "Hero_006"


def test_serial_from_double_suffix():
    # Hero_001_001 のような二重 suffix → "Hero_001" を base にして採番
    existing = {"Hero", "Hero_001", "Hero_001_001"}
    result = naming.next_serial_from("Hero_001_001", existing)
    # base="Hero_001" の連番 → "Hero_001_002"
    assert result == "Hero_001_002"


if __name__ == "__main__":
    test_split_no_suffix()
    test_split_with_suffix()
    test_split_short_suffix_ignored()
    test_unique_name_no_conflict()
    test_unique_name_with_conflict()
    test_unique_name_many_conflicts()
    print("OK")
