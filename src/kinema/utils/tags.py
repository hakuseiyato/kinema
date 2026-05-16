"""kn_tags（カンマ区切り文字列）のパース・整形を集約する。

PropertyGroup から StringProperty で受け取った "Cinematic, Hero,  Handheld" を
{"Cinematic", "Hero", "Handheld"} に正規化する。空白の有無・大文字小文字を
吸収するためのヘルパ。
"""

from __future__ import annotations

from typing import Iterable


def parse_tags(raw: str) -> list[str]:
    """カンマ区切り文字列をタグのリストに変換（順序保持・重複除去・空除外）。"""
    if not raw:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for chunk in raw.split(","):
        t = chunk.strip()
        if not t:
            continue
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out


def format_tags(tags: Iterable[str]) -> str:
    """タグのリストをカンマ + 空白区切りに整形して返す。"""
    return ", ".join(t.strip() for t in tags if t and t.strip())


def matches_all(raw: str, query: Iterable[str]) -> bool:
    """raw のタグ集合が query で指定された全タグを含むか（AND マッチ、大小無視）。"""
    actual = {t.lower() for t in parse_tags(raw)}
    needed = {t.lower().strip() for t in query if t and t.strip()}
    if not needed:
        return True
    return needed.issubset(actual)
