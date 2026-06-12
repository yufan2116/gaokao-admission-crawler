"""
HTML 解析工具：提取页面链接及可下载资源链接。
"""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

# 常见数据文件扩展名
DOWNLOAD_EXTENSIONS = (".xlsx", ".xls", ".pdf", ".csv", ".zip")


def extract_links(html: str, base_url: str) -> list[dict]:
    """
    从 HTML 中提取所有 <a> 链接。

    Returns:
        [{"url": 绝对URL, "text": 链接文本}, ...]
    """
    soup = BeautifulSoup(html, "lxml")
    results: list[dict] = []

    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if not href or href.startswith("#") or href.lower().startswith("javascript:"):
            continue

        absolute_url = urljoin(base_url, href)
        text = tag.get_text(strip=True)
        results.append({"url": absolute_url, "text": text})

    return results


def extract_download_links(html: str, base_url: str) -> list[dict]:
    """
    从 HTML 中提取 Excel/PDF 等可下载文件链接。

    匹配规则：
    - href 以指定扩展名结尾
    - 或链接文本中包含「下载」「excel」「xlsx」「pdf」等关键词

    Returns:
        [{"url", "text", "ext"}, ...]
    """
    all_links = extract_links(html, base_url)
    download_links: list[dict] = []
    keyword_pattern = re.compile(r"下载|excel|xlsx|xls|pdf|投档|录取|一分一段", re.I)

    seen_urls: set[str] = set()
    for link in all_links:
        url = link["url"]
        if url in seen_urls:
            continue

        path = urlparse(url).path.lower()
        ext = _match_extension(path)
        text = link.get("text", "")

        if ext or keyword_pattern.search(text) or keyword_pattern.search(path):
            if not ext:
                ext = _match_extension(path) or ".xlsx"
            download_links.append({"url": url, "text": text, "ext": ext})
            seen_urls.add(url)

    return download_links


def _match_extension(path: str) -> str | None:
    """匹配路径中的文件扩展名。"""
    for ext in DOWNLOAD_EXTENSIONS:
        if path.endswith(ext):
            return ext
    return None


# Phase 7.3：HTML 表格解析（省控线）
from parsers.parse_html_tables import parse_html_tables  # noqa: E402

__all__ = [
    "extract_links",
    "extract_download_links",
    "parse_html_tables",
]
