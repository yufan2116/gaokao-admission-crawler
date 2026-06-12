"""河北省插件静态配置（Phase 14.1）。"""

from __future__ import annotations

from provinces.base import SubjectMode

PROVINCE_NAME = "河北"
PROVINCE_SLUG = "hebei"
SOURCE_SITE_BASE_URL = "http://www.hebeea.edu.cn"
SUPPORTED_YEARS = [2024]
SUBJECT_MODE = SubjectMode.NEW_GAOKAO
DEFAULT_SUBJECT_TYPE = ""
STATUS = "completed"
SUPPORTED_DATA_TYPES = ["school"]
DISCOVERY_STRATEGY = "html_list"

INDEX_URLS = [
    "http://www.hebeea.edu.cn/html/xxgl/tzgg/index.html",
    "http://xxcx.hebeea.edu.cn/html/xxgl/tzgg/index.html",
]

DISCOVERY_KEYWORDS: dict[str, list[str]] = {
    "school": [
        "普通高校招生本科批平行志愿投档情况统计",
        "普通高校招生专科批平行志愿投档情况统计",
        "本科批平行志愿投档情况统计",
        "专科批平行志愿投档情况统计",
        "历史科目组合",
        "物理科目组合",
        "投档情况统计",
    ],
}

# 官方公告 seed（可手工增补 attachment_url 附件直链或新年份 page_url）
SEED_ANNOUNCEMENTS: dict[int, list[dict[str, str]]] = {
    2024: [
        {
            "title": "2024年河北省普通高校招生本科批平行志愿投档情况统计",
            "page_url": "http://www.hebeea.edu.cn/html/xxgl/tzgg/2024/0722-163123-755.html",
        },
        {
            "title": "2024年河北省普通高校招生专科批平行志愿投档情况统计",
            "page_url": "http://www.hebeea.edu.cn/html/xxgl/tzgg/2024/0810-205711-755.html",
        },
    ],
}
