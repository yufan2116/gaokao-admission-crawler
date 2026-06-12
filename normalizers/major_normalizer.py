"""
专业录取线标准化。

标准 Schema:
    year, province, subject_type, school_name, major_name, min_score, min_rank
"""

from __future__ import annotations

import pandas as pd

from normalizers.common import apply_defaults, to_int, to_str
from normalizers.school_name import normalize_school_name

MAJOR_COLUMNS = [
    "year",
    "province",
    "subject_type",
    "school_name",
    "major_name",
    "min_score",
    "min_rank",
]


def normalize_major(
    df: pd.DataFrame,
    year: int | None = None,
    province: str | None = None,
    subject_type: str | None = None,
) -> pd.DataFrame:
    """将 parse 后的 DataFrame 转为 major 标准结构。"""
    if df.empty:
        return pd.DataFrame(columns=MAJOR_COLUMNS)

    work = apply_defaults(df, MAJOR_COLUMNS, year, province, subject_type)
    work["year"] = work["year"].apply(to_int)
    work["school_name"] = work["school_name"].apply(
        lambda x: normalize_school_name(to_str(x)) if to_str(x) else None
    )
    work["major_name"] = work["major_name"].apply(to_str)
    work["min_score"] = work["min_score"].apply(to_int)
    work["min_rank"] = work["min_rank"].apply(to_int)

    return work[MAJOR_COLUMNS]
