"""
江苏省教育考试院数据源自动发现（Phase 7.1 / 7.2）。

从招考信息列表页发现公告 → 提取附件 → 下载 → 可选入库。
支持江苏 2021–2024 多年份批量处理。
合规：尊重 robots、请求间隔、失败不崩溃；403 时提示手动兜底流程。
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import requests

from config import BASE_DIR, CLEANED_DIR, DEFAULT_PROVINCE, RAW_DIR
from crawlers.filename_utils import sanitize_filename
from crawlers.jiangsu import JiangsuCrawler
from crawlers.sources_registry import DATA_TYPES
from parsers.parse_html import extract_links

logger = logging.getLogger(__name__)

JSEE_INDEX_URLS = [
    "https://www.jseea.cn/webfile/index/index_zkxx/",
]

CONTROL_TITLE_KEYWORDS: list[str] = [
    "录取控制分数线",
    "第一阶段录取控制分数线",
    "招生第一阶段录取控制分数线",
]

CONTROL_TITLE_EXCLUSIONS: list[str] = [
    "投档线",
    "平行志愿",
    "征求志愿",
    "提前批次投档",
    "本科批次平行志愿",
    "专科批次平行志愿",
]

SCHOOL_COLUMN_MARKERS: tuple[str, ...] = (
    "院校代号",
    "院校名称",
    "院校代码",
    "学校代号",
    "专业组",
    "专业代码",
    "专业名称",
    "投档最低分",
    "分数线",
)

DISCOVERY_KEYWORDS: dict[str, list[str]] = {
    "control": list(CONTROL_TITLE_KEYWORDS),
    "rank": [
        "逐分段统计表",
        "逐分段",
        "分段统计",
        "一分一段",
        "高考成绩分段",
        "第一阶段逐分段",
    ],
    "school": [
        "普通类本科批次平行志愿投档线",
        "普通类专科批次平行志愿投档线",
        "专科批次平行志愿投档线",
        "本科提前批次投档线",
        "体育类本科批次平行志愿投档线",
        "体育类本科",
        "艺术类本科批次平行志愿投档线",
        "艺术类本科",
    ],
    "major": [
        "专业录取分数线",
        "专业录取情况",
    ],
}

DETAIL_PAGE_RE = re.compile(r"/index_zkxx/\d{4}-\d{2}-\d{2}/\d+\.html$", re.I)

# 中文年份（官网标题偶用）
YEAR_CHINESE_MAP: dict[int, str] = {
    2024: "二〇二四",
    2023: "二〇二三",
    2022: "二〇二二",
    2021: "二〇二一",
}

JIANGSU_DISCOVERY_YEARS = [2021, 2022, 2023, 2024]

DATA_ATTACHMENT_EXTENSIONS = {".xlsx", ".xls", ".pdf", ".rar", ".zip"}
CONTROL_EXTRA_EXTENSIONS = {".jpg", ".jpeg", ".png"}
NON_IMPORTABLE_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
UI_ASSET_MARKERS = ("icon-", "logo", "resource-", "print.png", "wx.jpg", "school-logo", "/images/")


def filter_data_attachments(
    attachments: list[dict[str, str]],
    data_type: str | None = None,
) -> list[dict[str, str]]:
    """过滤公告附件，保留数据文件，去掉站点图标。"""
    allowed = set(DATA_ATTACHMENT_EXTENSIONS)
    if data_type == "control":
        allowed |= CONTROL_EXTRA_EXTENSIONS

    filtered: list[dict[str, str]] = []
    seen: set[str] = set()

    for att in attachments:
        url = (att.get("url") or "").strip()
        title = att.get("title") or ""
        if not url or url in seen:
            continue

        path_lower = urlparse(url).path.lower()
        ext = Path(path_lower).suffix
        if ext not in allowed and "downfile.jsp" in url.lower():
            qs = parse_qs(urlparse(url).query)
            fn = unquote((qs.get("filename") or [""])[0])
            if fn.lower().endswith((".xls", ".xlsx")):
                ext = Path(fn).suffix.lower()
            elif qs.get("filename"):
                ext = ".xls"

        if any(marker in path_lower or marker in title.lower() for marker in UI_ASSET_MARKERS):
            continue
        if ext not in allowed:
            continue

        seen.add(url)
        filtered.append(att)

    return filtered

FORBIDDEN_HINT = (
    "官网返回 403 或拒绝 requests 访问。"
    "请使用兜底流程：浏览器保存 HTML → extract-attachments-local → "
    "download-attachment → import-excel"
)


def is_control_title(title: str) -> bool:
    """标题是否属于省控线公告（排除投档线等误匹配）。"""
    if any(ex in title for ex in CONTROL_TITLE_EXCLUSIONS):
        return False
    if "投档线" in title and "控制分数线" in title:
        return False
    return any(kw in title for kw in CONTROL_TITLE_KEYWORDS)


def classify_suggested_type(title: str) -> str:
    """根据公告标题推断数据类型。"""
    if any(k in title for k in ("逐分段", "一分一段", "分段统计", "高考成绩分段")):
        return "rank"
    if any(ex in title for ex in CONTROL_TITLE_EXCLUSIONS):
        if "投档线" in title:
            return "school"
        return "unknown"
    if "投档线" in title and "控制分数线" in title:
        return "school"
    if is_control_title(title):
        return "control"
    if any(
        k in title
        for k in (
            "体育类本科",
            "艺术类本科",
            "体育类本科批次",
            "艺术类本科批次",
            "投档线",
            "平行投档分数线",
            "投档情况表",
            "投档情况",
            "投档分数线表",
            "投档分数线",
            "正式投档",
        )
    ):
        return "school"
    if "专业录取" in title:
        return "major"
    return "unknown"


def collect_keywords(
    data_type: str | None = None,
    extra_keyword: str | None = None,
    plugin_keywords: dict[str, list[str]] | None = None,
) -> list[str]:
    """汇总发现用关键词列表；可传入插件级 discovery_keywords。"""
    source = plugin_keywords if plugin_keywords is not None else DISCOVERY_KEYWORDS
    keywords: list[str] = []
    if extra_keyword and extra_keyword.strip():
        keywords.append(extra_keyword.strip())
    if data_type and data_type in source:
        keywords.extend(source[data_type])
    elif not data_type:
        for dtype in DATA_TYPES:
            keywords.extend(source.get(dtype, []))
    return list(dict.fromkeys(keywords))


def match_keyword(title: str, keywords: list[str]) -> str | None:
    """返回标题中命中的第一个关键词。"""
    for kw in keywords:
        if kw in title:
            return kw
    return None


def infer_school_metadata_from_title(
    title: str,
    source_title: str | None = None,
) -> dict[str, str]:
    """
    从公告/附件标题推断 school 的 admission_category 与 batch。

    admission_category: 普通类 / 艺术类 / 体育类
    batch: 本科批 / 专科批 / 本科提前批
    """
    from normalizers.admission_category import normalize_admission_category
    from normalizers.school_batch import normalize_school_batch

    primary = title or ""
    context = source_title or ""
    text = " ".join(t for t in (context, primary) if t)

    # 附件名优先（避免「体育类、艺术类」合并公告误判）
    if "艺术类" in primary:
        admission_category = "艺术类"
    elif "体育类" in primary:
        admission_category = "体育类"
    elif "艺术类" in text:
        admission_category = "艺术类"
    elif "体育类" in text or ("体育" in text and "本科" in text):
        admission_category = "体育类"
    else:
        admission_category = "普通类"

    if "本科一批" in text:
        batch = "本科一批"
    elif "本科二批" in text:
        batch = "本科二批"
    elif "高职高专" in text:
        batch = "高职高专批"
    elif "第一段" in text:
        batch = "本科批"
    elif "第二段" in text:
        batch = "专科批"
    elif "第1次志愿" in text or "第1次" in text:
        batch = "本科批"
    elif "第2次志愿" in text or "第3次志愿" in text or "第2次" in text or "第3次" in text:
        batch = "专科批"
    elif "专科" in text and ("批次" in text or "批" in text):
        batch = "专科批"
    elif "提前" in text and "批" in text:
        batch = "本科提前批"
    elif "本科" in text:
        batch = "本科批"
    else:
        batch = "本科批"

    return {
        "admission_category": normalize_admission_category(admission_category) or "普通类",
        "batch": normalize_school_batch(batch) or "本科批",
    }


def infer_subject_type_from_title(
    title: str,
    *,
    legacy: bool = False,
) -> str | None:
    """
    从附件/公告标题或文件名推断科类。

    legacy=True（河南等）：文科 / 理科
    默认（江苏等新高考）：历史类 / 物理类
    """
    text = title or ""
    if legacy:
        if "文科" in text:
            return "文科"
        if "理科" in text:
            return "理科"
        return None
    if any(k in text for k in ("历史等科目", "历史类", "文科")):
        return "历史类"
    if any(k in text for k in ("物理等科目", "物理类", "理科")):
        return "物理类"
    if "历史" in text and "物理" not in text:
        return "历史类"
    if "物理" in text:
        return "物理类"
    return None


def resolve_discovery_years(year: int | None = None, years: list[int] | None = None) -> list[int]:
    """解析 CLI 年份参数；--years 优先于 --year。"""
    if years:
        return sorted(set(years))
    if year is not None:
        return [year]
    raise ValueError("需要指定 --year 或 --years")


def _build_index_page_url(base_url: str, page_num: int) -> str:
    base = base_url.rstrip("/")
    if page_num <= 1:
        return f"{base}/"
    return f"{base}/index_{page_num}.html"


def _is_detail_page_url(url: str) -> bool:
    return bool(DETAIL_PAGE_RE.search(urlparse(url).path))


def _announcement_matches_year(title: str, page_url: str, year: int) -> bool:
    """匹配阿拉伯数字或中文年份（如 二〇二四）。"""
    year_str = str(year)
    if year_str in title:
        return True
    chinese = YEAR_CHINESE_MAP.get(year)
    if chinese and chinese in title:
        return True
    path = urlparse(page_url).path
    return f"/{year_str}-" in path or f"/{year_str}/" in path


def _match_announcement_year(title: str, page_url: str, years: list[int]) -> int | None:
    """返回公告匹配的目标年份（首个命中）。"""
    for year in years:
        if _announcement_matches_year(title, page_url, year):
            return year
    return None


def _extract_pagination_urls(html: str, base_url: str, max_pages: int) -> list[str]:
    """从首页解析数字分页链接，生成待抓取列表页 URL。"""
    urls: list[str] = []
    seen: set[str] = set()

    for page_num in range(1, max_pages + 1):
        page_url = _build_index_page_url(base_url, page_num)
        if page_url not in seen:
            seen.add(page_url)
            urls.append(page_url)

    links = extract_links(html, base_url)
    for link in links:
        text = (link.get("text") or "").strip()
        href = link.get("url") or ""
        if not href:
            continue
        if text.isdigit():
            num = int(text)
            if 1 <= num <= max_pages:
                page_url = _build_index_page_url(base_url, num)
                if page_url not in seen:
                    seen.add(page_url)
                    urls.append(page_url)

    return urls[:max_pages]


def parse_announcements_from_index(
    html: str,
    base_url: str,
    years: list[int],
    keywords: list[str],
) -> list[dict[str, str]]:
    """从列表页 HTML 提取匹配年份与关键词的公告。"""
    results: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    for link in extract_links(html, base_url):
        title = (link.get("text") or "").strip()
        page_url = (link.get("url") or "").strip()
        if not title or not page_url:
            continue
        if not _is_detail_page_url(page_url):
            continue
        if page_url in seen_urls:
            continue

        matched_year = _match_announcement_year(title, page_url, years)
        if matched_year is None:
            continue

        matched_kw = match_keyword(title, keywords)
        if not matched_kw:
            continue

        seen_urls.add(page_url)
        results.append(
            {
                "title": title,
                "page_url": page_url,
                "matched_keyword": matched_kw,
                "year": matched_year,
            }
        )

    return results


def _scan_index_announcements(
    years: list[int],
    keywords: list[str],
    max_pages: int,
    crawler: JiangsuCrawler,
) -> tuple[list[dict[str, str]], bool]:
    """
    扫描招考信息列表页（一次遍历，支持多年份）。

    Returns:
        (公告列表, 是否遇到 403)
    """
    announcements: list[dict[str, str]] = []
    seen_detail_urls: set[str] = set()
    had_403 = False

    for index_url in JSEE_INDEX_URLS:
        try:
            html = crawler.fetch_page(index_url)
            index_pages = _extract_pagination_urls(html, index_url, max_pages)
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status == 403:
                had_403 = True
                logger.error("%s 列表页 HTTP 403: %s", index_url, FORBIDDEN_HINT)
            else:
                logger.error("列表页请求失败 [%s]: %s", index_url, exc)
            continue
        except (PermissionError, requests.RequestException) as exc:
            logger.error("列表页请求失败 [%s]: %s", index_url, exc)
            continue

        for page_url in index_pages:
            try:
                if page_url.rstrip("/") == index_url.rstrip("/"):
                    page_html = html
                else:
                    page_html = crawler.fetch_page(page_url)
                items = parse_announcements_from_index(page_html, page_url, years, keywords)
                for item in items:
                    if item["page_url"] in seen_detail_urls:
                        continue
                    seen_detail_urls.add(item["page_url"])
                    announcements.append(item)
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else None
                if status == 403:
                    had_403 = True
                logger.warning("分页抓取失败 [%s]: %s", page_url, exc)
            except (PermissionError, requests.RequestException) as exc:
                logger.warning("分页抓取失败 [%s]: %s", page_url, exc)

    return announcements, had_403


def discover_jiangsu_sources(
    years: list[int] | int,
    keywords: list[str],
    max_pages: int = 5,
    crawler: JiangsuCrawler | None = None,
) -> dict[int, list[dict[str, Any]]]:
    """
    从江苏省教育考试院招考信息列表页自动发现数据源。

    Returns:
        按年份分组的公告字典 {year: [source, ...]}。
    """
    if isinstance(years, int):
        years = [years]

    if not keywords:
        logger.warning("关键词列表为空，无法发现数据源")
        return {y: [] for y in years}

    crawler = crawler or JiangsuCrawler()
    announcements, had_403 = _scan_index_announcements(years, keywords, max_pages, crawler)

    by_year: dict[int, list[dict[str, Any]]] = {y: [] for y in years}
    seen_page_urls: set[str] = set()

    for item in announcements:
        page_url = item["page_url"]
        year = item["year"]
        if year not in by_year:
            continue
        if page_url in seen_page_urls:
            continue
        seen_page_urls.add(page_url)

        title = item["title"]
        attachments: list[dict[str, str]] = []
        try:
                raw_attachments = crawler.extract_attachment_links(page_url)
                attachments = filter_data_attachments(
                    raw_attachments,
                    data_type=classify_suggested_type(title),
                )
        except Exception as exc:
            logger.warning("提取附件失败 [%s]: %s", page_url, exc)

        school_meta = infer_school_metadata_from_title(title)
        by_year[year].append(
            {
                "year": year,
                "title": title,
                "page_url": page_url,
                "matched_keyword": item["matched_keyword"],
                "attachments": attachments,
                "suggested_type": classify_suggested_type(title),
                "admission_category": school_meta["admission_category"],
                "batch": school_meta["batch"],
            }
        )

    total = sum(len(v) for v in by_year.values())
    if had_403 and total == 0:
        logger.error(FORBIDDEN_HINT)

    logger.info(
        "发现 %d 条公告（years=%s, keywords=%d）",
        total,
        years,
        len(keywords),
    )
    return by_year


def filter_discovered_sources(
    sources: list[dict[str, Any]],
    data_type: str | None = None,
    extra_keyword: str | None = None,
) -> list[dict[str, Any]]:
    """按 suggested_type 严格过滤（Phase 7.4）。"""
    filtered = sources
    if data_type:
        filtered = [s for s in filtered if s.get("suggested_type") == data_type]
    if extra_keyword and extra_keyword.strip():
        kw = extra_keyword.strip()
        filtered = [s for s in filtered if kw in s.get("title", "")]
    return filtered


def _download_announcement_html(
    crawler: JiangsuCrawler,
    source: dict[str, Any],
    year: int,
    data_type: str,
    force: bool,
    province_slug: str = "jiangsu",
) -> dict[str, Any] | None:
    """下载公告正文 HTML（rank/control 用于 table 解析）。"""
    page_url = source.get("page_url")
    title = source.get("title") or "announcement"
    if not page_url:
        return None

    save_dir = RAW_DIR / province_slug / str(year) / data_type
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / sanitize_filename(title, ext=".html")

    record: dict[str, Any] = {
        "source_title": title,
        "page_url": page_url,
        "attachment_title": title,
        "url": page_url,
        "file_type": "html",
        "local_path": str(save_path.relative_to(BASE_DIR)),
        "status": "pending",
        "kind": "page_html",
        "importable": True,
    }

    if save_path.exists() and not force:
        record["status"] = "skipped"
        return record

    try:
        if not crawler._can_fetch(page_url):  # noqa: SLF001
            record["status"] = "failed"
            return record
        crawler._sleep()  # noqa: SLF001
        response = crawler.session.get(page_url, timeout=30)
        response.raise_for_status()
        response.encoding = response.apparent_encoding or "utf-8"
        save_path.write_text(response.text, encoding="utf-8")
        record["status"] = "downloaded"
        logger.info("公告 HTML 已保存: %s", save_path)
        return record
    except Exception as exc:
        logger.warning("公告 HTML 下载失败 [%s]: %s", page_url, exc)
        record["status"] = "failed"
        return record


def _records_for_extracted_archive(
    archive_path: Path,
    source: dict[str, Any],
    attach_dir: Path,
) -> list[dict[str, Any]]:
    """RAR/ZIP 解压后为每个子文件生成下载记录。"""
    from crawlers.archive_utils import extract_archive
    from importers.file_import import is_importable_file

    records: list[dict[str, Any]] = []
    for child in extract_archive(archive_path, dest_dir=attach_dir / archive_path.stem):
        rel = child.relative_to(BASE_DIR)
        records.append(
            {
                "source_title": source.get("title"),
                "page_url": source.get("page_url"),
                "attachment_title": child.name,
                "url": source.get("page_url"),
                "file_type": child.suffix.lstrip(".").lower() or "bin",
                "local_path": str(rel),
                "status": "downloaded",
                "kind": "extracted",
                "parent_archive": str(archive_path.relative_to(BASE_DIR)),
                "importable": is_importable_file(child),
            }
        )
    return records


def download_discovered_attachments(
    sources: list[dict[str, Any]],
    year: int,
    data_type: str,
    force: bool = False,
    crawler: JiangsuCrawler | None = None,
    province_slug: str = "jiangsu",
) -> dict[str, Any]:
    """
    下载已发现公告的附件。

    同一 attachment url 不重复下载；已存在文件默认跳过。
    control / rank 类型额外保存公告 HTML 页面。
    rank 无附件时仅保存 HTML；有附件时同时保存 HTML 与 Excel。
    """
    crawler = crawler or JiangsuCrawler()
    attach_dir = RAW_DIR / province_slug / str(year) / data_type / "attachments"
    attach_dir.mkdir(parents=True, exist_ok=True)

    seen_attachment_urls: set[str] = set()
    seen_page_urls: set[str] = set()
    downloads: list[dict[str, Any]] = []
    had_403 = False

    for source in sources:
        if source.get("access_status") == "unsupported_verification_required":
            downloads.append(
                {
                    "source_title": source.get("title"),
                    "page_url": source.get("page_url"),
                    "status": "unsupported_verification_required",
                    "kind": "source_blocked",
                    "importable": False,
                }
            )
            continue

        if data_type in ("control", "rank"):
            page_url = source.get("page_url")
            if page_url and page_url not in seen_page_urls:
                seen_page_urls.add(page_url)
                html_record = _download_announcement_html(
                    crawler, source, year, data_type, force, province_slug=province_slug
                )
                if html_record:
                    downloads.append(html_record)

        for att in source.get("attachments") or []:
            url = (att.get("url") or "").strip()
            if not url or url in seen_attachment_urls:
                continue
            seen_attachment_urls.add(url)

            title = att.get("title") or "attachment"
            file_type = att.get("file_type") or "xlsx"
            ext = f".{file_type}" if not file_type.startswith(".") else file_type
            save_path = attach_dir / sanitize_filename(title, ext=ext)

            ext_lower = save_path.suffix.lower()
            record: dict[str, Any] = {
                "source_title": source.get("title"),
                "page_url": source.get("page_url"),
                "attachment_title": title,
                "url": url,
                "file_type": file_type,
                "local_path": str(save_path.relative_to(BASE_DIR)),
                "status": "pending",
                "kind": "attachment",
                "importable": ext_lower not in NON_IMPORTABLE_EXTENSIONS
                and ext_lower not in {".rar", ".zip", ".doc"},
            }

            if save_path.exists() and not force:
                record["status"] = "skipped"
                record["local_path"] = str(save_path.relative_to(BASE_DIR))
                downloads.append(record)
                if save_path.suffix.lower() in {".rar", ".zip"}:
                    downloads.extend(
                        _records_for_extracted_archive(
                            save_path,
                            source,
                            attach_dir,
                        )
                    )
                logger.info("附件已存在，跳过: %s", save_path)
                continue

            path = crawler._download_attachment(  # noqa: SLF001 — 复用合规下载逻辑
                {"title": title, "url": url, "file_type": file_type},
                attach_dir,
                force=force,
                save_path=save_path,
            )
            if path is not None:
                record["status"] = "downloaded"
                record["local_path"] = str(path.relative_to(BASE_DIR))
                if path.suffix.lower() in {".rar", ".zip"}:
                    downloads.extend(
                        _records_for_extracted_archive(path, source, attach_dir)
                    )
            else:
                record["status"] = "failed"
                had_403 = True
            downloads.append(record)

    report = {
        "year": year,
        "data_type": data_type,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": sources,
        "downloads": downloads,
        "summary": {
            "downloaded": sum(1 for d in downloads if d["status"] == "downloaded"),
            "skipped": sum(1 for d in downloads if d["status"] == "skipped"),
            "failed": sum(1 for d in downloads if d["status"] == "failed"),
            "downloaded_not_imported": sum(
                1
                for d in downloads
                if d["status"] in ("downloaded", "skipped")
                and d.get("importable") is False
            ),
        },
    }
    if had_403:
        report["hint"] = FORBIDDEN_HINT
    return report


def save_discovery_report(
    report: dict[str, Any],
    year: int,
    data_type: str,
    province_slug: str = "jiangsu",
) -> Path:
    """保存单年 discovery JSON 报告。"""
    CLEANED_DIR.mkdir(parents=True, exist_ok=True)
    out = CLEANED_DIR / f"discovery_{province_slug}_{year}_{data_type}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("已保存 discovery 报告: %s", out)
    return out


def save_combined_discovery_report(
    years: list[int],
    data_type: str,
    reports_by_year: dict[int, dict[str, Any]],
    year_summaries: list[dict[str, Any]],
    province_slug: str = "jiangsu",
) -> Path:
    """保存多年份总报告 discovery_{slug}_{min}_{max}_{type}.json。"""
    CLEANED_DIR.mkdir(parents=True, exist_ok=True)
    min_y, max_y = min(years), max(years)
    out = CLEANED_DIR / f"discovery_{province_slug}_{min_y}_{max_y}_{data_type}.json"
    payload = {
        "years": years,
        "data_type": data_type,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "by_year": {str(y): reports_by_year.get(y, {}) for y in years},
        "summary": year_summaries,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("已保存多年份 discovery 总报告: %s", out)
    return out


def _build_year_summary(
    year: int,
    sources: list[dict[str, Any]],
    report: dict[str, Any] | None = None,
    import_summary: dict[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """构建单年汇总行。"""
    dl_summary = (report or {}).get("summary", {})
    imp = import_summary or {}
    return {
        "year": year,
        "discovered_pages": len(sources),
        "downloaded_files": dl_summary.get("downloaded", 0),
        "imported": len(imp.get("imported", [])),
        "skipped": len(imp.get("skipped", [])) + dl_summary.get("skipped", 0),
        "skipped_wrong_type": len(imp.get("skipped_wrong_type", [])),
        "failed": len(imp.get("failed", [])) + dl_summary.get("failed", 0),
        "downloaded_not_imported": len(imp.get("downloaded_not_imported", []))
        or dl_summary.get("downloaded_not_imported", 0),
        "error": error,
    }


def _file_looks_like_school_data(path: Path) -> bool:
    """根据表头判断 Excel 是否为院校投档线（误标为 control 时跳过）。"""
    from parsers.parse_excel import _read_raw_sheet, detect_header_row, list_excel_sheet_names

    if path.suffix.lower() not in {".xlsx", ".xls"}:
        return False
    try:
        sheet_names = list_excel_sheet_names(path)
        sheet_name = sheet_names[0] if sheet_names else 0
        df_raw = _read_raw_sheet(path, sheet_name)
        if df_raw.empty:
            return False
        header_row = detect_header_row(df_raw)
        header_text = " ".join(
            str(v)
            for v in df_raw.iloc[header_row].tolist()
            if v is not None and str(v).strip() and str(v).lower() != "nan"
        )
    except Exception:
        return False

    return any(marker in header_text for marker in SCHOOL_COLUMN_MARKERS)


def import_downloaded_files(
    report: dict[str, Any],
    year: int,
    province: str,
    data_type: str,
    session,
) -> dict[str, Any]:
    """根据下载结果调用 import-file pipeline。"""
    from importers.file_import import (
        UnsupportedImportFormatError,
        import_file_to_db,
        is_download_only_file,
        is_importable_file,
    )
    from parsers.import_debug import write_import_debug_preview

    imported: list[str] = []
    skipped: list[str] = []
    skipped_wrong_type: list[str] = []
    failed: list[str] = []
    downloaded_not_imported: list[str] = []
    errors_detail: list[dict[str, Any]] = []

    def _sort_key(item: dict[str, Any]) -> int:
        kind = item.get("kind")
        if kind == "attachment":
            return 0
        if kind == "page_html":
            return 1
        return 2

    # control / rank：优先 Excel 附件，再尝试公告 HTML
    items = list(report.get("downloads") or [])
    if data_type in ("control", "rank"):
        items.sort(key=_sort_key)

    for item in items:
        if item.get("status") == "unsupported_verification_required":
            continue
        if item.get("status") not in ("downloaded", "skipped"):
            if item.get("status") == "failed":
                failed.append(item.get("local_path") or item.get("url", ""))
            continue

        local_path = item.get("local_path")
        if not local_path:
            continue
        path = Path(local_path)
        if not path.is_absolute():
            path = BASE_DIR / path
        if not path.exists():
            failed.append(str(path))
            continue

        if item.get("importable") is False or is_download_only_file(path):
            downloaded_not_imported.append(str(path))
            logger.info("已下载但不导入（PDF/图片等）: %s", path)
            continue

        if not is_importable_file(path):
            skipped.append(str(path))
            logger.info("跳过不支持的导入格式: %s", path)
            continue

        if data_type == "control" and _file_looks_like_school_data(path):
            skipped_wrong_type.append(str(path))
            logger.info("跳过误分类为 control 的 school 文件: %s", path)
            continue

        subject_hint = (
            item.get("attachment_title")
            or item.get("source_title")
            or path.stem
            or path.name
        )
        from province_registry import get_province_plugin
        from provinces.base import SubjectMode

        plugin = get_province_plugin(province)
        legacy = plugin.subject_mode == SubjectMode.LEGACY
        subject_type = infer_subject_type_from_title(subject_hint, legacy=legacy)
        if not subject_type:
            subject_type = plugin.default_subject_type or None
        school_meta = (
            infer_school_metadata_from_title(
                subject_hint,
                source_title=item.get("source_title"),
            )
            if data_type == "school"
            else {}
        )

        def _record_error(msg: str) -> None:
            try:
                rel = str(path.relative_to(BASE_DIR))
            except ValueError:
                rel = str(path)
            debug_path = write_import_debug_preview(
                path,
                data_type,
                year,
                province,
                subject_type,
                error_message=msg,
            )
            errors_detail.append(
                {
                    "file_path": rel,
                    "error_message": msg,
                    "year": year,
                    "type": data_type,
                    "debug_preview": str(debug_path.relative_to(BASE_DIR)) if debug_path else None,
                }
            )

        try:
            stats = import_file_to_db(
                session,
                path,
                record_type=data_type,
                default_year=year,
                default_province=province,
                subject_type=subject_type,
                admission_category=school_meta.get("admission_category"),
                batch=school_meta.get("batch"),
                subject_mode=plugin.subject_mode,
                write_debug_on_failure=False,
            )
        except UnsupportedImportFormatError as exc:
            downloaded_not_imported.append(str(path))
            _record_error(str(exc))
            continue
        except Exception as exc:
            logger.error("导入失败 [%s]: %s", path, exc)
            failed.append(str(path))
            _record_error(str(exc))
            continue

        if stats.inserted > 0:
            imported.append(str(path))
        elif stats.failed > 0:
            failed.append(str(path))
            msg = "; ".join(stats.errors[:5]) if stats.errors else "校验或插入失败"
            _record_error(msg)
        elif stats.inserted == 0 and not stats.skipped:
            skipped.append(str(path))
            if stats.errors:
                _record_error("; ".join(stats.errors[:5]))
        else:
            skipped.append(str(path))

    return {
        "imported": imported,
        "skipped": skipped,
        "skipped_wrong_type": skipped_wrong_type,
        "failed": failed,
        "downloaded_not_imported": downloaded_not_imported,
        "errors_detail": errors_detail,
    }


def _filter_sources_by_year(
    by_year: dict[int, list[dict[str, Any]]],
    data_type: str | None,
    keyword: str | None,
) -> dict[int, list[dict[str, Any]]]:
    """对每年公告列表做类型/关键词过滤。"""
    return {
        year: filter_discovered_sources(sources, data_type=data_type, extra_keyword=keyword)
        for year, sources in by_year.items()
    }


def run_discover(
    years: list[int],
    province: str,
    data_type: str | None = None,
    keyword: str | None = None,
    max_pages: int = 5,
) -> dict[int, list[dict[str, Any]]]:
    """执行发现并按类型/关键词过滤，返回按年份分组结果。"""
    from province_registry import get_province_plugin

    plugin = get_province_plugin(province)
    return plugin.discover(
        years=years,
        data_type=data_type,
        keyword=keyword,
        max_pages=max_pages,
    )


def run_discover_and_download(
    years: list[int],
    province: str,
    data_type: str,
    keyword: str | None = None,
    max_pages: int = 5,
    force: bool = False,
) -> tuple[dict[int, Path], Path | None]:
    """
    多年份发现 → 下载 → 保存每年报告 + 总报告。

    Returns:
        (每年报告路径, 总报告路径或 None)
    """
    from province_registry import get_province_plugin

    plugin = get_province_plugin(province)
    province_slug = plugin.province_slug
    crawler = plugin.get_crawler()

    by_year = run_discover(years, province, data_type, keyword, max_pages)
    reports_by_year: dict[int, dict[str, Any]] = {}
    report_paths: dict[int, Path] = {}
    year_summaries: list[dict[str, Any]] = []

    for year in years:
        sources = by_year.get(year, [])
        try:
            if not sources:
                logger.warning("[%s] 未发现匹配数据源，仍将写入空报告", year)
            report = download_discovered_attachments(
                sources,
                year,
                data_type,
                force=force,
                crawler=crawler,
                province_slug=province_slug,
            )
            reports_by_year[year] = report
            report_paths[year] = save_discovery_report(
                report, year, data_type, province_slug=province_slug
            )
            year_summaries.append(_build_year_summary(year, sources, report))
        except Exception as exc:
            logger.error("[%s] 下载失败: %s", year, exc)
            year_summaries.append(
                _build_year_summary(year, sources, error=str(exc))
            )

    combined_path: Path | None = None
    if len(years) > 1:
        combined_path = save_combined_discovery_report(
            years, data_type, reports_by_year, year_summaries, province_slug=province_slug
        )
    elif len(years) == 1:
        combined_path = report_paths.get(years[0])

    return report_paths, combined_path


def run_discover_only(
    years: list[int],
    province: str,
    data_type: str,
    keyword: str | None = None,
    max_pages: int = 5,
) -> dict[str, Any]:
    """仅发现公告，不下载、不导入（dry-run）。"""
    by_year = run_discover(years, province, data_type, keyword, max_pages)
    year_summaries = [
        _build_year_summary(year, by_year.get(year, []))
        for year in years
    ]
    return {
        "dry_run": True,
        "data_type": data_type,
        "summary": year_summaries,
        "discovered_total": sum(len(v) for v in by_year.values()),
    }


def run_discover_download_import(
    years: list[int],
    province: str,
    data_type: str,
    keyword: str | None = None,
    max_pages: int = 5,
    force: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """多年份发现 → 下载 → 入库；单年失败不影响其他年份。"""
    from db.database import SessionLocal

    if dry_run:
        return run_discover_only(years, province, data_type, keyword, max_pages)

    report_paths, combined_path = run_discover_and_download(
        years, province, data_type, keyword, max_pages, force
    )
    from province_registry import get_province_plugin

    plugin = get_province_plugin(province)
    province_norm = plugin.province_name
    province_slug = plugin.province_slug

    year_summaries: list[dict[str, Any]] = []
    hints: list[str] = []
    reports_by_year: dict[int, dict[str, Any]] = {}
    import_errors: list[dict[str, Any]] = []

    for year in years:
        path = report_paths.get(year)
        try:
            if path is None or not path.exists():
                year_summaries.append(
                    _build_year_summary(year, [], error="报告文件未生成")
                )
                continue

            report = json.loads(path.read_text(encoding="utf-8"))
            reports_by_year[year] = report
            if report.get("hint"):
                hints.append(report["hint"])

            session = SessionLocal()
            try:
                import_summary = import_downloaded_files(
                    report, year, province_norm, data_type, session
                )
            finally:
                session.close()

            import_errors.extend(import_summary.get("errors_detail") or [])
            year_summaries.append(
                _build_year_summary(year, report.get("sources") or [], report, import_summary)
            )
        except Exception as exc:
            logger.error("[%s] 导入失败: %s", year, exc)
            year_summaries.append(_build_year_summary(year, [], error=str(exc)))

    if len(years) > 1:
        combined_path = save_combined_discovery_report(
            years, data_type, reports_by_year, year_summaries, province_slug=province_slug
        )

    result: dict[str, Any] = {
        "data_type": data_type,
        "combined_report_path": str(combined_path) if combined_path else None,
        "year_reports": {str(y): str(p) for y, p in report_paths.items()},
        "summary": year_summaries,
        "import_errors": import_errors,
    }
    if hints:
        result["hint"] = hints[0]
    return result
