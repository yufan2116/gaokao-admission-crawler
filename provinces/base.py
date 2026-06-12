"""
省份插件基类与科类模式枚举（Phase 8）。

各省份在 provinces/<name>/ 下实现 ProvincePlugin，通过 province_registry 注册。
核心 parse / normalize / validate 流水线保持不变，省份插件负责发现与解析入口。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from typing import Any

import pandas as pd

from importers.pipeline import PipelineResult


class SubjectMode(str, Enum):
    """高考科类划分模式。"""

    LEGACY = "legacy"
    NEW_GAOKAO = "new_gaokao"
    COMPREHENSIVE = "comprehensive"


SUBJECT_MODE_LABELS: dict[SubjectMode, list[str]] = {
    SubjectMode.LEGACY: ["文科", "理科"],
    SubjectMode.NEW_GAOKAO: ["历史类", "物理类"],
    SubjectMode.COMPREHENSIVE: ["综合改革"],
}


class ProvincePlugin(ABC):
    """
    省份数据采集插件接口。

    子类只需实现本省发现与解析入口；入库、校验、Dashboard 等共用核心层。
    """

    province_name: str
    province_slug: str
    supported_years: list[int]
    subject_mode: SubjectMode
    discovery_keywords: dict[str, list[str]]
    status: str = "planned"
    supported_data_types: list[str]
    index_urls: list[str] = []
    source_site_base_url: str = ""
    discovery_strategy: str = "html_list"
    seed_announcements: dict[int, list[dict[str, str]]] = {}
    default_subject_type: str = ""

    @property
    def is_available(self) -> bool:
        """插件是否已可运行（非规划中）。"""
        return self.status == "completed"

    @property
    def subject_types(self) -> list[str]:
        return SUBJECT_MODE_LABELS[self.subject_mode]

    @abstractmethod
    def discover(
        self,
        years: list[int],
        data_type: str | None = None,
        keyword: str | None = None,
        max_pages: int = 5,
    ) -> dict[int, list[dict[str, Any]]]:
        """从本省考试院官网发现公告数据源。"""

    @abstractmethod
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
    ) -> PipelineResult:
        """解析院校投档线文件。"""

    @abstractmethod
    def parse_rank(
        self,
        file_path: str | Path,
        *,
        year: int | None = None,
        province: str | None = None,
        subject_type: str | None = None,
        sheet_name: str | int = 0,
    ) -> PipelineResult:
        """解析一分一段表文件。"""

    @abstractmethod
    def parse_control(
        self,
        file_path: str | Path,
        *,
        year: int | None = None,
        province: str | None = None,
        subject_type: str | None = None,
        sheet_name: str | int = 0,
    ) -> PipelineResult:
        """解析省控线文件。"""

    def get_crawler(self) -> Any | None:
        """返回本省爬虫实例；未实现时返回 None。"""
        return None

    def coverage_summary(self) -> dict[str, Any]:
        """Dashboard / CLI 用的静态覆盖说明。"""
        year_range = (
            f"{min(self.supported_years)}-{max(self.supported_years)}"
            if self.supported_years
            else "—"
        )
        return {
            "province": self.province_name,
            "year_range": year_range,
            "supported_years": list(self.supported_years),
            "data_types": list(self.supported_data_types),
            "status": self.status,
            "subject_mode": self.subject_mode.value,
            "subject_types": self.subject_types,
        }
