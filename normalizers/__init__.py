"""
数据标准化层（Phase 4）。

parse_excel 输出 → normalize_xxx → 内部标准 DataFrame
"""

from __future__ import annotations

import pandas as pd

from normalizers.batch import normalize_batch
from normalizers.control_normalizer import CONTROL_COLUMNS, normalize_control
from normalizers.major_normalizer import MAJOR_COLUMNS, normalize_major
from normalizers.province import normalize_province
from normalizers.rank_normalizer import RANK_COLUMNS, normalize_rank
from normalizers.school_name import normalize_school_name
from normalizers.school_normalizer import SCHOOL_COLUMNS, normalize_school
from normalizers.subject_type import normalize_subject_type

NORMALIZERS = {
    "school": normalize_school,
    "rank": normalize_rank,
    "control": normalize_control,
    "major": normalize_major,
}

SCHEMA_COLUMNS = {
    "school": SCHOOL_COLUMNS,
    "rank": RANK_COLUMNS,
    "control": CONTROL_COLUMNS,
    "major": MAJOR_COLUMNS,
}


def normalize_dataframe(
    df: pd.DataFrame,
    data_type: str,
    year: int | None = None,
    province: str | None = None,
    subject_type: str | None = None,
    admission_category: str | None = None,
    batch: str | None = None,
    subject_mode: object | None = None,
) -> pd.DataFrame:
    """
    按数据类型调用对应 normalizer。

    Args:
        df: parse_excel 输出的 DataFrame
        data_type: school | rank | control | major
        year / province / subject_type: 默认值补全

    Returns:
        标准结构 DataFrame
    """
    if data_type not in NORMALIZERS:
        raise ValueError(f"不支持的 data_type: {data_type}")
    if data_type == "school":
        return normalize_school(
            df,
            year=year,
            province=province,
            subject_type=subject_type,
            admission_category=admission_category,
            batch=batch,
            subject_mode=subject_mode,
        )
    return NORMALIZERS[data_type](df, year=year, province=province, subject_type=subject_type)


__all__ = [
    "normalize_dataframe",
    "normalize_school",
    "normalize_rank",
    "normalize_control",
    "normalize_major",
    "normalize_province",
    "normalize_subject_type",
    "normalize_school_name",
    "normalize_batch",
    "NORMALIZERS",
    "SCHEMA_COLUMNS",
    "SCHOOL_COLUMNS",
    "RANK_COLUMNS",
    "CONTROL_COLUMNS",
    "MAJOR_COLUMNS",
]
