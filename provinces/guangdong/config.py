"""广东省插件静态配置（Phase 12）。"""

from __future__ import annotations

from provinces.base import SubjectMode

PROVINCE_NAME = "广东"
PROVINCE_SLUG = "guangdong"
SOURCE_SITE_BASE_URL = "https://eea.gd.gov.cn"
SUPPORTED_YEARS = [2024]
SUBJECT_MODE = SubjectMode.NEW_GAOKAO
DEFAULT_SUBJECT_TYPE = ""
STATUS = "completed"
SUPPORTED_DATA_TYPES = ["school"]
DISCOVERY_STRATEGY = "html_list"

INDEX_URLS = [
    "https://eea.gd.gov.cn/ptgk/index.html",
    "https://eea.gd.gov.cn/zwgk/sjfb/tjsj/index.html",
]

DISCOVERY_KEYWORDS: dict[str, list[str]] = {
    "school": [
        "普通类本科批次投档情况",
        "普通类专科批次投档情况",
        "本科批次普通类投档",
        "专科批次普通类投档",
        "本科批次正式投档",
        "专科批次普通类",
        "历史类",
        "物理类",
        "投档情况",
    ],
}

# 官方公告 seed（可人工增补）；2024 年附件多为 ZIP/PDF，下载后 PDF 标记 downloaded_not_imported
SEED_ANNOUNCEMENTS: dict[int, list[dict[str, str]]] = {
    2024: [
        {
            "title": "我省2024年普通高考本科批次正式投档",
            "page_url": "https://eea.gd.gov.cn/ptgk/content/post_4458330.html",
        },
        {
            "title": "我省2024年普通高考本科批次正式投档（政务公开）",
            "page_url": "https://eea.gd.gov.cn/zwgk/sjfb/tjsj/content/post_4458419.html",
        },
        {
            "title": "我省专科批次普通类及艺体类正式投档",
            "page_url": "https://eea.gd.gov.cn/zwgk/sjfb/tjsj/content/post_4468541.html",
        },
    ],
}
