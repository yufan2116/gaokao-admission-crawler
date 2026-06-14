"""重庆市插件（Phase 18）。"""

from __future__ import annotations

from provinces.chongqing import config
from provinces.plugin_factory import build_new_gaokao_school_plugin

ChongqingPlugin = build_new_gaokao_school_plugin(config)

__all__ = ["ChongqingPlugin"]
