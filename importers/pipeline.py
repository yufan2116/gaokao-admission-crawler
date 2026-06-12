"""
Excel 数据处理流水线：parse → normalize → validate
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from normalizers import normalize_dataframe
from parsers.parse_excel import parse_excel
from parsers.subject_infer import infer_subject_from_filename
from validators.validate import ValidationResult, validate_dataframe

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """流水线输出。"""

    parsed_df: pd.DataFrame
    normalized_df: pd.DataFrame
    validation: ValidationResult
    source_path: Path

    @property
    def valid_df(self) -> pd.DataFrame:
        return self.validation.valid_df


def run_excel_pipeline(
    file_path: str | Path,
    data_type: str,
    year: int | None = None,
    province: str = "江苏",
    sheet_name: str | int = 0,
    subject_type_hint: str | None = None,
    subject_mode: object | None = None,
) -> PipelineResult:
    """
    执行 parse → normalize → validate。

    Returns:
        PipelineResult 含各阶段 DataFrame 与校验结果
    """
    path = Path(file_path)
    hint = subject_type_hint or infer_subject_from_filename(path.stem, subject_mode=subject_mode)

    parsed = parse_excel(
        path,
        data_type=data_type,
        sheet_name=sheet_name,
        default_year=year,
        default_province=province,
        subject_type_hint=hint,
        subject_mode=subject_mode,
    )

    normalized = normalize_dataframe(
        parsed,
        data_type=data_type,
        year=year,
        province=province,
        subject_type=hint,
        subject_mode=subject_mode,
    )

    validation = validate_dataframe(normalized, data_type)

    logger.info(
        "流水线完成 [%s]: parsed=%d normalized=%d valid=%d failed=%d",
        data_type,
        len(parsed),
        len(normalized),
        len(validation.valid_df),
        validation.failed_count,
    )

    return PipelineResult(
        parsed_df=parsed,
        normalized_df=normalized,
        validation=validation,
        source_path=path,
    )


def run_parsed_pipeline(
    parsed_df: pd.DataFrame,
    data_type: str,
    year: int | None = None,
    province: str = "江苏",
    subject_type: str | None = None,
    source_path: Path | None = None,
    admission_category: str | None = None,
    batch: str | None = None,
    subject_mode: object | None = None,
) -> PipelineResult:
    """对已 parse 的 DataFrame 执行 normalize → validate。"""
    normalized = normalize_dataframe(
        parsed_df,
        data_type=data_type,
        year=year,
        province=province,
        subject_type=subject_type,
        admission_category=admission_category,
        batch=batch,
        subject_mode=subject_mode,
    )
    validation = validate_dataframe(normalized, data_type)
    logger.info(
        "流水线完成 [%s]: parsed=%d normalized=%d valid=%d failed=%d",
        data_type,
        len(parsed_df),
        len(normalized),
        len(validation.valid_df),
        validation.failed_count,
    )
    return PipelineResult(
        parsed_df=parsed_df,
        normalized_df=normalized,
        validation=validation,
        source_path=source_path or Path("."),
    )


def enriched_rows_for_db(
    valid_df: pd.DataFrame,
    data_type: str,
    source_url: str | None = None,
) -> list[dict]:
    """
    为标准 DataFrame 补充入库所需字段（batch、school_code 等）。
    """
    rows: list[dict] = []
    for _, row in valid_df.iterrows():
        record = {k: (None if pd.isna(v) else v) for k, v in row.to_dict().items()}
        record["source_url"] = source_url

        if data_type == "school":
            if not record.get("admission_category"):
                record["admission_category"] = "普通类"
            if not record.get("batch"):
                record["batch"] = "本科批"
            if not record.get("school_code") and record.get("school_name"):
                record["school_code"] = record["school_name"]
        elif data_type == "major":
            if not record.get("batch"):
                record["batch"] = "本科批"
            if not record.get("school_code") and record.get("school_name"):
                record["school_code"] = record["school_name"]
            if not record.get("major_code") and record.get("major_name"):
                record["major_code"] = record["major_name"]

        rows.append(record)
    return rows
