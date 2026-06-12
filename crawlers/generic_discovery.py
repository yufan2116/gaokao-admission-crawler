"""
通用省份数据源发现（Phase 10）。

根据 ProvincePlugin 配置扫描列表页 / 嵌入记录 / seed URL，不复制江苏专用逻辑。
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

from crawlers.discovery import (
    FORBIDDEN_HINT,
    YEAR_CHINESE_MAP,
    classify_suggested_type,
    collect_keywords,
    filter_data_attachments,
    filter_discovered_sources,
    infer_school_metadata_from_title,
    match_keyword,
)
from crawlers.http_crawler import HttpProvinceCrawler
from provinces.base import ProvincePlugin

logger = logging.getLogger(__name__)

VERIFICATION_MARKERS = ("验证码", "captcha", "人机验证", "安全验证")
DATACENTER_HOST = "datacenter.haeea.cn"


def _page_requires_verification(html: str) -> bool:
    if not html:
        return False
    lower = html.lower()
    return any(marker in html or marker in lower for marker in VERIFICATION_MARKERS)


def _is_datacenter_query_url(url: str) -> bool:
    return DATACENTER_HOST in (url or "").lower()


def _page_has_datacenter_links(html: str) -> bool:
    return DATACENTER_HOST in (html or "")


def _assess_source_access(
    page_url: str,
    html: str,
    attachments: list[dict[str, str]],
) -> str:
    """
    评估公告是否可自动导入。

    无公开附件且指向数据中心查询页/验证码页 → unsupported_verification_required
    """
    if attachments:
        return "ok"
    if _is_datacenter_query_url(page_url):
        return "unsupported_verification_required"
    if not html:
        return "ok"
    if _page_requires_verification(html):
        return "unsupported_verification_required"
    if _page_has_datacenter_links(html) and any(
        kw in html for kw in ("投档", "平行投档", "投档分数线")
    ):
        return "unsupported_verification_required"
    return "ok"


def _announcement_matches_year(title: str, page_url: str, year: int) -> bool:
    year_str = str(year)
    if year_str in title:
        return True
    chinese = YEAR_CHINESE_MAP.get(year)
    if chinese and chinese in title:
        return True
    path = urlparse(page_url).path
    return f"/{year_str}-" in path or f"/{year_str}/" in path or f"/{year_str}/" in title


def _match_announcement_year(title: str, page_url: str, years: list[int]) -> int | None:
    for year in years:
        if _announcement_matches_year(title, page_url, year):
            return year
    return None


def _parse_zj_embedded_records(html: str, base_url: str) -> list[dict[str, str]]:
    """解析浙江 col 页嵌入的 jpage recordset CDATA。"""
    results: list[dict[str, str]] = []
    seen: set[str] = set()
    for block in re.findall(r"<record><!\[CDATA\[(.*?)\]\]></record>", html, re.S):
        href_m = re.search(r'href="([^"]+)"', block)
        title_m = re.search(r'title="([^"]+)"', block)
        if not href_m:
            continue
        href = href_m.group(1).strip()
        if href.lower().startswith("javascript:") or "weixin.qq.com" in href:
            continue
        page_url = urljoin(base_url, href)
        if page_url in seen:
            continue
        seen.add(page_url)
        title = (title_m.group(1) if title_m else "").strip() or page_url
        results.append({"title": title, "page_url": page_url})
    return results


def _parse_html_list_links(
    html: str,
    base_url: str,
    years: list[int],
    keywords: list[str],
    detail_url_checker,
) -> list[dict[str, Any]]:
    """从普通 HTML 列表页提取公告链接。"""
    from parsers.parse_html import extract_links

    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for link in extract_links(html, base_url):
        title = (link.get("text") or "").strip()
        page_url = (link.get("url") or "").strip()
        if not title or not page_url or page_url in seen:
            continue
        if not detail_url_checker(page_url):
            continue
        matched_year = _match_announcement_year(title, page_url, years)
        if matched_year is None:
            continue
        matched_kw = match_keyword(title, keywords)
        if not matched_kw:
            continue
        seen.add(page_url)
        found.append(
            {
                "title": title,
                "page_url": page_url,
                "matched_keyword": matched_kw,
                "year": matched_year,
            }
        )
    return found


def _build_source_entry(item: dict[str, Any], crawler: HttpProvinceCrawler) -> dict[str, Any]:
    title = item["title"]
    page_url = item["page_url"]
    year = item["year"]
    attachments: list[dict[str, str]] = []
    access_status = "ok"
    page_html = ""
    try:
        page_html = crawler.fetch_page(page_url)
        from crawlers.jiangsu import _extract_attachments_from_html

        raw_attachments = _extract_attachments_from_html(page_html, page_url)
        suggested = classify_suggested_type(title)
        attachments = filter_data_attachments(raw_attachments, data_type=suggested)
        access_status = _assess_source_access(page_url, page_html, attachments)
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status in (403, 412):
            access_status = "unsupported_verification_required"
        logger.warning("提取附件失败 [%s]: %s", page_url, exc)
    except Exception as exc:
        logger.warning("提取附件失败 [%s]: %s", page_url, exc)

    school_meta = infer_school_metadata_from_title(title)
    return {
        "year": year,
        "title": title,
        "page_url": page_url,
        "matched_keyword": item.get("matched_keyword", ""),
        "attachments": attachments,
        "suggested_type": classify_suggested_type(title),
        "admission_category": school_meta["admission_category"],
        "batch": school_meta["batch"],
        "access_status": access_status,
    }


def discover_plugin_sources(
    plugin: ProvincePlugin,
    years: list[int],
    keywords: list[str],
    max_pages: int = 5,
    crawler: HttpProvinceCrawler | None = None,
) -> dict[int, list[dict[str, Any]]]:
    """按插件配置发现数据源。"""
    if not keywords:
        logger.warning("关键词列表为空，无法发现数据源")
        return {y: [] for y in years}

    crawler = crawler or plugin.get_crawler()
    if crawler is None:
        raise ValueError(f"{plugin.province_name} 未提供爬虫实现")

    strategy = getattr(plugin, "discovery_strategy", "html_list")
    by_year: dict[int, list[dict[str, Any]]] = {y: [] for y in years}
    raw_items: list[dict[str, Any]] = []
    had_403 = False

    # seed 公告（历史年份兜底，如浙江 dataproxy 不可用）
    for year, seeds in getattr(plugin, "seed_announcements", {}).items():
        if year not in years:
            continue
        for seed in seeds:
            title = seed.get("title") or ""
            page_url = seed.get("page_url") or ""
            if not page_url:
                continue
            matched_kw = match_keyword(title, keywords) or keywords[0]
            raw_items.append(
                {
                    "title": title,
                    "page_url": page_url,
                    "matched_keyword": matched_kw,
                    "year": year,
                }
            )

    if strategy == "html_list":
        checker = getattr(plugin, "is_detail_page_url", lambda u: True)
        for index_url in plugin.index_urls[: max(1, max_pages)]:
            try:
                html = crawler.fetch_page(index_url)
                raw_items.extend(_parse_html_list_links(html, index_url, years, keywords, checker))
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else None
                if status == 403:
                    had_403 = True
                logger.error("列表页请求失败 [%s]: %s", index_url, exc)
            except (PermissionError, requests.RequestException) as exc:
                logger.error("列表页请求失败 [%s]: %s", index_url, exc)

    elif strategy == "zj_col":
        checker = getattr(plugin, "is_detail_page_url", lambda u: "/art/" in u)
        for index_url in plugin.index_urls:
            try:
                html = crawler.fetch_page(index_url)
                for rec in _parse_zj_embedded_records(html, index_url):
                    matched_year = _match_announcement_year(rec["title"], rec["page_url"], years)
                    if matched_year is None:
                        continue
                    matched_kw = match_keyword(rec["title"], keywords)
                    if not matched_kw:
                        continue
                    raw_items.append(
                        {
                            **rec,
                            "matched_keyword": matched_kw,
                            "year": matched_year,
                        }
                    )
                raw_items.extend(
                    _parse_html_list_links(html, index_url, years, keywords, checker)
                )
            except Exception as exc:
                logger.error("浙江 col 扫描失败 [%s]: %s", index_url, exc)

    seen_page_urls: set[str] = set()
    for item in raw_items:
        page_url = item["page_url"]
        year = item["year"]
        if year not in by_year or page_url in seen_page_urls:
            continue
        seen_page_urls.add(page_url)
        by_year[year].append(_build_source_entry(item, crawler))

    total = sum(len(v) for v in by_year.values())
    if had_403 and total == 0:
        logger.error(FORBIDDEN_HINT)
    logger.info(
        "发现 %d 条公告（province=%s, years=%s）",
        total,
        plugin.province_name,
        years,
    )
    return by_year


def discover_via_plugin(
    plugin: ProvincePlugin,
    years: list[int],
    data_type: str | None = None,
    keyword: str | None = None,
    max_pages: int = 5,
) -> dict[int, list[dict[str, Any]]]:
    """插件发现 + 类型过滤。"""
    keywords = collect_keywords(data_type, keyword, plugin.discovery_keywords)
    by_year = discover_plugin_sources(plugin, years, keywords, max_pages=max_pages)
    return {
        year: filter_discovered_sources(sources, data_type=data_type, extra_keyword=keyword)
        for year, sources in by_year.items()
    }
