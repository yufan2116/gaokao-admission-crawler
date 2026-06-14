"""
各省数据源可机器读取性与入库状态（Phase 12.1）。

静态声明，与 province_registry 插件注册互补；用于 Dashboard / API 明示哪些省已真正入库、哪些仅下载未解析。
"""

from __future__ import annotations

from typing import Any, NotRequired, TypedDict

from sources.base import AccessStatus
from sources.registry import get_default_access_status


class ProvinceDataAvailabilityRow(TypedDict):
    province: str
    year: int
    school_discovery_status: str
    school_download_status: str
    school_import_status: str
    source_format: str
    machine_readable: bool
    query_mode: str
    notes: str
    access_status: str
    machine_readable_level: NotRequired[str]


PROVINCE_DATA_AVAILABILITY: list[ProvinceDataAvailabilityRow] = [
    {
        "province": "江苏",
        "year": 2021,
        "school_discovery_status": "discovered",
        "school_download_status": "downloaded",
        "school_import_status": "imported",
        "source_format": "Excel",
        "machine_readable": True,
        "query_mode": "score",
        "notes": "school / rank / control 均已入库",
        "access_status": AccessStatus.AVAILABLE.value,
    },
    {
        "province": "江苏",
        "year": 2022,
        "school_discovery_status": "discovered",
        "school_download_status": "downloaded",
        "school_import_status": "imported",
        "source_format": "Excel",
        "machine_readable": True,
        "query_mode": "score",
        "notes": "school / rank / control 均已入库",
        "access_status": AccessStatus.AVAILABLE.value,
    },
    {
        "province": "江苏",
        "year": 2023,
        "school_discovery_status": "discovered",
        "school_download_status": "downloaded",
        "school_import_status": "imported",
        "source_format": "Excel",
        "machine_readable": True,
        "query_mode": "score",
        "notes": "school / rank / control 均已入库",
        "access_status": AccessStatus.AVAILABLE.value,
    },
    {
        "province": "江苏",
        "year": 2024,
        "school_discovery_status": "discovered",
        "school_download_status": "downloaded",
        "school_import_status": "imported",
        "source_format": "Excel",
        "machine_readable": True,
        "query_mode": "score",
        "notes": "school / rank / control 均已入库",
        "access_status": AccessStatus.AVAILABLE.value,
    },
    {
        "province": "浙江",
        "year": 2024,
        "school_discovery_status": "discovered",
        "school_download_status": "downloaded",
        "school_import_status": "imported",
        "source_format": "Excel",
        "machine_readable": True,
        "query_mode": "score",
        "notes": "普通类一、二段平行投档 Excel 已入库",
        "access_status": AccessStatus.AVAILABLE.value,
    },
    {
        "province": "山东",
        "year": 2024,
        "school_discovery_status": "discovered",
        "school_download_status": "downloaded",
        "school_import_status": "imported",
        "source_format": "Excel",
        "machine_readable": True,
        "query_mode": "rank",
        "notes": "常规批投档表以 min_rank 为主，推荐按位次查询",
        "access_status": AccessStatus.AVAILABLE.value,
    },
    {
        "province": "河南",
        "year": 2024,
        "school_discovery_status": "discovered",
        "school_download_status": "downloaded",
        "school_import_status": "downloaded_not_imported",
        "source_format": "RAR + image Word + verification page",
        "machine_readable": False,
        "query_mode": "unsupported_pdf_or_image",
        "notes": "公开 RAR 内为图片型 Word；官方数据中心需验证码，不绕过",
        "access_status": AccessStatus.VERIFICATION_REQUIRED.value,
    },
    {
        "province": "广东",
        "year": 2024,
        "school_discovery_status": "discovered",
        "school_download_status": "downloaded",
        "school_import_status": "imported_partial",
        "source_format": "ZIP + machine-readable PDF",
        "machine_readable": False,
        "machine_readable_level": "partial",
        "query_mode": "score",
        "notes": "普通类历史/物理已入库；艺体类已下载但暂不建模",
        "access_status": AccessStatus.PARTIAL.value,
    },
    {
        "province": "福建",
        "year": 2024,
        "school_discovery_status": "discovered",
        "school_download_status": "not_started",
        "school_import_status": "not_started",
        "source_format": "Excel / PDF",
        "machine_readable": True,
        "query_mode": "score",
        "notes": "普通类本科/专科投档；艺体类 skipped_unsupported_category",
        "access_status": AccessStatus.WAF_BLOCKED.value,
    },
    {
        "province": "河北",
        "year": 2024,
        "school_discovery_status": "discovered",
        "school_download_status": "not_started",
        "school_import_status": "not_started",
        "source_format": "Excel / PDF",
        "machine_readable": True,
        "query_mode": "score",
        "notes": "普通类本科/专科专业粒度投档；艺体/对口 skipped_unsupported_category",
        "access_status": AccessStatus.CONNECTION_RESET.value,
    },
    {
        "province": "湖北",
        "year": 2024,
        "school_discovery_status": "discovered",
        "school_download_status": "downloaded_not_imported",
        "school_import_status": "unsupported_pdf_or_image",
        "source_format": "PNG images (hbccks.cn)",
        "machine_readable": False,
        "query_mode": "unsupported_pdf_or_image",
        "notes": "2024 普通类本科/专科投档线已发现（hbccks 官方页面）；表格为 PNG 图片，无 OCR 不入库",
        "access_status": AccessStatus.AVAILABLE.value,
    },
    {
        "province": "湖南",
        "year": 2024,
        "school_discovery_status": "plugin_ready",
        "school_download_status": "pending",
        "school_import_status": "pending",
        "source_format": "unknown",
        "machine_readable": False,
        "machine_readable_level": "unknown",
        "query_mode": "unknown",
        "notes": "Phase 18 插件骨架；待补 seed 或列表页 URL 后验证",
        "access_status": AccessStatus.UNKNOWN.value,
    },
    {
        "province": "辽宁",
        "year": 2024,
        "school_discovery_status": "plugin_ready",
        "school_download_status": "pending",
        "school_import_status": "pending",
        "source_format": "unknown",
        "machine_readable": False,
        "machine_readable_level": "unknown",
        "query_mode": "unknown",
        "notes": "Phase 18 插件骨架；待补 seed 或列表页 URL 后验证",
        "access_status": AccessStatus.UNKNOWN.value,
    },
    {
        "province": "重庆",
        "year": 2024,
        "school_discovery_status": "plugin_ready",
        "school_download_status": "pending",
        "school_import_status": "pending",
        "source_format": "unknown",
        "machine_readable": False,
        "machine_readable_level": "unknown",
        "query_mode": "unknown",
        "notes": "Phase 18 插件骨架；待补 seed 或列表页 URL 后验证",
        "access_status": AccessStatus.UNKNOWN.value,
    },
]

