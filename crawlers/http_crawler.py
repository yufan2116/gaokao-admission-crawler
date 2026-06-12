"""
通用省份 HTTP 爬虫（Phase 10）。

复用合规请求间隔与 robots 检查，供浙江/山东等插件使用；江苏仍用 JiangsuCrawler。
"""

from __future__ import annotations

import logging
import mimetypes
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse
from urllib.robotparser import RobotFileParser

import requests

from config import DEFAULT_HEADERS, RAW_DIR, REQUEST_DELAY, REQUEST_TIMEOUT
from crawlers.filename_utils import sanitize_filename
from crawlers.jiangsu import _extract_attachments_from_html, _file_type_to_suffix

logger = logging.getLogger(__name__)

_CONTENT_TYPE_EXT = {
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/x-rar-compressed": ".rar",
    "application/vnd.rar": ".rar",
    "application/zip": ".zip",
}


class HttpProvinceCrawler:
    """轻量 HTTP 爬虫：抓列表/详情页、下载 Excel 附件。"""

    def __init__(
        self,
        *,
        province: str,
        base_url: str,
        raw_dir: Path | None = None,
        delay: float = REQUEST_DELAY,
    ) -> None:
        self.province = province
        self.base_url = base_url.rstrip("/")
        self.raw_dir = raw_dir or RAW_DIR
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self.raw_dir.mkdir(parents=True, exist_ok=True)

    def extract_attachment_links(self, page_url: str) -> list[dict[str, str]]:
        try:
            html = self.fetch_page(page_url)
        except (PermissionError, requests.RequestException) as exc:
            logger.error("提取附件失败 [%s]: %s", page_url, exc)
            return []
        results = _extract_attachments_from_html(html, page_url)
        logger.info("从 %s 提取到 %d 个附件链接", page_url, len(results))
        return results

    def _download_attachment(
        self,
        attachment: dict[str, str],
        save_dir: Path,
        force: bool = False,
        save_path: Path | None = None,
    ) -> Path | None:
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
        except (PermissionError, requests.RequestException, OSError) as exc:
            logger.warning("附件下载失败 [%s]: %s", att_title, exc)
            return None

    def _can_fetch(self, url: str) -> bool:
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        user_agent = DEFAULT_HEADERS.get("User-Agent", "*")
        try:
            response = self.session.get(robots_url, timeout=REQUEST_TIMEOUT)
            text = response.text or ""
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
        if not self._can_fetch(url):
            raise PermissionError(f"robots.txt 禁止访问: {url}")
        self._sleep()
        response = self.session.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        response.encoding = response.apparent_encoding or "utf-8"
        return response.text

    def _resolve_extension(self, url: str, file_type: str) -> str:
        if file_type in ("xlsx", "xls", "excel", "rar", "zip"):
            return _file_type_to_suffix(file_type)
        path_ext = Path(urlparse(url).path).suffix.lower()
        if path_ext in (".xlsx", ".xls", ".rar", ".zip"):
            return path_ext
        qs = parse_qs(urlparse(url).query)
        fn = (qs.get("filename") or [""])[0]
        if fn.lower().endswith((".xls", ".xlsx")):
            return Path(fn).suffix.lower()
        return ".xls"

    def _guess_ext_from_response(self, response: requests.Response, fallback: str) -> str:
        content_type = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        # 部分考试院将 Excel/RAR 误标为 text/html 或 octet-stream，保留 URL 推断扩展名
        if content_type in ("text/html", "text/plain", "application/octet-stream") and fallback in (
            ".xls",
            ".xlsx",
            ".rar",
            ".zip",
        ):
            return fallback
        if content_type in _CONTENT_TYPE_EXT:
            return _CONTENT_TYPE_EXT[content_type]
        guessed = mimetypes.guess_extension(content_type) or ""
        if guessed in (".html", ".htm", ".bin") and fallback in (".xls", ".xlsx", ".rar", ".zip"):
            return fallback
        return guessed or fallback

    def _save_binary(self, url: str, save_path: Path, file_type: str) -> Path:
        if not self._can_fetch(url):
            raise PermissionError(f"robots.txt 禁止访问: {url}")
        save_path.parent.mkdir(parents=True, exist_ok=True)
        self._sleep()
        response = self.session.get(url, timeout=REQUEST_TIMEOUT, stream=True)
        response.raise_for_status()
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
