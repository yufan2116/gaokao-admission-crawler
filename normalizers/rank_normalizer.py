"""
一分一段表标准化。

标准 Schema:
    year, province, subject_type, score, same_score_count, cumulative_count
"""

from __future__ import annotations

import pandas as pd

from normalizers.common import apply_defaults, to_int

RANK_COLUMNS = [
    "year",
    "province",
    "subject_type",
    "score",
    "same_score_count",
    "cumulative_count",
]


def normalize_rank(
    df: pd.DataFrame,
    year: int | None = None,
    province: str | None = None,
    subject_type: str | None = None,
) -> pd.DataFrame:
    """将 parse 后的 DataFrame 转为 rank 标准结构。"""
    if df.empty:
        return pd.DataFrame(columns=RANK_COLUMNS)

    work = apply_defaults(df, RANK_COLUMNS, year, province, subject_type)
    work["year"] = work["year"].apply(to_int)
    work["score"] = work["score"].apply(to_int)
    work["same_score_count"] = work["same_score_count"].apply(to_int)
    work["cumulative_count"] = work["cumulative_count"].apply(to_int)

    return work[RANK_COLUMNS]
