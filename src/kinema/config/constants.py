"""kinema 全体で共有する定数とキー名。

書き手と読み手のミスマッチを防ぐため、カスタムプロパティのキー名・
プレフィックス・enum 値などをここに集約する。
"""

# --- Defaults ---
DEFAULT_PRESET_ROOT = "Kinema_Presets"
DEFAULT_INSTANCES_ROOT = "Kinema_Instances"

# --- Marker / proxy prefix ---
KN_MARKER_PREFIX = "KN_"
KN_LOOKAT_PROXY_SUFFIX = "_KnLookatProxy"

# --- Workspace ---
KN_WORKSPACE_NAME = "Kinema"

# --- Custom property keys (collection / camera) ---
KEY_TAGS = "kn_tags"            # カンマ区切り文字列
KEY_HAS_ANIM = "kn_has_anim"
KEY_DEFAULT_LENS = "kn_default_lens"
KEY_PREVIEW_END = "kn_preview_end"
KEY_FOLLOW_TARGET = "kn_follow_target"
KEY_LOOKAT_TARGET = "kn_lookat_target"
KEY_SCHEMA_VERSION = "kn_schema_version"

# 旧 cineflow 互換キー（Importer のみが参照）
LEGACY_CF_MODE = "cf_mode"
LEGACY_CF_MODE_CATEGORY = "cf_category"
LEGACY_CF_HAS_ANIM = "cf_has_anim"
LEGACY_CF_DEFAULT_LENS = "cf_default_lens"
LEGACY_CF_PREVIEW_END = "cf_preview_end"
LEGACY_CF_FOLLOW_TARGET = "cf_follow_target"
LEGACY_CF_LOOKAT_TARGET = "cf_lookat_target"

# 現行スキーマバージョン（JSON I/O / マイグレーション判定で使用）
CURRENT_SCHEMA_VERSION = 1