MACHINE_READABLE_LABELS: dict[str, str] = {
    "full": "是",
    "partial": "部分",
    "none": "否",
    "unknown": "未知",
}

IMPORT_STATUS_LABELS: dict[str, str] = {
    "imported": "已入库",
    "downloaded_not_imported": "已下载未入库",
    "parsed": "已解析入库",
    "unsupported_pdf_table": "不支持（PDF 表格）",
    "parsed_or_unsupported": "已解析 / 不支持",
    "imported_partial": "部分已入库",
    "not_started": "未开始",
    "plugin_ready": "插件就绪",
    "pending": "待验证",
}

QUERY_MODE_LABELS: dict[str, str] = {
    "score": "按分数",
    "rank": "按位次",
    "mixed": "混合",
    "unsupported": "不支持",
    "unsupported_pdf_or_image": "不支持（PDF/图片源）",
    "unknown": "未知",
}


def get_province_data_availability() -> list[dict[str, Any]]:
    """返回省份数据可用性配置（API / 服务层）。"""
    rows: list[dict[str, Any]] = []
    for row in PROVINCE_DATA_AVAILABILITY:
        item = dict(row)
        if not item.get("access_status"):
            item["access_status"] = get_default_access_status(item["province"]).value
        rows.append(item)
    return rows


def get_province_availability_display_rows() -> list[dict[str, str]]:
    """Dashboard 展示用中文列。"""
    rows: list[dict[str, str]] = []
    for row in PROVINCE_DATA_AVAILABILITY:
        level = row.get("machine_readable_level")
        if level:
            readable_label = MACHINE_READABLE_LABELS.get(level, level)
        else:
            readable_label = "是" if row["machine_readable"] else "否"
        access = row.get("access_status") or get_default_access_status(row["province"]).value
        rows.append(
            {
                "省份": row["province"],
                "年份": str(row["year"]),
                "是否可结构化": readable_label,
                "数据格式": row["source_format"],
                "入库状态": IMPORT_STATUS_LABELS.get(
                    row["school_import_status"], row["school_import_status"]
                ),
                "查询模式": QUERY_MODE_LABELS.get(row["query_mode"], row["query_mode"]),
                "Access Status": access,
                "说明": row["notes"],
            }
        )
    return rows
