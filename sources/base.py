"""
数据源适配层基类（Phase 15）。

统一各省官网的发现、下载与访问状态评估，不把 WAF/验证码/连接重置当作 bug。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

import requests

from config import DEFAULT_HEADERS, REQUEST_TIMEOUT

logger = logging.getLogger(__name__)

VERIFICATION_MARKERS = ("验证码", "captcha", "人机验证", "安全验证", "datacenter.haeea.cn")


class SourceType(str, Enum):
    """官网数据获取模式。"""

    HTML_LIST = "html_list"
    SEED_ONLY = "seed_only"
    ARCHIVE = "archive"
    PROTECTED = "protected"
    ATTACHMENT = "attachment"


class AccessStatus(str, Enum):
    """数据源访问状态（非流水线失败码）。"""

    AVAILABLE = "available"
    PARTIAL = "partial"
    WAF_BLOCKED = "waf_blocked"
    VERIFICATION_REQUIRED = "verification_required"
    CONNECTION_RESET = "connection_reset"
    UNSUPPORTED_ARCHIVE = "unsupported_archive"
    UNSUPPORTED_PDF = "unsupported_pdf"


ACCESS_STATUS_LABELS: dict[str, str] = {
    AccessStatus.AVAILABLE.value: "可访问",
    AccessStatus.PARTIAL.value: "部分可访问",
    AccessStatus.WAF_BLOCKED.value: "WAF 拦截",
    AccessStatus.VERIFICATION_REQUIRED.value: "需验证码",
    AccessStatus.CONNECTION_RESET.value: "连接被重置",
    AccessStatus.UNSUPPORTED_ARCHIVE.value: "不支持归档包",
    AccessStatus.UNSUPPORTED_PDF.value: "不支持 PDF",
}

LEGACY_ACCESS_STATUS_MAP: dict[str, AccessStatus] = {
    "ok": AccessStatus.AVAILABLE,
    "unsupported_verification_required": AccessStatus.VERIFICATION_REQUIRED,
}


def normalize_access_status(value: str | AccessStatus | None) -> AccessStatus:
    """将旧 discovery access_status 或字符串转为标准 AccessStatus。"""
    if isinstance(value, AccessStatus):
        return value
    if not value:
        return AccessStatus.AVAILABLE
    text = str(value).strip().lower()
    if text in LEGACY_ACCESS_STATUS_MAP:
        return LEGACY_ACCESS_STATUS_MAP[text]
    try:
        return AccessStatus(text)
    except ValueError:
        return AccessStatus.PARTIAL


def probe_url(url: str, *, timeout: int = REQUEST_TIMEOUT) -> AccessStatus:
    """探测单个 URL 可达性，映射为 AccessStatus。"""
    if not url:
        return AccessStatus.PARTIAL
    try:
        response = requests.head(
            url,
            headers=DEFAULT_HEADERS,
            timeout=timeout,
            allow_redirects=True,
        )
        if response.status_code in (403, 451):
            return AccessStatus.WAF_BLOCKED
        if response.status_code in (412, 429):
            return AccessStatus.VERIFICATION_REQUIRED
        if response.status_code >= 400:
            return AccessStatus.PARTIAL
        return AccessStatus.AVAILABLE
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status in (403, 451):
            return AccessStatus.WAF_BLOCKED
        if status in (412, 429):
            return AccessStatus.VERIFICATION_REQUIRED
        return AccessStatus.PARTIAL
    except requests.ConnectionError as exc:
        err = str(exc).lower()
        if "connection aborted" in err or "10054" in err or "reset" in err:
            return AccessStatus.CONNECTION_RESET
        return AccessStatus.CONNECTION_RESET
    except requests.Timeout:
        return AccessStatus.CONNECTION_RESET
    except Exception as exc:
        logger.debug("probe_url failed [%s]: %s", url, exc)
        return AccessStatus.PARTIAL


def probe_html_for_verification(html: str) -> bool:
    if not html:
        return False
    lower = html.lower()
    return any(m in html or m in lower for m in VERIFICATION_MARKERS)


def merge_access_status(*statuses: AccessStatus) -> AccessStatus:
    """合并多次探测结果，取最严重（最不可达）状态。"""
    priority = (
        AccessStatus.VERIFICATION_REQUIRED,
        AccessStatus.WAF_BLOCKED,
        AccessStatus.CONNECTION_RESET,
        AccessStatus.UNSUPPORTED_ARCHIVE,
        AccessStatus.UNSUPPORTED_PDF,
        AccessStatus.PARTIAL,
        AccessStatus.AVAILABLE,
    )
    if not statuses:
        return AccessStatus.AVAILABLE
    for level in priority:
        if level in statuses:
            return level
    return statuses[0]


class SourceAdapter(ABC):
    """省份数据源适配器。"""

    source_type: SourceType

    def __init__(
        self,
        plugin: Any,
        *,
        default_status: AccessStatus | None = None,
    ) -> None:
        self.plugin = plugin
        self._default_status = default_status
        self._cached_status: AccessStatus | None = None

    @property
    def source_types(self) -> list[SourceType]:
        return [self.source_type]

    def discover(
        self,
        years: list[int],
        data_type: str | None = None,
        keyword: str | None = None,
        max_pages: int = 5,
    ) -> dict[int, list[dict[str, Any]]]:
        """发现公告数据源（委托 ProvincePlugin）。"""
        return self.plugin.discover(
            years=years,
            data_type=data_type,
            keyword=keyword,
            max_pages=max_pages,
        )

    def download(
        self,
        sources: list[dict[str, Any]],
        year: int,
        data_type: str,
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        """下载已发现公告的附件（委托现有 discovery 下载逻辑）。"""
        from crawlers.discovery import download_discovered_attachments

        crawler = self.plugin.get_crawler()
        return download_discovered_attachments(
            sources,
            year,
            data_type,
            force=force,
            crawler=crawler,
            province_slug=self.plugin.province_slug,
        )

    @abstractmethod
    def check_availability(self) -> AccessStatus:
        """在线探测官网可达性。"""

    def get_status(self) -> AccessStatus:
        """返回访问状态；若配置了静态 default 则优先使用（不把 WAF 当 bug）。"""
        if self._default_status is not None:
            return self._default_status
        if self._cached_status is not None:
            return self._cached_status
        self._cached_status = self.check_availability()
        return self._cached_status

    def enrich_source_entry(self, entry: dict[str, Any]) -> dict[str, Any]:
        """为发现结果附加标准 access_status。"""
        legacy = entry.get("access_status")
        entry["access_status"] = normalize_access_status(legacy).value
        return entry
