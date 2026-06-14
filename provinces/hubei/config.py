"""湖北省插件静态配置（Phase 19）。"""

from __future__ import annotations

from provinces.base import SubjectMode

PROVINCE_NAME = "湖北"
PROVINCE_SLUG = "hubei"
# 2024 投档线发布在湖北教育考试网（hbea 官网页脚链接的官方站点）
SOURCE_SITE_BASE_URL = "http://www.hbccks.cn"
SUPPORTED_YEARS = [2024]
SUBJECT_MODE = SubjectMode.NEW_GAOKAO
DEFAULT_SUBJECT_TYPE = ""
STATUS = "completed"
SUPPORTED_DATA_TYPES = ["school"]
DISCOVERY_STRATEGY = "html_list"

INDEX_URLS = [
    "http://www.hbccks.cn/html/gkgzzt/apccglq/",
    "http://www.hbccks.cn/html/gkgzzt/gzgzbl/",
]

DISCOVERY_KEYWORDS: dict[str, list[str]] = {
    "school": [
        "湖北省2024年本科普通批录取院校平行志愿投档线",
        "本科普通批录取院校平行志愿投档线",
        "高职高专普通批录取院校平行志愿投档线",
        "本科普通批",
        "高职高专普通批",
        "平行志愿投档线",
        "院校专业组",
        "首选历史",
        "首选物理",
        "平行志愿",
        "投档线",
        "投档情况",
        "历史类",
        "物理类",
    ],
}

# 已验证的 2024 普通类投档公告（页面内为 PNG 表格图，无 Excel/PDF 附件）
SEED_ANNOUNCEMENTS: dict[int, list[dict[str, str]]] = {
    2024: [
        {
            "title": "湖北省2024年本科普通批录取院校（首选历史）平行志愿投档线",
            "page_url": "http://www.hbccks.cn/html/apccglq/2024-07/142208.html",
        },
        {
            "title": "湖北省2024年本科普通批录取院校（首选物理）平行志愿投档线",
            "page_url": "http://www.hbccks.cn/html/apccglq/2024-07/142207.html",
        },
        {
            "title": "湖北省2024年高职高专普通批录取院校（首选历史）平行志愿投档线",
            "page_url": "http://www.hbccks.cn/html/gzgzbl/2024-08/142216.html",
        },
        {
            "title": "湖北省2024年高职高专普通批录取院校（首选物理）平行志愿投档线",
            "page_url": "http://www.hbccks.cn/html/gzgzbl/2024-08/142215.html",
        },
    ],
}
