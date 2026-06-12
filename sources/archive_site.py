"""归档包下载模式（广东 ZIP、河南 RAR 等）。"""

from __future__ import annotations

from sources.base import AccessStatus, SourceAdapter, SourceType, merge_access_status, probe_url
from sources.html_site import HtmlListSiteAdapter
from sources.seed_site import SeedSiteAdapter


class ArchiveSiteAdapter(SourceAdapter):
    source_type = SourceType.ARCHIVE

    def check_availability(self) -> AccessStatus:
        # 优先探测 seed / 列表页是否可发现归档附件
        helper: SourceAdapter
        seeds = getattr(self.plugin, "seed_announcements", {}) or {}
        if seeds:
            helper = SeedSiteAdapter(self.plugin)
        elif getattr(self.plugin, "index_urls", None):
            helper = HtmlListSiteAdapter(self.plugin)
        else:
            base = getattr(self.plugin, "source_site_base_url", "") or ""
            return probe_url(base) if base else AccessStatus.PARTIAL
        list_status = helper.check_availability()
        # 归档包本身可能部分可解析（如广东 ZIP 内 PDF）
        if list_status == AccessStatus.AVAILABLE:
            return AccessStatus.PARTIAL
        return merge_access_status(list_status, AccessStatus.PARTIAL)
