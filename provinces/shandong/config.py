"""山东省插件静态配置（Phase 10）。"""

from __future__ import annotations

from provinces.base import SubjectMode

PROVINCE_NAME = "山东"
PROVINCE_SLUG = "shandong"
SOURCE_SITE_BASE_URL = "https://www.sdzk.cn"
SUPPORTED_YEARS = [2024]
SUBJECT_MODE = SubjectMode.COMPREHENSIVE
DEFAULT_SUBJECT_TYPE = "综合改革"
STATUS = "completed"
SUPPORTED_DATA_TYPES = ["school"]
DISCOVERY_STRATEGY = "html_list"

INDEX_URLS = [
    "https://www.sdzk.cn/NewsList.aspx?BCID=12&CID=47",
]

DISCOVERY_KEYWORDS: dict[str, list[str]] = {
    "school": [
        "普通类常规批第1次志愿投档情况表",
        "普通类常规批第2次志愿投档情况表",
        "普通类常规批第3次志愿投档情况表",
        "普通类常规批",
        "投档情况表",
    ],
}

SEED_ANNOUNCEMENTS: dict[int, list[dict[str, str]]] = {}
