"""
Normalizer 公共工具：空值处理、类型转换、列筛选。
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from typing import Any

from normalizers.province import normalize_province
from normalizers.subject_type import normalize_subject_type


def empty_to_none(value: Any) -> Any:
    """空字符串 / NaN / 空白 → None。"""
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return value


def to_int(value: Any) -> int | None:
    """转为 int，失败返回 None。"""
    value = empty_to_none(value)
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def to_float(value: Any) -> float | None:
    """转为 float，失败返回 None。"""
    value = empty_to_none(value)
    if value is None:
        return None
    if isinstance(value, (int, float)) and not (isinstance(value, float) and pd.isna(value)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    head = re.split(r"[\n(（]", text, maxsplit=1)[0].strip()
    match = re.search(r"[\d.]+", head)
    if match:
        try:
            return float(match.group())
        except ValueError:
            pass
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def to_str(value: Any) -> str | None:
    """转为非空字符串，空则 None。"""
    value = empty_to_none(value)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def apply_defaults(
    df: pd.DataFrame,
    columns: list[str],
    year: int | None = None,
    province: str | None = None,
    subject_type: str | None = None,
    subject_mode: Any = None,
) -> pd.DataFrame:
    """补充 year / province / subject_type 默认值。"""
    out = df.copy()
    if year is not None and "year" not in out.columns:
        out["year"] = year
    if province is not None and "province" not in out.columns:
        out["province"] = province
    if subject_type and "subject_type" not in out.columns:
        out["subject_type"] = subject_type

    if "year" in out.columns and year is not None:
        out["year"] = out["year"].apply(lambda x: to_int(x) if empty_to_none(x) is not None else year)
    if "province" in out.columns:
        out["province"] = out["province"].apply(
            lambda x: normalize_province(x) if empty_to_none(x) else normalize_province(province or "")
        )
    elif province:
        out["province"] = normalize_province(province)

    if "subject_type" in out.columns:
        out["subject_type"] = out["subject_type"].apply(
            lambda x: normalize_subject_type(x, subject_mode=subject_mode)
        )
    elif subject_type:
        out["subject_type"] = normalize_subject_type(subject_type, subject_mode=subject_mode)

    return _select_columns(out, columns)


def _select_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """只保留标准列，缺失列补 None。"""
    result = pd.DataFrame()
    for col in columns:
        if col in df.columns:
            result[col] = df[col]
        else:
            result[col] = None
    return result
