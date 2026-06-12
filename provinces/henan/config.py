"""河南省插件静态配置（Phase 11）。"""

from __future__ import annotations

from provinces.base import SubjectMode

PROVINCE_NAME = "河南"
PROVINCE_SLUG = "henan"
SOURCE_SITE_BASE_URL = "https://www.henanjk.com"
SUPPORTED_YEARS = [2024]
SUBJECT_MODE = SubjectMode.LEGACY
DEFAULT_SUBJECT_TYPE = ""
STATUS = "completed"
SUPPORTED_DATA_TYPES = ["school"]
DISCOVERY_STRATEGY = "henan_id_scan"

# henanjk 新闻详情页 ID 扫描起点；max_pages 控制扫描宽度
DISCOVERY_ID_SCAN_START = 79200
DISCOVERY_ID_SCAN_WIDTH_PER_PAGE = 4

INDEX_URLS: list[str] = []

DISCOVERY_KEYWORDS: dict[str, list[str]] = {
    "school": [
        "本科一批院校平行投档分数线",
        "本科二批院校平行投档分数线",
        "高职高专批院校平行投档分数线",
        "本科一批院校平行投档",
        "本科二批院校平行投档",
        "高职高专批院校平行投档",
        "平行投档分数线",
        "平行投档",
        "文科",
        "理科",
    ],
}

# 教考资源信息网公开镜像 + 官方数据中心仅链查询页（需验证码）
SEED_ANNOUNCEMENTS: dict[int, list[dict[str, str]]] = {
    2024: [
        {
            "title": "2024年河南省普通高校招生本科一批院校平行投档分数线（理科）",
            "page_url": "https://www.henanjk.com/show.asp?id=79291&tb=xw&ut=0",
        },
        {
            "title": "2024年河南省普通高校招生本科一批院校平行投档分数线（文科）",
            "page_url": "https://www.henanjk.com/show.asp?id=79292&tb=xw&ut=0",
        },
        {
            "title": "2024年河南省普通高校招生本科二批院校平行投档分数线",
            "page_url": "https://www.henanjk.com/show.asp?id=79319&tb=xw&ut=0",
        },
    ],
}
