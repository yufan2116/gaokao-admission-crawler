"""
江苏省高考录取数据爬虫。

Phase 2：按 JIANGSU_SOURCES 下载官方数据源。
Phase 2.1：从 HTML 公告页提取并下载附件（xlsx/xls/pdf/jpg 等）。
Phase 2.2：本地 HTML 解析 + 手动配置 attachments 直链（403 合规降级）。
"""

from __future__ import annotations

import logging
import mimetypes
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

from config import DEFAULT_HEADERS, DEFAULT_PROVINCE, DEFAULT_YEARS, RAW_DIR, REQUEST_DELAY, REQUEST_TIMEOUT
from crawlers.filename_utils import sanitize_filename
from crawlers.sources_registry import (
    DATA_TYPES,
    JIANGSU_LEGACY_INDEX,
    JIANGSU_SOURCES,
    check_sources_status,
    get_jiangsu_year_config,
    iter_jiangsu_sources,
)
from parsers.parse_html import extract_download_links

logger = logging.getLogger(__name__)

__all__ = [
    "JiangsuCrawler",
    "JIANGSU_SOURCES",
    "JIANGSU_LEGACY_INDEX",
    "DATA_TYPES",
    "check_sources_status",
    "iter_jiangsu_sources",
    "extract_attachment_links",
    "extract_attachment_links_from_html_file",
]

# 页面内可提取的附件后缀
ATTACHMENT_EXTENSIONS = (".xlsx", ".xls", ".pdf", ".rar", ".zip", ".jpg", ".jpeg", ".png")

# 可直接下载的配置 type
DIRECT_FILE_TYPES = {"xlsx", "xls", "pdf", "rar", "zip", "jpg", "jpeg", "png", "excel"}

_CONTENT_TYPE_EXT = {
    "text/html": ".html",
    "application/pdf": ".pdf",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}


def _suffix_to_file_type(suffix: str) -> str:
    """扩展名 → file_type 字符串（不含点）。"""
    s = suffix.lower()
    if s == ".jpeg":
        return "jpg"
    return s.lstrip(".")


def _file_type_to_suffix(file_type: str) -> str:
    """file_type → 扩展名。"""
    mapping = {
        "xlsx": ".xlsx",
        "xls": ".xls",
        "pdf": ".pdf",
        "jpg": ".jpg",
        "jpeg": ".jpg",
        "png": ".png",
        "rar": ".rar",
        "zip": ".zip",
        "excel": ".xlsx",
        "html": ".html",
    }
    return mapping.get(file_type.lower(), f".{file_type}")


def _is_configured_url(url: str | None) -> bool:
    """判断 URL 是否已配置（非空且非 TODO 占位）。"""
    if not url:
        return False
    text = url.strip()
    return bool(text) and text.upper() != "TODO"


def _read_html_file(html_path: Path) -> str:
    """读取本地 HTML，尝试常见中文编码。"""
    for encoding in ("utf-8", "utf-8-sig", "gbk", "gb2312"):
        try:
            return html_path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return html_path.read_text(encoding="utf-8", errors="replace")


def _extract_attachments_from_html(html: str, base_url: str) -> list[dict[str, str]]:
    """从 HTML 文本中提取附件链接（共用解析逻辑）。"""
    soup = BeautifulSoup(html, "lxml")
    results: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    for tag in soup.find_all(["a", "img"]):
        attr = "href" if tag.name == "a" else "src"
        raw_href = tag.get(attr)
        if not raw_href:
            continue

        href = raw_href.strip()
        if href.lower().startswith("javascript:"):
            continue

        absolute_url = urljoin(base_url, href)
        path_lower = urlparse(absolute_url).path.lower()

        matched_ext: str | None = None
        for ext in ATTACHMENT_EXTENSIONS:
            if path_lower.endswith(ext):
                matched_ext = ext
                break
        if not matched_ext and "downfile.jsp" in absolute_url.lower():
            qs = parse_qs(urlparse(absolute_url).query)
            fn = unquote((qs.get("filename") or [""])[0])
            showname = unquote((qs.get("showname") or [""])[0])
            for candidate in (fn, showname):
                if candidate.lower().endswith((".xls", ".xlsx")):
                    matched_ext = Path(candidate).suffix.lower()
                    break
            if not matched_ext and qs.get("filename"):
                matched_ext = ".xls"
        if not matched_ext:
            continue

        if absolute_url in seen_urls:
            continue
        seen_urls.add(absolute_url)

        title = tag.get_text(strip=True) if tag.name == "a" else ""
        if not title:
            title = Path(urlparse(absolute_url).path).name or "attachment"

        results.append(
            {
                "title": title,
                "url": absolute_url,
                "file_type": _suffix_to_file_type(matched_ext),
            }
        )

    return results


