"""新高考省份插件工厂（Phase 18）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from crawlers.http_crawler import HttpProvinceCrawler
from importers.file_import import UnsupportedImportFormatError
from importers.pipeline import run_excel_pipeline, run_pdf_pipeline, run_parsed_pipeline
from provinces.base import ProvincePlugin


def _is_html_detail_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    return path.endswith((".html", ".htm", ".shtml", ".jhtml"))


def build_new_gaokao_school_plugin(config_module: Any) -> type[ProvincePlugin]:
    """基于 config 模块构建仅 school 的新高考省份插件。"""

    class _Plugin(ProvincePlugin):
        province_name = config_module.PROVINCE_NAME
        province_slug = config_module.PROVINCE_SLUG
        supported_years = config_module.SUPPORTED_YEARS
        subject_mode = config_module.SUBJECT_MODE
        discovery_keywords = config_module.DISCOVERY_KEYWORDS
        status = config_module.STATUS
        supported_data_types = config_module.SUPPORTED_DATA_TYPES
        index_urls = config_module.INDEX_URLS
        source_site_base_url = config_module.SOURCE_SITE_BASE_URL
        discovery_strategy = config_module.DISCOVERY_STRATEGY
        seed_announcements = config_module.SEED_ANNOUNCEMENTS
        default_subject_type = config_module.DEFAULT_SUBJECT_TYPE
        is_detail_page_url = staticmethod(_is_html_detail_url)

        def discover(
            self,
            years: list[int],
            data_type: str | None = None,
            keyword: str | None = None,
            max_pages: int = 5,
        ) -> dict[int, list[dict[str, Any]]]:
            from crawlers.generic_discovery import discover_via_plugin

            return discover_via_plugin(self, years, data_type, keyword, max_pages)

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
            if path.suffix.lower() == ".pdf":
                try:
                    return run_pdf_pipeline(
                        path,
                        data_type="school",
                        year=year,
                        province=prov,
                        subject_type_hint=subject_type or self.default_subject_type,
                        subject_mode=self.subject_mode,
                    )
                except ValueError as exc:
                    raise UnsupportedImportFormatError(str(exc)) from exc
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

    return _Plugin
