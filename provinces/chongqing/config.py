"""重庆市插件静态配置（Phase 18）。"""

from __future__ import annotations

from provinces.base import SubjectMode
from provinces.new_gaokao_keywords import NEW_GAOKAO_SCHOOL_KEYWORDS

PROVINCE_NAME = "重庆"
PROVINCE_SLUG = "chongqing"
SOURCE_SITE_BASE_URL = "https://www.cqksy.cn"
SUPPORTED_YEARS = [2024]
SUBJECT_MODE = SubjectMode.NEW_GAOKAO
DEFAULT_SUBJECT_TYPE = ""
STATUS = "completed"
SUPPORTED_DATA_TYPES = ["school"]
DISCOVERY_STRATEGY = "html_list"

INDEX_URLS: list[str] = []

DISCOVERY_KEYWORDS: dict[str, list[str]] = {
    "school": list(NEW_GAOKAO_SCHOOL_KEYWORDS),
}

SEED_ANNOUNCEMENTS: dict[int, list[dict[str, str]]] = {
    2024: [],
}
