"""Seed 公告兜底模式（浙江、福建、河北等）。"""

from __future__ import annotations

from sources.base import AccessStatus, SourceAdapter, SourceType, merge_access_status, probe_url


class SeedSiteAdapter(SourceAdapter):
    source_type = SourceType.SEED_ONLY

    def check_availability(self) -> AccessStatus:
        seeds = getattr(self.plugin, "seed_announcements", {}) or {}
        urls: list[str] = []
        for items in seeds.values():
            for seed in items:
                page = (seed.get("page_url") or "").strip()
                if page:
                    urls.append(page)
        base = getattr(self.plugin, "source_site_base_url", "") or ""
        if base:
            urls.append(base)
        if not urls:
            return AccessStatus.PARTIAL
        return merge_access_status(*[probe_url(u) for u in urls[:4]])
