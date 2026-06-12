"""
省份插件注册表（Phase 8）。

CLI / Dashboard / discovery 通过本模块解析省份，避免散落 if province == "江苏"。
"""

from __future__ import annotations

from provinces.base import ProvincePlugin
from provinces.fujian import FujianPlugin
from provinces.guangdong import GuangdongPlugin
from provinces.hebei import HebeiPlugin
from provinces.henan import HenanPlugin
from provinces.jiangsu import JiangsuPlugin
from provinces.shandong import ShandongPlugin
from provinces.zhejiang import ZhejiangPlugin
from normalizers.province import normalize_province
from services.school_query_mode import PROVINCE_DEFAULT_QUERY_MODE

PROVINCES: dict[str, ProvincePlugin] = {
    "江苏": JiangsuPlugin(),
    "浙江": ZhejiangPlugin(),
    "山东": ShandongPlugin(),
    "河南": HenanPlugin(),
    "广东": GuangdongPlugin(),
    "福建": FujianPlugin(),
    "河北": HebeiPlugin(),
}


def get_province_plugin(province: str) -> ProvincePlugin:
    """按省份名返回插件实例；未注册则抛出 ValueError。"""
    name = normalize_province(province)
    plugin = PROVINCES.get(name)
    if plugin is None:
        available = "、".join(sorted(PROVINCES))
        raise ValueError(f"暂不支持省份: {province}，已注册: {available}")
    return plugin


def list_registered_provinces() -> list[str]:
    return sorted(PROVINCES.keys())


def get_province_coverage_rows() -> list[dict[str, str]]:
    """Dashboard「Province Coverage」静态行（与 DB 无关）。"""
    rows: list[dict[str, str]] = []
    for name in list_registered_provinces():
        summary = PROVINCES[name].coverage_summary()
        status_label = "已完成" if summary["status"] == "completed" else "TODO"
        query_mode = PROVINCE_DEFAULT_QUERY_MODE.get(name, "mixed")
        rows.append(
            {
                "省份": summary["province"],
                "年份": summary["year_range"],
                "数据类型": "、".join(summary["data_types"]) if summary["data_types"] else "—",
                "科类模式": summary["subject_mode"],
                "查询模式": query_mode,
                "状态": status_label,
            }
        )
    return rows
