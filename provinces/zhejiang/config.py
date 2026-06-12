"""浙江省插件静态配置（Phase 10）。"""

from __future__ import annotations

from provinces.base import SubjectMode

PROVINCE_NAME = "浙江"
PROVINCE_SLUG = "zhejiang"
SOURCE_SITE_BASE_URL = "https://www.zjzs.net"
SUPPORTED_YEARS = [2024]
SUBJECT_MODE = SubjectMode.COMPREHENSIVE
DEFAULT_SUBJECT_TYPE = "综合改革"
STATUS = "completed"
SUPPORTED_DATA_TYPES = ["school"]
DISCOVERY_STRATEGY = "zj_col"

INDEX_URLS = [
    "https://www.zjzs.net/col/col45/index.html",
    "https://www.zjzs.net/col/col155/index.html",
]

DISCOVERY_KEYWORDS: dict[str, list[str]] = {
    "school": [
        "普通类第一段平行投档分数线",
        "普通类第二段平行投档分数线",
        "平行投档分数线表",
        "平行投档分数线",
    ],
}

# dataproxy 分页不可用时的 2024 兜底 seed
SEED_ANNOUNCEMENTS: dict[int, list[dict[str, str]]] = {
    2024: [
        {
            "title": "浙江省2024年普通高校招生普通类第一段平行投档分数线表",
            "page_url": "https://www.zjzs.net/art/2024/7/21/art_155_9900.html",
        },
        {
            "title": "浙江省2024年普通高校招生普通类第二段平行投档分数线表",
            "page_url": "https://www.zjzs.net/art/2024/7/30/art_155_10144.html",
        },
    ],
}
