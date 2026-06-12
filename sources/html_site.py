"""HTML 列表页发现模式（江苏、山东等）。"""

from __future__ import annotations

from sources.base import AccessStatus, SourceAdapter, SourceType, merge_access_status, probe_url


class HtmlListSiteAdapter(SourceAdapter):
    source_type = SourceType.HTML_LIST

    def check_availability(self) -> AccessStatus:
        urls = list(getattr(self.plugin, "index_urls", []) or [])
        base = getattr(self.plugin, "source_site_base_url", "") or ""
        if base and base not in urls:
            urls.insert(0, base)
        if not urls:
            return AccessStatus.PARTIAL
        results = [probe_url(u) for u in urls[:3]]
        return merge_access_status(*results)
