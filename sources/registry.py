"""
省份 → SourceAdapter 注册（Phase 15）。
"""

from __future__ import annotations

from typing import Any

from sources.archive_site import ArchiveSiteAdapter
from sources.attachment_site import AttachmentSiteAdapter
from sources.base import AccessStatus, SourceAdapter, SourceType, merge_access_status
from sources.html_site import HtmlListSiteAdapter
from sources.protected_site import ProtectedSiteAdapter
from sources.seed_site import SeedSiteAdapter

PROVINCE_SOURCE_TYPES: dict[str, list[SourceType]] = {
    "江苏": [SourceType.HTML_LIST],
    "山东": [SourceType.HTML_LIST],
    "浙江": [SourceType.SEED_ONLY],
    "福建": [SourceType.SEED_ONLY],
    "河北": [SourceType.SEED_ONLY],
    "广东": [SourceType.ARCHIVE],
    "河南": [SourceType.ARCHIVE, SourceType.PROTECTED],
    "湖北": [SourceType.SEED_ONLY],
    "湖南": [SourceType.SEED_ONLY],
    "辽宁": [SourceType.SEED_ONLY],
    "重庆": [SourceType.SEED_ONLY],
}

PROVINCE_DEFAULT_ACCESS_STATUS: dict[str, AccessStatus] = {
    "jiangsu": AccessStatus.AVAILABLE,
    "shandong": AccessStatus.AVAILABLE,
    "zhejiang": AccessStatus.AVAILABLE,
    "fujian": AccessStatus.WAF_BLOCKED,
    "hebei": AccessStatus.CONNECTION_RESET,
    "henan": AccessStatus.VERIFICATION_REQUIRED,
    "guangdong": AccessStatus.PARTIAL,
    "hubei": AccessStatus.AVAILABLE,
    "hunan": AccessStatus.UNKNOWN,
    "liaoning": AccessStatus.UNKNOWN,
    "chongqing": AccessStatus.UNKNOWN,
}

PROVINCE_NAME_TO_DEFAULT_STATUS: dict[str, AccessStatus] = {
    "江苏": AccessStatus.AVAILABLE,
    "山东": AccessStatus.AVAILABLE,
    "浙江": AccessStatus.AVAILABLE,
    "福建": AccessStatus.WAF_BLOCKED,
    "河北": AccessStatus.CONNECTION_RESET,
    "河南": AccessStatus.VERIFICATION_REQUIRED,
    "广东": AccessStatus.PARTIAL,
    "湖北": AccessStatus.AVAILABLE,
    "湖南": AccessStatus.UNKNOWN,
    "辽宁": AccessStatus.UNKNOWN,
    "重庆": AccessStatus.UNKNOWN,
}


class CompositeSourceAdapter(SourceAdapter):
    """多模式省份（如河南 ARCHIVE + PROTECTED）。"""

    def __init__(
        self,
        plugin: Any,
        adapters: list[SourceAdapter],
        *,
        default_status: AccessStatus | None = None,
    ) -> None:
        super().__init__(plugin, default_status=default_status)
        self._adapters = adapters

    @property
    def source_types(self) -> list[SourceType]:
        types: list[SourceType] = []
        for adapter in self._adapters:
            types.extend(adapter.source_types)
        return types

    def check_availability(self) -> AccessStatus:
        return merge_access_status(*(a.check_availability() for a in self._adapters))

    def get_status(self) -> AccessStatus:
        if self._default_status is not None:
            return self._default_status
        return self.check_availability()


def _has_attachment_seeds(plugin: Any) -> bool:
    seeds = getattr(plugin, "seed_announcements", {}) or {}
    for items in seeds.values():
        for seed in items:
            if (seed.get("attachment_url") or "").strip():
                return True
    return False


def _build_adapter_for_type(
    plugin: Any,
    source_type: SourceType,
    default_status: AccessStatus | None,
) -> SourceAdapter:
    if source_type == SourceType.HTML_LIST:
        return HtmlListSiteAdapter(plugin, default_status=default_status)
    if source_type == SourceType.SEED_ONLY:
        if _has_attachment_seeds(plugin):
            return AttachmentSiteAdapter(plugin, default_status=default_status)
        return SeedSiteAdapter(plugin, default_status=default_status)
    if source_type == SourceType.ARCHIVE:
        return ArchiveSiteAdapter(plugin, default_status=None)
    if source_type == SourceType.PROTECTED:
        return ProtectedSiteAdapter(plugin, default_status=None)
    if source_type == SourceType.ATTACHMENT:
        return AttachmentSiteAdapter(plugin, default_status=default_status)
    return SeedSiteAdapter(plugin, default_status=default_status)


def get_source_adapter_for_plugin(plugin: Any) -> SourceAdapter:
    """按省份 slug 构建 SourceAdapter。"""
    slug = getattr(plugin, "province_slug", "")
    province_name = getattr(plugin, "province_name", "")
    default = PROVINCE_DEFAULT_ACCESS_STATUS.get(slug) or PROVINCE_NAME_TO_DEFAULT_STATUS.get(
        province_name
    )
    types = PROVINCE_SOURCE_TYPES.get(province_name, [SourceType.SEED_ONLY])
    if len(types) == 1:
        return _build_adapter_for_type(plugin, types[0], default)
    inner = [_build_adapter_for_type(plugin, t, None) for t in types]
    return CompositeSourceAdapter(plugin, inner, default_status=default)


def get_default_access_status(province: str) -> AccessStatus:
    """静态配置的省份访问状态（Dashboard / API）。"""
    from normalizers.province import normalize_province

    name = normalize_province(province)
    return PROVINCE_NAME_TO_DEFAULT_STATUS.get(name, AccessStatus.PARTIAL)
