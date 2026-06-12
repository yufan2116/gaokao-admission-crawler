"""
Excel 解析结果校验与入库编排。

流程：parse → normalize → validate → database
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from db.repository import (
    InsertResult,
    insert_major_admission_lines,
    insert_province_control_lines,
    insert_school_admission_lines,
    insert_score_rank_rows,
)
from importers.pipeline import enriched_rows_for_db, run_excel_pipeline

logger = logging.getLogger(__name__)

RECORD_TYPES = {
    "control": "control",
    "school": "school",
    "major": "major",
    "rank": "rank",
}


@dataclass
class ImportStats:
    """导入全流程统计。"""

    inserted: int = 0
    skipped: int = 0
    failed: int = 0
    validation_failed: int = 0
    errors: list[str] = field(default_factory=list)


def import_excel_to_db(
    session: Session,
    file_path: str | Path,
    record_type: str,
    default_year: int | None = None,
    default_province: str = "江苏",
    sheet_name: str | int = 0,
    subject_type: str | None = None,
) -> ImportStats:
    """
    Excel → parse → normalize → validate → SQLite 入库。
    """
    if record_type not in RECORD_TYPES:
        raise ValueError(f"不支持的 type: {record_type}")

    path = Path(file_path)
    source_url = str(path.resolve()) if path.exists() else None

    pipeline = run_excel_pipeline(
        path,
        data_type=record_type,
        year=default_year,
        province=default_province,
        sheet_name=sheet_name,
        subject_type_hint=subject_type,
    )

    stats = ImportStats()
    stats.validation_failed = pipeline.validation.failed_count
    stats.failed = pipeline.validation.failed_count
    stats.errors.extend(pipeline.validation.errors)

    valid_df = pipeline.valid_df
    if valid_df.empty:
        logger.warning("校验后无有效行可入库: %s", path)
        return stats

    valid_rows = enriched_rows_for_db(valid_df, record_type, source_url)

    inserters: dict[str, Any] = {
        "control": insert_province_control_lines,
        "school": insert_school_admission_lines,
        "major": insert_major_admission_lines,
        "rank": insert_score_rank_rows,
    }
    insert_result: InsertResult = inserters[record_type](session, valid_rows)

    stats.inserted = insert_result.inserted
    stats.skipped = insert_result.skipped
    stats.failed += insert_result.failed
    stats.errors.extend(insert_result.errors)

    return stats
