"""江苏省插件：委托现有 crawlers / importers 实现。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from crawlers.jiangsu import JiangsuCrawler
from importers.pipeline import run_excel_pipeline, run_parsed_pipeline
from provinces.base import ProvincePlugin
from provinces.jiangsu import config


class JiangsuPlugin(ProvincePlugin):
    province_name = config.PROVINCE_NAME
    province_slug = config.PROVINCE_SLUG
    supported_years = config.SUPPORTED_YEARS
    subject_mode = config.SUBJECT_MODE
    status = config.STATUS
    supported_data_types = config.SUPPORTED_DATA_TYPES

    @property
    def discovery_keywords(self) -> dict[str, list[str]]:
        from crawlers.discovery import DISCOVERY_KEYWORDS

        return DISCOVERY_KEYWORDS

    def discover(
        self,
        years: list[int],
        data_type: str | None = None,
        keyword: str | None = None,
        max_pages: int = 5,
    ) -> dict[int, list[dict[str, Any]]]:
        from crawlers.discovery import (
            _filter_sources_by_year,
            collect_keywords,
            discover_jiangsu_sources,
        )

        keywords = collect_keywords(data_type, keyword)
        by_year = discover_jiangsu_sources(years, keywords, max_pages=max_pages)
        return _filter_sources_by_year(by_year, data_type, keyword)

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
            subject_type_hint=subject_type,
        )
        if admission_category or batch:
            return run_parsed_pipeline(
                parsed.parsed_df,
                data_type="school",
                year=year,
                province=prov,
                subject_type=subject_type,
                source_path=path,
                admission_category=admission_category,
                batch=batch,
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
        return run_excel_pipeline(
            Path(file_path),
            data_type="rank",
            year=year,
            province=province or self.province_name,
            sheet_name=sheet_name,
            subject_type_hint=subject_type,
        )

    def parse_control(
        self,
        file_path: str | Path,
        *,
        year: int | None = None,
        province: str | None = None,
        subject_type: str | None = None,
        sheet_name: str | int = 0,
    ):
        return run_excel_pipeline(
            Path(file_path),
            data_type="control",
            year=year,
            province=province or self.province_name,
            sheet_name=sheet_name,
            subject_type_hint=subject_type,
        )

    def get_crawler(self) -> JiangsuCrawler:
        return JiangsuCrawler()


__all__ = ["JiangsuPlugin"]
