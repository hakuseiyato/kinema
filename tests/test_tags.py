"""utils/tags.py の純粋ロジックテスト。bpy 非依存。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from kinema.utils import tags


def test_parse_empty():
    assert tags.parse_tags("") == []


def test_parse_basic():
    assert tags.parse_tags("Cinematic, Hero") == ["Cinematic", "Hero"]


def test_parse_dedup_and_strip():
    # 空白除去・重複除去（大小無視）・順序保持
    assert tags.parse_tags("Cinematic,  hero , Cinematic") == ["Cinematic", "hero"]


def test_parse_skip_empty_chunks():
    assert tags.parse_tags("a,, ,b") == ["a", "b"]


def test_format_roundtrip():
    assert tags.format_tags(["a", "b", "c"]) == "a, b, c"


def test_matches_all_empty_query():
    assert tags.matches_all("Cinematic, Hero", []) is True


def test_matches_all_subset():
    assert tags.matches_all("Cinematic, Hero, Wide", ["hero"]) is True
    assert tags.matches_all("Cinematic, Hero, Wide", ["hero", "wide"]) is True


def test_matches_all_miss():
    assert tags.matches_all("Cinematic, Hero", ["closeup"]) is False


if __name__ == "__main__":
    for fn in [v for k, v in dict(globals()).items() if k.startswith("test_")]:
        fn()
    print("OK")
