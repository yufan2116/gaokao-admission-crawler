"""河南省插件（Phase 11）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from crawlers.http_crawler import HttpProvinceCrawler
from importers.pipeline import run_excel_pipeline, run_parsed_pipeline
from provinces.base import ProvincePlugin
from provinces.henan import config


def _is_henan_detail_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    return "show.asp" in path and "id=" in url.lower()


class HenanPlugin(ProvincePlugin):
    province_name = config.PROVINCE_NAME
    province_slug = config.PROVINCE_SLUG
    supported_years = config.SUPPORTED_YEARS
    subject_mode = config.SUBJECT_MODE
    discovery_keywords = config.DISCOVERY_KEYWORDS
    status = config.STATUS
    supported_data_types = config.SUPPORTED_DATA_TYPES
    index_urls = config.INDEX_URLS
    source_site_base_url = config.SOURCE_SITE_BASE_URL
    discovery_strategy = config.DISCOVERY_STRATEGY
    seed_announcements = config.SEED_ANNOUNCEMENTS
    default_subject_type = config.DEFAULT_SUBJECT_TYPE
    is_detail_page_url = staticmethod(_is_henan_detail_url)

    def discover(
        self,
        years: list[int],
        data_type: str | None = None,
        keyword: str | None = None,
        max_pages: int = 5,
    ) -> dict[int, list[dict[str, Any]]]:
        from provinces.henan.discovery import discover_via_henan_plugin

        return discover_via_henan_plugin(self, years, data_type, keyword, max_pages)

    def parse_school(
        self,
        file_path: str | Path,
        *,
        year: int | None = None,
        province: str | None = None,
        subject_type: str | None = None,
        admission_category: str | None = None,
        batch: str | None = None,
        sheet_name: str | int = 0,
    ):
        path = Path(file_path)
        prov = province or self.province_name
        parsed = run_excel_pipeline(
            path,
            data_type="school",
            year=year,
            province=prov,
            sheet_name=sheet_name,
            subject_type_hint=subject_type or self.default_subject_type,
            subject_mode=self.subject_mode,
        )
        if admission_category or batch:
            return run_parsed_pipeline(
                parsed.parsed_df,
                data_type="school",
                year=year,
                province=prov,
                subject_type=subject_type or self.default_subject_type,
                source_path=path,
                admission_category=admission_category,
                batch=batch,
                subject_mode=self.subject_mode,
            )
        return parsed

    def parse_rank(
        self,
        file_path: str | Path,
        *,
        year: int | None = None,
        province: str | None = None,
        subject_type: str | None = None,
        sheet_name: str | int = 0,
    ):
        raise NotImplementedError(f"{self.province_name} 暂不支持 rank")

    def parse_control(
        self,
        file_path: str | Path,
        *,
        year: int | None = None,
        province: str | None = None,
        subject_type: str | None = None,
        sheet_name: str | int = 0,
    ):
        raise NotImplementedError(f"{self.province_name} 暂不支持 control")

    def get_crawler(self) -> HttpProvinceCrawler:
        return HttpProvinceCrawler(
            province=self.province_name,
            base_url=self.source_site_base_url,
        )


__all__ = ["HenanPlugin"]
