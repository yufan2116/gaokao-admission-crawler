"""福建省插件静态配置（Phase 14）。"""

from __future__ import annotations

from provinces.base import SubjectMode

PROVINCE_NAME = "福建"
PROVINCE_SLUG = "fujian"
SOURCE_SITE_BASE_URL = "https://www.eeafj.cn"
SUPPORTED_YEARS = [2024]
SUBJECT_MODE = SubjectMode.NEW_GAOKAO
DEFAULT_SUBJECT_TYPE = ""
STATUS = "completed"
SUPPORTED_DATA_TYPES = ["school"]
DISCOVERY_STRATEGY = "html_list"

INDEX_URLS = [
    "https://www.eeafj.cn/gkptgkgsgg/",
]

DISCOVERY_KEYWORDS: dict[str, list[str]] = {
    "school": [
        "普通类本科批常规志愿院校专业组投档最低分",
        "普通类高职专科批常规志愿院校专业组投档最低分",
        "普通类本科批",
        "高职专科批",
        "院校专业组投档最低分",
        "历史科目组",
        "物理科目组",
        "普通类高职（专科）批常规志愿投档最低分",
        "投档最低分公布",
    ],
}

# 官方公告 seed（可人工增补附件直链或新年份 URL）
SEED_ANNOUNCEMENTS: dict[int, list[dict[str, str]]] = {
    2024: [
        {
            "title": "2024年普通类本科批常规志愿院校专业组投档最低分公布（历史科目组）",
            "page_url": "https://www.eeafj.cn/gkptgkgsgg/20240726/13541.html",
        },
        {
            "title": "2024年普通类本科批常规志愿院校专业组投档最低分公布（物理科目组）",
            "page_url": "https://www.eeafj.cn/gkptgkgsgg/20240726/13557.html",
        },
        {
            "title": "2024年普通类高职（专科）批常规志愿投档最低分公布（历史科目组）",
            "page_url": "https://www.eeafj.cn/gkptgkgsgg/20240819/13609.html",
        },
        {
            "title": "2024年普通类高职（专科）批常规志愿投档最低分公布（物理科目组）",
            "page_url": "https://www.eeafj.cn/gkptgkgsgg/20240819/13610.html",
        },
    ],
}
