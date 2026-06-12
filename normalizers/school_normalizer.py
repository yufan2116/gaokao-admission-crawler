"""
院校投档线标准化。

标准 Schema:
    year, province, subject_type, admission_category, batch,
    school_code, school_name, major_group, min_score, min_rank,
    tie_breaker_text, plan_count
"""

from __future__ import annotations

import re

import pandas as pd

from normalizers.admission_category import normalize_admission_category
from normalizers.common import apply_defaults, empty_to_none, to_float, to_int, to_str
from normalizers.school_batch import normalize_school_batch
from normalizers.school_name import normalize_school_name

_COMBINED_SCHOOL_RE = re.compile(r"^([A-Za-z]\d{3,4})(.+)$")
_COMBINED_MAJOR_RE = re.compile(r"^(\d{1,3})(\S.+)$")


def _split_combined_school_fields(code: str | None, name: str | None) -> tuple[str | None, str | None]:
    """拆分「院校代号及名称」类合并字段，如 A001北京大学。"""
    for value in (code, name):
        if not value:
            continue
        text = str(value).strip()
        match = _COMBINED_SCHOOL_RE.match(text)
        if match:
            return match.group(1), match.group(2).strip()
    return code, name


def _split_combined_major_field(major_code: str | None, major_name: str | None) -> tuple[str | None, str | None]:
    """拆分「专业代号及名称」类合并字段，如 17文科试验班类。"""
    for value in (major_code, major_name):
        if not value:
            continue
        text = str(value).strip()
        match = _COMBINED_MAJOR_RE.match(text)
        if match:
            return match.group(1), match.group(2).strip()
    return major_code, major_name


SCHOOL_COLUMNS = [
    "year",
    "province",
    "subject_type",
    "admission_category",
    "batch",
    "school_code",
    "school_name",
    "major_group",
    "min_score",
    "min_rank",
    "tie_breaker_text",
    "plan_count",
]


def normalize_school(
    df: pd.DataFrame,
    year: int | None = None,
    province: str | None = None,
    subject_type: str | None = None,
    admission_category: str | None = None,
    batch: str | None = None,
    subject_mode: object | None = None,
) -> pd.DataFrame:
    """将 parse 后的 DataFrame 转为 school 标准结构。"""
    if df.empty:
        return pd.DataFrame(columns=SCHOOL_COLUMNS)

    work = apply_defaults(df, SCHOOL_COLUMNS, year, province, subject_type, subject_mode)

    # 公告标题推断优先于 parse_excel 默认 batch=本科批
    if admission_category:
        work["admission_category"] = normalize_admission_category(admission_category) or "普通类"
    if batch:
        work["batch"] = normalize_school_batch(batch) or "本科批"

    work["admission_category"] = work["admission_category"].apply(
        lambda x: normalize_admission_category(to_str(x)) if empty_to_none(x) else "普通类"
    )
    work["batch"] = work["batch"].apply(
        lambda x: normalize_school_batch(to_str(x)) if empty_to_none(x) else "本科批"
    )
    work["school_code"] = work["school_code"].apply(to_str)
    work["school_name"] = work["school_name"].apply(
        lambda x: normalize_school_name(to_str(x)) if empty_to_none(x) else None
    )
    work["major_group"] = work["major_group"].apply(to_str)
    work["min_score"] = work["min_score"].apply(to_float)
    work["min_rank"] = work["min_rank"].apply(to_int)
    work["plan_count"] = work["plan_count"].apply(to_int)
    work["tie_breaker_text"] = work["tie_breaker_text"].apply(to_str)
    work["year"] = work["year"].apply(to_int)

    for idx in work.index:
        mc = to_str(df.at[idx, "major_code"]) if "major_code" in df.columns else None
        mn = to_str(df.at[idx, "major_name"]) if "major_name" in df.columns else None
        mc, mn = _split_combined_major_field(mc, mn)
        if empty_to_none(work.at[idx, "major_group"]):
            pass
        elif mc and mn:
            work.at[idx, "major_group"] = f"{mc}-{mn}"
        elif mc:
            work.at[idx, "major_group"] = mc
        elif mn:
            work.at[idx, "major_group"] = mn

        code = work.at[idx, "school_code"]
        name = work.at[idx, "school_name"]
        major_group = work.at[idx, "major_group"]
        code, name = _split_combined_school_fields(code, name)
        if not code and name:
            code, name = _split_combined_school_fields(name, None)
        if not name and code:
            code, name = _split_combined_school_fields(code, None)
        work.at[idx, "school_code"] = code
        work.at[idx, "school_name"] = name
        cat = work.at[idx, "admission_category"]
        if major_group and cat in ("艺术类", "体育类") and (not name or name == code):
            work.at[idx, "school_name"] = major_group

    return work[SCHOOL_COLUMNS]
