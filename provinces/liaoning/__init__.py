"""辽宁省插件（Phase 18）。"""

from __future__ import annotations

from provinces.liaoning import config
from provinces.plugin_factory import build_new_gaokao_school_plugin

LiaoningPlugin = build_new_gaokao_school_plugin(config)

__all__ = ["LiaoningPlugin"]
