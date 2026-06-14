"""湖南省插件（Phase 18）。"""

from __future__ import annotations

from provinces.hunan import config
from provinces.plugin_factory import build_new_gaokao_school_plugin

HunanPlugin = build_new_gaokao_school_plugin(config)

__all__ = ["HunanPlugin"]
