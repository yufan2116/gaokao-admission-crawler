"""爬虫模块。"""

from crawlers.jiangsu import (
    JIANGSU_LEGACY_INDEX,
    JIANGSU_SOURCES,
    JiangsuCrawler,
    check_sources_status,
    extract_attachment_links,
    extract_attachment_links_from_html_file,
    iter_jiangsu_sources,
    resolve_province_crawler,
)

__all__ = [
    "JiangsuCrawler",
    "JIANGSU_SOURCES",
    "JIANGSU_LEGACY_INDEX",
    "check_sources_status",
    "iter_jiangsu_sources",
    "extract_attachment_links",
    "extract_attachment_links_from_html_file",
    "resolve_province_crawler",
]
