"""江苏省插件静态配置（不含爬虫/解析业务逻辑）。"""

from __future__ import annotations

from provinces.base import SubjectMode

PROVINCE_NAME = "江苏"
PROVINCE_SLUG = "jiangsu"
SUPPORTED_YEARS = [2021, 2022, 2023, 2024]
SUBJECT_MODE = SubjectMode.NEW_GAOKAO
STATUS = "completed"
SUPPORTED_DATA_TYPES = ["school", "rank", "control"]