class JiangsuCrawler:
    """江苏省录取数据爬虫。"""

    def __init__(
        self,
        years: list[int] | None = None,
        raw_dir: Path | None = None,
        delay: float = REQUEST_DELAY,
    ) -> None:
        self.province = DEFAULT_PROVINCE
        self.years = years or DEFAULT_YEARS
        self.raw_dir = raw_dir or RAW_DIR
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self.base_url = JIANGSU_LEGACY_INDEX["base_url"]
        self.admission_index = JIANGSU_LEGACY_INDEX["admission_index"]
        self.raw_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Phase 2.1：HTML 附件提取
    # ------------------------------------------------------------------ #

    def extract_attachment_links(self, page_url: str) -> list[dict[str, str]]:
        """
        从 HTML 页面提取附件链接。

        Returns:
            [{"title", "url", "file_type"}, ...]
        """
        try:
            html = self.fetch_page(page_url)
        except PermissionError as exc:
            logger.error("提取附件失败 [%s]: %s", page_url, exc)
            return []
        except requests.RequestException as exc:
            logger.error("提取附件失败 [%s]: %s", page_url, exc)
            return []
        except Exception as exc:
            logger.error("提取附件失败 [%s]: %s", page_url, exc)
            return []

        results = _extract_attachments_from_html(html, page_url)
        logger.info("从 %s 提取到 %d 个附件链接", page_url, len(results))
        return results

    def extract_attachment_links_from_html_file(
        self,
        html_path: str | Path,
        base_url: str,
    ) -> list[dict[str, str]]:
        """
        从本地 HTML 文件提取附件链接（无需在线请求页面）。

        Args:
            html_path: 本地 HTML 路径
            base_url: 原公告页 URL，用于 urljoin 相对链接

        Returns:
            [{"title", "url", "file_type"}, ...]
        """
        path = Path(html_path)
        try:
            if not path.exists():
                logger.error("HTML 文件不存在: %s", path)
                return []
            if not base_url.strip().startswith("http"):
                logger.error("base_url 必须是有效的 HTTP(S) 地址: %s", base_url)
                return []

            html = _read_html_file(path)
            results = _extract_attachments_from_html(html, base_url.strip())
            logger.info("从本地文件 %s 提取到 %d 个附件链接", path, len(results))
            return results
        except OSError as exc:
            logger.error("读取 HTML 文件失败 [%s]: %s", path, exc)
            return []
        except Exception as exc:
            logger.error("解析 HTML 文件失败 [%s]: %s", path, exc)
            return []

    # ------------------------------------------------------------------ #
    # Phase 2：数据源列表与下载
    # ------------------------------------------------------------------ #

    def list_sources(self, year: int, data_type: str | None = None) -> list[dict[str, Any]]:
        """列出指定年份（及可选类型）的配置数据源。"""
        return iter_jiangsu_sources(year, data_type)

    def download_configured_sources(
        self,
        year: int,
        data_type: str,
        force: bool = False,
    ) -> list[Path]:
        """从 JIANGSU_SOURCES 下载指定类型或 all 的全部数据源。"""
        if data_type == "all":
            saved: list[Path] = []
            for dtype in DATA_TYPES:
                saved.extend(self.download_configured_sources(year, dtype, force=force))
            return saved

        if data_type not in DATA_TYPES:
            raise ValueError(f"不支持的数据类型: {data_type}，可选: {', '.join(DATA_TYPES)}, all")

        entries = iter_jiangsu_sources(year, data_type)
        if not entries:
            logger.warning("未找到 [%s][%s] 的数据源配置", year, data_type)
            return []

        saved_paths: list[Path] = []
        for entry in entries:
            paths = self._download_single_source(entry, force=force)
            saved_paths.extend(paths)

        logger.info(
            "[%s][%s] 下载完成: 共 %d 个文件 / 配置 %d 条",
            year,
            data_type,
            len(saved_paths),
            len(entries),
        )
        return saved_paths

    def _download_single_source(self, entry: dict[str, Any], force: bool = False) -> list[Path]:
        """下载单个配置项；url 为空则跳过。"""
        url = (entry.get("url") or "").strip()
        title = entry.get("title") or "untitled"
        year = entry.get("year")
        data_type = entry.get("data_type", "unknown")
        file_type = (entry.get("file_type") or "html_or_excel_or_pdf").lower()
        attachments = entry.get("attachments")

        save_dir = self.raw_dir / "jiangsu" / str(year) / data_type
        save_dir.mkdir(parents=True, exist_ok=True)

        # Phase 2.2：若配置了 attachments，跳过在线 HTML 提取，直接下载直链
        if attachments is not None:
            return self._download_configured_attachments(
                entry=entry,
                attachments=attachments,
                save_dir=save_dir,
                force=force,
            )

        if not url:
            logger.warning("[%s][%s] URL 未配置，跳过: %s", year, data_type, title)
            return []

        try:
            if file_type == "html":
                return self._download_html_with_attachments(
                    url=url,
                    title=title,
                    save_dir=save_dir,
                    force=force,
                )

            if file_type in DIRECT_FILE_TYPES or file_type == "html_or_excel_or_pdf":
                ext = self._resolve_extension(url, file_type)
                filename = sanitize_filename(title, ext=ext)
                save_path = save_dir / filename

                if save_path.exists() and not force:
                    logger.info("文件已存在，跳过: %s", save_path)
                    return [save_path]

                if ext == ".html":
                    path = self._save_html(url, save_path)
                    return [path]

                path = self._save_binary(url, save_path, file_type)
                return [path]

            logger.warning("未知 file_type=%s，按二进制下载: %s", file_type, title)
            save_path = save_dir / sanitize_filename(title, ext=_file_type_to_suffix(file_type))
            if save_path.exists() and not force:
                return [save_path]
            path = self._save_binary(url, save_path, file_type)
            return [path]

        except PermissionError as exc:
            logger.warning("robots.txt 禁止访问，跳过 [%s]: %s", title, exc)
            return []
        except requests.RequestException as exc:
            logger.warning("下载失败 [%s]: %s", title, exc)
            return []
        except OSError as exc:
            logger.warning("保存失败 [%s]: %s", title, exc)
            return []

    def _download_configured_attachments(
        self,
        entry: dict[str, Any],
        attachments: list[dict[str, Any]],
        save_dir: Path,
        force: bool = False,
    ) -> list[Path]:
        """下载 sources_registry 中手动配置的 attachments 直链。"""
        year = entry.get("year")
        data_type = entry.get("data_type", "unknown")
        title = entry.get("title", "untitled")
        saved: list[Path] = []

        valid = [att for att in attachments if _is_configured_url(att.get("url"))]
        if not valid:
            logger.warning(
                "[%s][%s] attachments 已配置但无有效 URL，跳过: %s（请用 extract-attachments-local 提取后填入）",
                year,
                data_type,
                title,
            )
            return saved

        attach_dir = save_dir / "attachments"
        attach_dir.mkdir(parents=True, exist_ok=True)
        logger.info(
            "[%s][%s] 使用手动配置的 attachments（%d 条），跳过 HTML 在线提取: %s",
            year,
            data_type,
            len(valid),
            title,
        )

        for att in valid:
            item = {
                "title": att.get("title") or "attachment",
                "url": att["url"].strip(),
                "file_type": att.get("file_type") or "xlsx",
            }
            path = self._download_attachment(item, attach_dir, force=force)
            if path is not None:
                saved.append(path)
                logger.info("附件已保存: %s", path.resolve())

        return saved

    def download_attachment_to_dir(
        self,
        url: str,
        output_dir: str | Path,
        filename: str | None = None,
        force: bool = False,
    ) -> Path | None:
        """下载单个附件直链到指定目录。"""
        if not _is_configured_url(url):
            logger.error("URL 未配置或无效: %s", url)
            return None

        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        url_path = Path(urlparse(url).path)
        file_type = _suffix_to_file_type(url_path.suffix) if url_path.suffix else "xlsx"

        if filename:
            fn = Path(filename)
            save_path = (
                out_dir / sanitize_filename(fn.name)
                if fn.suffix
                else out_dir / sanitize_filename(filename, ext=_file_type_to_suffix(file_type))
            )
        else:
            save_path = out_dir / sanitize_filename(
                url_path.stem or "attachment",
                ext=_file_type_to_suffix(file_type),
            )

        if save_path.exists() and not force:
            logger.info("文件已存在，跳过: %s", save_path)
            return save_path

        attachment = {
            "title": save_path.stem,
            "url": url.strip(),
            "file_type": file_type,
        }
        return self._download_attachment(
            attachment,
            out_dir,
            force=force,
            save_path=save_path,
        )

    def _download_html_with_attachments(
        self,
        url: str,
        title: str,
        save_dir: Path,
        force: bool = False,
    ) -> list[Path]:
        """下载 HTML 页面并提取、下载页面内附件。"""
        saved: list[Path] = []
        html_path = save_dir / sanitize_filename(title, ext=".html")

        if html_path.exists() and not force:
            logger.info("HTML 已存在，跳过下载: %s", html_path)
        else:
            html_path = self._save_html(url, html_path)

        saved.append(html_path)
        logger.info("页面已保存: %s", html_path.resolve())

        attachments = self.extract_attachment_links(url)
        if not attachments:
            logger.warning("页面内未发现附件: %s", url)
            return saved

        attach_dir = save_dir / "attachments"
        attach_dir.mkdir(parents=True, exist_ok=True)

        for att in attachments:
            path = self._download_attachment(att, attach_dir, force=force)
            if path is not None:
                saved.append(path)
                logger.info("附件已保存: %s", path.resolve())

        return saved

    def _download_attachment(
        self,
        attachment: dict[str, str],
        save_dir: Path,
        force: bool = False,
        save_path: Path | None = None,
    ) -> Path | None:
        """下载单个附件到指定目录。"""
        url = attachment["url"]
        att_title = attachment.get("title") or "attachment"
        file_type = attachment.get("file_type", "xlsx")
        ext = _file_type_to_suffix(file_type)
        target = save_path or (save_dir / sanitize_filename(att_title, ext=ext))

        if target.exists() and not force:
            logger.info("附件已存在，跳过: %s", target)
            return target

        try:
            return self._save_binary(url, target, file_type)
        except PermissionError as exc:
            logger.warning("附件下载失败 [%s]: %s", att_title, exc)
            return None
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            logger.warning("附件下载失败 [%s]: HTTP %s %s", att_title, status, url)
            return None
        except requests.RequestException as exc:
            logger.warning("附件下载失败 [%s]: %s", att_title, exc)
            return None
        except OSError as exc:
            logger.warning("附件保存失败 [%s]: %s", att_title, exc)
            return None

    def _resolve_extension(self, url: str, file_type: str) -> str:
        """根据配置 type 或 URL 推断扩展名。"""
        if file_type in DIRECT_FILE_TYPES:
            return _file_type_to_suffix(file_type)

        type_map = {
            "html": ".html",
            "excel": ".xlsx",
            "pdf": ".pdf",
        }
        if file_type in type_map:
            return type_map[file_type]

        path_ext = Path(urlparse(url).path).suffix.lower()
        if path_ext in (".html", ".htm", ".xlsx", ".xls", ".pdf", ".jpg", ".jpeg", ".png"):
            return path_ext if path_ext != ".htm" else ".html"
        return ".html"

    def _guess_ext_from_response(self, response: requests.Response, fallback: str) -> str:
        content_type = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if content_type in ("text/html", "text/plain") and fallback in (".xls", ".xlsx"):
            return fallback
        if content_type in _CONTENT_TYPE_EXT:
            return _CONTENT_TYPE_EXT[content_type]
        guessed = mimetypes.guess_extension(content_type) or ""
        if guessed == ".htm":
            guessed = ".html"
        if guessed in (".html", ".htm") and fallback in (".xls", ".xlsx"):
            return fallback
        return guessed or fallback

    def _save_html(self, url: str, save_path: Path) -> Path:
        """下载网页并保存为 .html。"""
        if not self._can_fetch(url):
            raise PermissionError(f"robots.txt 禁止访问: {url}")

        self._sleep()
        response = self.session.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        response.encoding = response.apparent_encoding or "utf-8"

        if not save_path.suffix:
            save_path = save_path.with_suffix(".html")

        save_path.write_text(response.text, encoding="utf-8")
        logger.info("已保存 HTML: %s", save_path)
        return save_path

    def _save_binary(self, url: str, save_path: Path, file_type: str) -> Path:
        """下载二进制文件（Excel/PDF/图片等）。"""
        if not self._can_fetch(url):
            raise PermissionError(f"robots.txt 禁止访问: {url}")

        save_path.parent.mkdir(parents=True, exist_ok=True)
        self._sleep()

        response = self.session.get(url, timeout=REQUEST_TIMEOUT, stream=True)
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            logger.warning("下载失败 [%s]: HTTP %s", url, status)
            raise

        fallback = self._resolve_extension(url, file_type)
        ext = self._guess_ext_from_response(response, fallback)
        if save_path.suffix.lower() != ext:
            save_path = save_path.with_suffix(ext)

        with open(save_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        logger.info("已保存: %s", save_path)
        return save_path

    # ------------------------------------------------------------------ #
    # Phase 1：索引页发现链接（保留）
    # ------------------------------------------------------------------ #

    def _can_fetch(self, url: str) -> bool:
        """检查 robots.txt 是否允许抓取该 URL。"""
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        user_agent = DEFAULT_HEADERS.get("User-Agent", "*")

        try:
            response = self.session.get(robots_url, timeout=REQUEST_TIMEOUT)
            text = response.text or ""
            # 部分站点 robots.txt 被 WAF 替换为 HTML，不可当作有效规则
            if "user-agent:" not in text.lower():
                logger.warning(
                    "robots.txt 非标准内容（可能为 WAF 页面），跳过 robots 限制: %s",
                    robots_url,
                )
                return True

            rp = RobotFileParser()
            rp.parse(text.splitlines())
            allowed = rp.can_fetch(user_agent, url)
            if not allowed:
                logger.warning("robots.txt 禁止访问: %s", url)
            return allowed
        except Exception as exc:
            logger.warning("无法读取 robots.txt (%s): %s，默认允许访问", robots_url, exc)
            return True

    def _sleep(self) -> None:
        time.sleep(self.delay)

    def fetch_page(self, url: str) -> str:
        """获取 HTML 页面内容。"""
        if not self._can_fetch(url):
            raise PermissionError(f"robots.txt 禁止访问: {url}")

        self._sleep()
        response = self.session.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        response.encoding = response.apparent_encoding or "utf-8"
        return response.text

    def download_file(self, url: str, save_path: Path) -> Path:
        """下载 Excel/PDF 等二进制文件到本地。"""
        if not self._can_fetch(url):
            raise PermissionError(f"robots.txt 禁止访问: {url}")

        save_path.parent.mkdir(parents=True, exist_ok=True)
        self._sleep()

        response = self.session.get(url, timeout=REQUEST_TIMEOUT, stream=True)
        response.raise_for_status()
        with open(save_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        logger.info("已保存: %s", save_path)
        return save_path

    def discover_links(self, index_url: str | None = None) -> list[dict]:
        """从索引页提取可下载链接（Excel/PDF）。"""
        url = index_url or self.admission_index
        html = self.fetch_page(url)
        links = extract_download_links(html, base_url=url)
        logger.info("在 %s 发现 %d 个下载链接", url, len(links))
        return links

    def _guess_year_from_text(self, text: str) -> int | None:
        for year in self.years:
            if str(year) in text:
                return year
        return None

    def _build_save_path(self, url: str, year: int | None, ext: str) -> Path:
        filename = urlparse(url).path.split("/")[-1] or "download"
        if not filename.lower().endswith(ext):
            filename = f"{filename}{ext}"
        year_part = str(year) if year else "unknown"
        return self.raw_dir / "jiangsu" / year_part / filename

    def crawl(self, max_files: int = 1, target_year: int | None = None) -> list[Path]:
        """执行爬取：从索引页发现链接并下载（Phase 1 逻辑）。"""
        logger.info(
            "开始爬取江苏省数据，年份范围 %s，最多下载 %d 个文件",
            self.years,
            max_files,
        )

        try:
            links = self.discover_links()
        except PermissionError as exc:
            logger.warning("%s，已中止爬取。请使用 download-source 或手动下载。", exc)
            return []
        except requests.RequestException as exc:
            logger.error("发现链接失败: %s", exc)
            return []

        if not links:
            logger.warning("未发现任何下载链接，请检查索引页 URL 或配置 JIANGSU_SOURCES")
            return []

        candidates: list[dict] = []
        for link in links:
            hint = link.get("text", "") + " " + link.get("url", "")
            year = self._guess_year_from_text(hint)
            if target_year and year and year != target_year:
                continue
            link["year_hint"] = year
            candidates.append(link)

        candidates.sort(key=lambda x: (0 if x.get("ext") == ".xlsx" else 1, x.get("url", "")))

        downloaded: list[Path] = []
        for link in candidates:
            if len(downloaded) >= max_files:
                break

            file_url = link["url"]
            ext = link.get("ext") or Path(urlparse(file_url).path).suffix or ".bin"
            year = link.get("year_hint") or target_year
            save_path = self._build_save_path(file_url, year, ext)

            if save_path.exists():
                logger.info("文件已存在，跳过: %s", save_path)
                downloaded.append(save_path)
                continue

            try:
                absolute_url = urljoin(self.base_url, file_url)
                path = self.download_file(absolute_url, save_path)
                downloaded.append(path)
            except (requests.RequestException, PermissionError) as exc:
                logger.warning("跳过链接 %s: %s", file_url, exc)
                continue

        logger.info("爬取完成，共下载 %d 个文件", len(downloaded))
        return downloaded


def extract_attachment_links(page_url: str) -> list[dict[str, str]]:
    """
    从 HTML 页面提取附件链接（模块级入口，便于 CLI 测试）。

    Returns:
        [{"title", "url", "file_type"}, ...]
    """
    crawler = JiangsuCrawler()
    return crawler.extract_attachment_links(page_url)


def extract_attachment_links_from_html_file(
    html_path: str | Path,
    base_url: str,
) -> list[dict[str, str]]:
    """
    从本地 HTML 文件提取附件链接（模块级入口）。

    Returns:
        [{"title", "url", "file_type"}, ...]
    """
    crawler = JiangsuCrawler()
    return crawler.extract_attachment_links_from_html_file(html_path, base_url)


def resolve_province_crawler(province: str) -> JiangsuCrawler:
    """根据省份名称返回对应爬虫（经 province_registry 解析）。"""
    from province_registry import get_province_plugin

    plugin = get_province_plugin(province)
    crawler = plugin.get_crawler()
    if crawler is None:
        raise ValueError(f"{plugin.province_name} 尚未提供爬虫实现")
    return crawler
