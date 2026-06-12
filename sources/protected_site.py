"""需验证码 / 数据中心查询页模式（河南 datacenter 等）。"""

from __future__ import annotations

import requests

from config import DEFAULT_HEADERS, REQUEST_TIMEOUT
from sources.base import (
    AccessStatus,
    SourceAdapter,
    SourceType,
    probe_html_for_verification,
)


PROTECTED_PROBE_URLS: dict[str, list[str]] = {
    "henan": [
        "https://datacenter.haeea.cn",
    ],
}


class ProtectedSiteAdapter(SourceAdapter):
    source_type = SourceType.PROTECTED

    def check_availability(self) -> AccessStatus:
        slug = getattr(self.plugin, "province_slug", "")
        urls = PROTECTED_PROBE_URLS.get(slug, [])
        base = getattr(self.plugin, "source_site_base_url", "") or ""
        if base and "datacenter" in base.lower():
            urls.append(base)
        if not urls:
            return AccessStatus.VERIFICATION_REQUIRED
        for url in urls:
            try:
                response = requests.get(
                    url,
                    headers=DEFAULT_HEADERS,
                    timeout=REQUEST_TIMEOUT,
                    allow_redirects=True,
                )
                if response.status_code in (403, 412, 429):
                    return AccessStatus.VERIFICATION_REQUIRED
                if probe_html_for_verification(response.text):
                    return AccessStatus.VERIFICATION_REQUIRED
            except requests.RequestException:
                continue
        return AccessStatus.VERIFICATION_REQUIRED
