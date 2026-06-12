"""
江苏省 2024 年待导入文件清单（Phase 7）。

路径相对于项目根目录；由 scripts/import_jiangsu_2024.py 按列表顺序导入。
下载完成后请将 status 同步更新到 docs/data_sources_jiangsu_2024.md。
"""

from __future__ import annotations

JIANGSU_2024_META = {
    "year": 2024,
    "province": "江苏",
}

# 固定导入顺序：control → rank(历史) → rank(物理) → school(历史) → school(物理)
JIANGSU_2024_IMPORT_FILES: list[dict] = [
    {
        "type": "control",
        "title": "江苏省2024年普通高校招生第一阶段录取控制分数线",
        "path": "data/raw/jiangsu/2024/control/attachments/江苏省2024年普通高校招生第一阶段录取控制分数线.xlsx",
    },
    {
        "type": "rank",
        "subject_type": "历史类",
        "title": "江苏省2024年普通高考逐分段统计表（历史类）",
        "path": "data/raw/jiangsu/2024/rank/attachments/江苏省2024年普通高考逐分段统计表（历史类等科目类）.xlsx",
    },
    {
        "type": "rank",
        "subject_type": "物理类",
        "title": "江苏省2024年普通高考逐分段统计表（物理类）",
        "path": "data/raw/jiangsu/2024/rank/attachments/江苏省2024年普通高考逐分段统计表（物理类等科目类）.xlsx",
    },
    {
        "type": "school",
        "subject_type": "历史类",
        "title": "江苏省2024年普通类本科批次平行志愿投档线（历史类）",
        "path": "data/raw/jiangsu/2024/school/attachments/江苏省2024年普通类本科批次平行志愿投档线（历史等科目类）.xlsx",
    },
    {
        "type": "school",
        "subject_type": "物理类",
        "title": "江苏省2024年普通类本科批次平行志愿投档线（物理类）",
        "path": "data/raw/jiangsu/2024/school/attachments/江苏省2024年普通类本科批次平行志愿投档线（物理等科目类）.xlsx",
    },
]
