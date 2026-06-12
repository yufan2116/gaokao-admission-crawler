"""河南省数据源发现（Phase 11）：seed + henanjk 详情页 ID 扫描。"""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.parse import urlparse

import requests

from config import DEFAULT_HEADERS
from crawlers.discovery import YEAR_CHINESE_MAP, collect_keywords, match_keyword
from crawlers.generic_discovery import _build_source_entry, _match_announcement_year
from crawlers.http_crawler import HttpProvinceCrawler
from provinces.base import ProvincePlugin

logger = logging.getLogger(__name__)


def _announcement_matches_year(title: str, page_url: str, year: int) -> bool:
    year_str = str(year)
    if year_str in title:
        return True
    chinese = YEAR_CHINESE_MAP.get(year)
    if chinese and chinese in title:
        return True
    path = urlparse(page_url).path
    return f"/{year_str}-" in path or f"/{year_str}/" in path


def _fetch_show_page(page_id: int) -> tuple[int, str, str] | None:
    url = f"https://www.henanjk.com/show.asp?id={page_id}&tb=xw&ut=0"
    try:
        response = requests.get(url, headers=DEFAULT_HEADERS, timeout=12)
        if response.status_code != 200:
            return None
        response.encoding = "gbk"
        html = response.text
        title_m = re.search(r"<title>([^<]+)</title>", html, re.I)
        title = (title_m.group(1) if title_m else "").strip()
        if not title:
            return None
        return page_id, title, url
    except requests.RequestException:
        return None


def _scan_henanjk_ids(
    years: list[int],
    keywords: list[str],
    start_id: int,
    scan_count: int,
) -> list[dict[str, Any]]:
    """并行扫描 henanjk show.asp?id= 公告。"""
    end_id = start_id + max(1, scan_count)
    found: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(_fetch_show_page, pid): pid for pid in range(start_id, end_id)}
        for future in as_completed(futures):
            result = future.result()
            if result is None:
                continue
            _page_id, title, page_url = result
            if page_url in seen_urls:
                continue
            matched_year = _match_announcement_year(title, page_url, years)
            if matched_year is None:
                continue
            matched_kw = match_keyword(title, keywords)
            if not matched_kw:
                continue
            seen_urls.add(page_url)
            found.append(
                {
                    "title": title,
                    "page_url": page_url,
                    "matched_keyword": matched_kw,
                    "year": matched_year,
                }
            )
    logger.info("henanjk ID 扫描 [%d,%d) 命中 %d 条", start_id, end_id, len(found))
    return found


def discover_henan_sources(
    plugin: ProvincePlugin,
    years: list[int],
    keywords: list[str],
    max_pages: int = 5,
    crawler: HttpProvinceCrawler | None = None,
) -> dict[int, list[dict[str, Any]]]:
    """河南发现：seed_announcements + ID 范围扫描。"""
    from provinces.henan import config as henan_config

    crawler = crawler or plugin.get_crawler()
    if crawler is None:
        raise ValueError(f"{plugin.province_name} 未提供爬虫实现")

    by_year: dict[int, list[dict[str, Any]]] = {y: [] for y in years}
    raw_items: list[dict[str, Any]] = []

    for year, seeds in getattr(plugin, "seed_announcements", {}).items():
        if year not in years:
            continue
        for seed in seeds:
            title = seed.get("title") or ""
            page_url = seed.get("page_url") or ""
            if not page_url:
                continue
            matched_kw = match_keyword(title, keywords) or (keywords[0] if keywords else "")
            raw_items.append(
                {
                    "title": title,
                    "page_url": page_url,
                    "matched_keyword": matched_kw,
                    "year": year,
                }
            )

    scan_width = henan_config.DISCOVERY_ID_SCAN_WIDTH_PER_PAGE * max(1, max_pages)
    raw_items.extend(
        _scan_henanjk_ids(
            years,
            keywords,
            henan_config.DISCOVERY_ID_SCAN_START,
            scan_width,
        )
    )

    seen_page_urls: set[str] = set()
    for item in raw_items:
        page_url = item["page_url"]
        year = item["year"]
        if year not in by_year or page_url in seen_page_urls:
            continue
        seen_page_urls.add(page_url)
        by_year[year].append(_build_source_entry(item, crawler))

    total = sum(len(v) for v in by_year.values())
    logger.info(
        "发现 %d 条公告（province=%s, years=%s）",
        total,
        plugin.province_name,
        years,
    )
    return by_year


def discover_via_henan_plugin(
    plugin: ProvincePlugin,
    years: list[int],
    data_type: str | None = None,
    keyword: str | None = None,
    max_pages: int = 5,
) -> dict[int, list[dict[str, Any]]]:
    """河南插件发现 + 类型过滤。"""
    from crawlers.discovery import filter_discovered_sources

    keywords = collect_keywords(data_type, keyword, plugin.discovery_keywords)
    by_year = discover_henan_sources(plugin, years, keywords, max_pages=max_pages)
    return {
        year: filter_discovered_sources(sources, data_type=data_type, extra_keyword=keyword)
        for year, sources in by_year.items()
    }
