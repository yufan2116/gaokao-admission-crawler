"""
江苏省官方数据源注册表（Phase 2 / 2.1 / 2.2）。

在 crawlers/jiangsu.py 中 re-export；此处集中维护，便于手动补 URL。
"""

from __future__ import annotations

from typing import Any

# 旧版 crawl-jiangsu 使用的入口页（与按年数据源配置分离）
JIANGSU_LEGACY_INDEX = {
    "base_url": "https://www.jseea.cn",
    "admission_index": "https://www.jseea.cn/webfile/index/index_zkxx/",
}

# 数据类型键
DATA_TYPES = ("control", "rank", "school", "major")


def _is_valid_url(url: str | None) -> bool:
    if not url:
        return False
    text = url.strip()
    return bool(text) and text.upper() != "TODO"


# 江苏省按年份配置的真实/待补数据源
# url 可为空字符串或 TODO，表示尚未配置
# type: html | xlsx | xls | pdf | jpg | excel | html_or_excel_or_pdf
# attachments: 可选，手动配置的附件直链（存在时 download-source 跳过在线 HTML 提取）
JIANGSU_SOURCES: dict[int, dict[str, list[dict[str, Any]]]] = {
    2024: {
        "control": [
            {
                "title": "江苏省2024年普通高校招生第一阶段录取控制分数线",
                "url": "",  # TODO: 江苏省教育考试院官网公告页
                "type": "html",
            },
        ],
        "rank": [
            {
                "title": "江苏省2024年普通高考逐分段统计表（第一阶段）",
                "url": "https://www.jseea.cn/webfile/index/index_zkxx/2024-06-24/7210960924591525888.html",
                "type": "html",
            },
        ],
        "school": [
            {
                "title": "江苏省2024年普通类本科批次平行志愿投档线",
                "url": "https://www.jseea.cn/webfile/index/index_zkxx/2024-07-18/7219509116052443136.html",
                "type": "html",
                "attachments": [
                    {
                        "title": "江苏省2024年普通类本科批次平行志愿投档线（历史类）",
                        "url": "",  # TODO: 用 extract-attachments-local 提取后填入
                        "file_type": "xlsx",
                    },
                    {
                        "title": "江苏省2024年普通类本科批次平行志愿投档线（物理类）",
                        "url": "",  # TODO
                        "file_type": "xlsx",
                    },
                ],
            },
        ],
        "major": [
            {
                "title": "2024年江苏省普通高考本科批次专业录取线",
                "url": "",  # TODO
                "type": "html",
            },
        ],
    },
}


def get_jiangsu_year_config(year: int) -> dict[str, list[dict[str, Any]]] | None:
    """获取指定年份的江苏省数据源配置。"""
    return JIANGSU_SOURCES.get(year)


def iter_jiangsu_sources(
    year: int,
    data_type: str | None = None,
) -> list[dict[str, Any]]:
    """
    展开数据源为扁平列表，每项含 year / data_type / title / url / file_type。
    若配置含 attachments 字段，一并传入（用于手动直链下载）。
    """
    year_cfg = get_jiangsu_year_config(year)
    if not year_cfg:
        return []

    types = [data_type] if data_type else list(DATA_TYPES)
    entries: list[dict[str, Any]] = []

    for dtype in types:
        if dtype not in DATA_TYPES:
            continue
        for item in year_cfg.get(dtype, []):
            entry: dict[str, Any] = {
                "year": year,
                "data_type": dtype,
                "title": item.get("title", ""),
                "url": (item.get("url") or "").strip(),
                "file_type": item.get("type", "html_or_excel_or_pdf"),
            }
            if "attachments" in item:
                entry["attachments"] = item["attachments"]
            entries.append(entry)
    return entries


def check_sources_status() -> list[dict[str, Any]]:
    """
    统计各年份、各类型已配置 / 缺失 URL 数量。

    Returns:
        [{"year", "data_type", "configured", "missing", "total", "attachments_configured", "attachments_missing"}, ...]
    """
    summary: list[dict[str, Any]] = []
    for year, year_cfg in sorted(JIANGSU_SOURCES.items()):
        for dtype in DATA_TYPES:
            items = year_cfg.get(dtype, [])
            configured = sum(1 for i in items if _is_valid_url(i.get("url")))
            missing = len(items) - configured

            att_configured = 0
            att_missing = 0
            for item in items:
                for att in item.get("attachments") or []:
                    if _is_valid_url(att.get("url")):
                        att_configured += 1
                    else:
                        att_missing += 1

            summary.append(
                {
                    "year": year,
                    "data_type": dtype,
                    "configured": configured,
                    "missing": missing,
                    "total": len(items),
                    "attachments_configured": att_configured,
                    "attachments_missing": att_missing,
                }
            )
    return summary
