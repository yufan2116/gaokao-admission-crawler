"""附件直链 seed 模式（如河北 file.hebeea.edu.cn）。"""

from __future__ import annotations

from sources.base import AccessStatus, SourceType, merge_access_status, probe_url
from sources.seed_site import SeedSiteAdapter


class AttachmentSiteAdapter(SeedSiteAdapter):
    source_type = SourceType.ATTACHMENT

    def check_availability(self) -> AccessStatus:
        seeds = getattr(self.plugin, "seed_announcements", {}) or {}
        attachment_urls: list[str] = []
        page_urls: list[str] = []
        for items in seeds.values():
            for seed in items:
                att = (seed.get("attachment_url") or "").strip()
                page = (seed.get("page_url") or "").strip()
                if att:
                    attachment_urls.append(att)
                elif page:
                    page_urls.append(page)
        if attachment_urls:
            return merge_access_status(*[probe_url(u) for u in attachment_urls[:4]])
        return super().check_availability()
