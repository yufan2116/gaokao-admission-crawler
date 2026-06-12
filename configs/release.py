"""MVP+ 稳定版标识（Phase 16）。"""

from __future__ import annotations

STABLE_VERSION_LABEL = "MVP+ Stable"
STABLE_VERSION_ID = "mvp-plus-stable"

STRUCTURED_PROVINCES: tuple[str, ...] = ("江苏", "浙江", "山东", "广东")
SOURCE_AWARE_PROVINCES: tuple[str, ...] = ("河南", "福建", "河北")

STABLE_VERSION_NOTE = (
    "这是 MVP+ 稳定版本，覆盖多省插件与 Source Adapter；"
    "不是全国完整库，未结构化省份为 source-aware 注册状态。"
)
