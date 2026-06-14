"""
从 SQLite 按省份分目录导出 CSV。

输出结构：{output_dir}/{省份}/{type}_{year}.csv
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import create_engine, text

from config import DATABASE_URL, EXPORT_CSV_DIR

logger = logging.getLogger(__name__)

RECORD_TYPES = ("school", "major", "control", "rank")

_TABLE_SPECS: dict[str, dict[str, Any]] = {
    "school": {
        "table": "school_admission_line",
        "select": """
            year, province, subject_type, admission_category, batch,
            school_name, school_code, major_group, min_score, min_rank, plan_count,
            tie_breaker_text, source_url
        """,
        "rename": {
            "year": "年份",
            "province": "省份",
            "subject_type": "科类",
            "admission_category": "招生类别",
            "batch": "批次",
            "school_name": "院校名称",
            "school_code": "院校代号",
            "major_group": "专业组",
            "min_score": "投档最低分",
            "min_rank": "位次",
            "plan_count": "计划数",
            "tie_breaker_text": "同分排序项",
            "source_url": "来源",
        },
        "order_by": "year DESC, batch, subject_type, min_score DESC, school_name",
    },
    "major": {
        "table": "major_admission_line",
        "select": """
            year, province, school_name, school_code, major_name, major_code,
            subject_type, major_group, min_score, avg_score, max_score, min_rank, source_url
        """,
        "rename": {
            "year": "年份",
            "province": "省份",
            "school_name": "院校名称",
            "school_code": "院校代号",
            "major_name": "专业名称",
            "major_code": "专业代号",
            "subject_type": "科类",
            "major_group": "专业组",
            "min_score": "最低分",
            "avg_score": "平均分",
            "max_score": "最高分",
            "min_rank": "位次",
            "source_url": "来源",
        },
        "order_by": "year DESC, school_name, major_name",
    },
    "control": {
        "table": "province_control_line",
        "select": "year, province, subject_type, batch, score, source_url",
        "rename": {
            "year": "年份",
            "province": "省份",
            "subject_type": "科类",
            "batch": "批次",
            "score": "控制线分数",
            "source_url": "来源",
        },
        "order_by": "year DESC, batch, subject_type",
    },
    "rank": {
        "table": "score_rank_table",
        "select": """
            year, province, subject_type, score,
            same_score_count, cumulative_count, source_url
        """,
        "rename": {
            "year": "年份",
            "province": "省份",
            "subject_type": "科类",
            "score": "分数",
            "same_score_count": "同分人数",
            "cumulative_count": "累计人数",
            "source_url": "来源",
        },
        "order_by": "year DESC, subject_type, score DESC",
    },
}


@dataclass
class ProvinceCsvExportReport:
    output_dir: Path
    record_types: list[str]
    provinces: list[str]
    years: list[int] | None
    files: list[dict[str, Any]] = field(default_factory=list)
    total_rows: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "output_dir": str(self.output_dir),
            "record_types": self.record_types,
            "provinces": self.provinces,
            "years": self.years,
            "file_count": len(self.files),
            "total_rows": self.total_rows,
            "files": self.files,
        }

    def to_lines(self) -> list[str]:
        lines = [
            f"导出目录: {self.output_dir}",
            f"数据类型: {', '.join(self.record_types)}",
            f"省份: {', '.join(self.provinces)}",
            f"年份: {self.years if self.years else '全部'}",
            f"文件数: {len(self.files)}，总行数: {self.total_rows}",
        ]
        for item in self.files:
            lines.append(
                f"  {item['path']} ({item['rows']} 行)"
            )
        lines.append(f"清单: {self.output_dir / 'export_manifest.json'}")
        return lines


def _query_df(sql: str, params: dict | None = None) -> pd.DataFrame:
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
    )
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params or {})


def list_export_provinces(
    record_type: str = "school",
    years: list[int] | None = None,
) -> list[str]:
    spec = _TABLE_SPECS[record_type]
    table = spec["table"]
    conditions = ["province IS NOT NULL", "TRIM(province) != ''"]
    params: dict[str, Any] = {}
    if years:
        placeholders = ", ".join(f":y{i}" for i in range(len(years)))
        conditions.append(f"year IN ({placeholders})")
        params.update({f"y{i}": y for i, y in enumerate(years)})
    where = " AND ".join(conditions)
    df = _query_df(
        f"SELECT DISTINCT province FROM {table} WHERE {where} ORDER BY province",
        params,
    )
    return df["province"].tolist()


def export_province_csv(
    *,
    output_dir: Path | None = None,
    record_types: list[str] | None = None,
    provinces: list[str] | None = None,
    years: list[int] | None = None,
    split_by_year: bool = True,
) -> ProvinceCsvExportReport:
    """按省份分文件夹导出 CSV，默认每种类型按年份拆分文件。"""
    out_root = Path(output_dir or EXPORT_CSV_DIR)
    out_root.mkdir(parents=True, exist_ok=True)

    types = record_types or ["school"]
    for t in types:
        if t not in RECORD_TYPES:
            raise ValueError(f"不支持的数据类型: {t}")

    resolved_provinces = provinces
    if not resolved_provinces:
        seen: set[str] = set()
        resolved_provinces = []
        for t in types:
            for p in list_export_provinces(t, years):
                if p not in seen:
                    seen.add(p)
                    resolved_provinces.append(p)

    report = ProvinceCsvExportReport(
        output_dir=out_root,
        record_types=types,
        provinces=resolved_provinces,
        years=years,
    )

    if not resolved_provinces:
        logger.warning("数据库中无匹配省份数据，跳过导出")
        return report

    for record_type in types:
        spec = _TABLE_SPECS[record_type]
        table = spec["table"]
        for province in resolved_provinces:
            province_dir = out_root / province
            province_dir.mkdir(parents=True, exist_ok=True)

            conditions = ["province = :province"]
            params: dict[str, Any] = {"province": province}
            if years:
                placeholders = ", ".join(f":y{i}" for i in range(len(years)))
                conditions.append(f"year IN ({placeholders})")
                params.update({f"y{i}": y for i, y in enumerate(years)})

            where = " AND ".join(conditions)
            df = _query_df(
                f"""
                SELECT {spec["select"]}
                FROM {table}
                WHERE {where}
                ORDER BY {spec["order_by"]}
                """,
                params,
            )
            if df.empty:
                continue

            rename_map = spec["rename"]
            if split_by_year:
                for year, year_df in df.groupby("year", sort=False):
                    export_df = year_df.rename(columns=rename_map)
                    filename = f"{record_type}_{int(year)}.csv"
                    out_path = province_dir / filename
                    export_df.to_csv(out_path, index=False, encoding="utf-8-sig")
                    row_count = len(export_df)
                    report.files.append(
                        {
                            "province": province,
                            "record_type": record_type,
                            "year": int(year),
                            "path": str(out_path),
                            "rows": row_count,
                        }
                    )
                    report.total_rows += row_count
            else:
                export_df = df.rename(columns=rename_map)
                filename = f"{record_type}.csv"
                out_path = province_dir / filename
                export_df.to_csv(out_path, index=False, encoding="utf-8-sig")
                row_count = len(export_df)
                report.files.append(
                    {
                        "province": province,
                        "record_type": record_type,
                        "year": None,
                        "path": str(out_path),
                        "rows": row_count,
                    }
                )
                report.total_rows += row_count

    manifest_path = out_root / "export_manifest.json"
    manifest_path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report
