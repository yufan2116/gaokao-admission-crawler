"""
省控线标准化。

标准 Schema:
    year, province, subject_type, batch, score
"""

from __future__ import annotations

import pandas as pd

from normalizers.batch import normalize_batch
from normalizers.common import apply_defaults, empty_to_none, to_int, to_str

CONTROL_COLUMNS = [
    "year",
    "province",
    "subject_type",
    "batch",
    "score",
]


def normalize_control(
    df: pd.DataFrame,
    year: int | None = None,
    province: str | None = None,
    subject_type: str | None = None,
) -> pd.DataFrame:
    """将 parse 后的 DataFrame 转为 control 标准结构。"""
    if df.empty:
        return pd.DataFrame(columns=CONTROL_COLUMNS)

    work = apply_defaults(df, CONTROL_COLUMNS, year, province, subject_type)
    work["year"] = work["year"].apply(to_int)
    work["batch"] = work["batch"].apply(
        lambda x: normalize_batch(to_str(x)) if empty_to_none(x) else None
    )
    work["score"] = work["score"].apply(to_int)

    return work[CONTROL_COLUMNS]
