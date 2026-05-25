"""Collection ベースの動的ターゲット解決。

yato_visibility_kit の Solo モード（表情差分の切替）と連動するため、
「Collection 内で hide_viewport==False の最初のオブジェクト」を解決する。

判定基準: hide_viewport == False のみ。複数可視時は collection.objects の
順で最初に見つかったものを採用。サブコレクションも再帰的に走査。
"""

from __future__ import annotations


def resolve_visible_in_collection(coll, _seen: set | None = None):
    """coll 配下で最初の hide_viewport==False のオブジェクトを返す。

    再帰で見つからなければ None。死んだ参照や None メンバはスキップ。
    """
    if coll is None:
        return None
    if _seen is None:
        _seen = set()
    if coll.name in _seen:
        return None
    _seen.add(coll.name)
    for o in coll.objects:
        if o is None:
            continue
        try:
            if not o.hide_viewport:
                return o
        except Exception:
            continue
    for child in coll.children:
        r = resolve_visible_in_collection(child, _seen)
        if r is not None:
            return r
    return None


def resolve_target(params, base_attr: str):
    """Instance / Preset 両対応のターゲット解決。

    base_attr: "follow_target" | "lookat_target" | "dof_focus"
      - base_attr が "dof_focus" の場合のみ、Object ref 側のフォールバックは
        呼び元（dispatcher）が cam.data.dof.focus_object をそのまま尊重するので
        ここでは Collection 解決の結果（None も含む）だけ返す。

    通常の Follow/LookAt: Collection モード ON で解決失敗 → Object 直指定に
    フォールバック（None 安全のため）。
    """
    use_coll_attr = f"{base_attr}_use_collection"
    coll_attr = f"{base_attr}_collection"
    if getattr(params, use_coll_attr, False):
        coll = getattr(params, coll_attr, None)
        resolved = resolve_visible_in_collection(coll)
        if resolved is not None:
            return resolved
        # 解決失敗 → Object 直指定を fallback として使う（None 安全）
    obj = getattr(params, base_attr, None)
    return obj if obj is not None else None
