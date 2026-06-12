"""
标准化后的 DataFrame 业务校验。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pandas as pd

from normalizers.common import empty_to_none

logger = logging.getLogger(__name__)

VALID_SUBJECT_TYPES = frozenset({
    "文科",
    "理科",
    "历史类",
    "物理类",
    "综合改革",
})

MIN_SCORE = 100
MAX_SCORE = 750


@dataclass
class ValidationResult:
    """校验结果。"""

    valid_df: pd.DataFrame
    failed_count: int = 0
    errors: list[str] = field(default_factory=list)


def _is_empty(value) -> bool:
    return empty_to_none(value) is None


def _validate_school_row(row: dict, row_num: int) -> str | None:
    required = ["year", "province", "subject_type", "school_name"]
    missing = [f for f in required if _is_empty(row.get(f))]
    if missing:
        return f"第 {row_num} 行缺少必填字段: {', '.join(missing)}"

    if _is_empty(row.get("min_score")) and _is_empty(row.get("min_rank")):
        return f"第 {row_num} 行缺少 min_score 或 min_rank"

    if not _is_empty(row.get("min_score")):
        score = row.get("min_score")
        try:
            score_f = float(score)
        except (TypeError, ValueError):
            return f"第 {row_num} 行 min_score 无效: {score}"
        if not (MIN_SCORE <= score_f <= MAX_SCORE):
            return f"第 {row_num} 行 min_score 超出范围 [{MIN_SCORE}, {MAX_SCORE}]: {score_f}"

    st = str(row.get("subject_type", "")).strip()
    if st not in VALID_SUBJECT_TYPES:
        return f"第 {row_num} 行 subject_type 无效: {st}，须为 {sorted(VALID_SUBJECT_TYPES)}"

    return None


def _validate_rank_row(row: dict, row_num: int) -> str | None:
    required = ["year", "province", "subject_type", "score", "cumulative_count"]
    missing = [f for f in required if _is_empty(row.get(f))]
    if missing:
        return f"第 {row_num} 行缺少必填字段: {', '.join(missing)}"

    st = str(row.get("subject_type", "")).strip()
    if st not in VALID_SUBJECT_TYPES:
        return f"第 {row_num} 行 subject_type 无效: {st}"

    return None


def _validate_rank_monotonic(df: pd.DataFrame) -> list[str]:
    """累计人数应随分数下降而非递减（高分段累计少）。"""
    errors: list[str] = []
    if "score" not in df.columns or "cumulative_count" not in df.columns:
        return errors

    work = df.dropna(subset=["score", "cumulative_count"]).copy()
    if len(work) < 2:
        return errors

    # 按分数降序：累计人数应递增（或持平）
    work = work.sort_values("score", ascending=False)
    prev_cum = None
    for idx, row in work.iterrows():
        cum = row["cumulative_count"]
        if prev_cum is not None and cum < prev_cum:
            errors.append(
                f"行 {idx} 累计人数未递增: score={row['score']} "
                f"cumulative={cum} < 前一行 {prev_cum}"
            )
        prev_cum = cum
    return errors


def _validate_control_row(row: dict, row_num: int) -> str | None:
    required = ["year", "province", "subject_type", "batch", "score"]
    missing = [f for f in required if _is_empty(row.get(f))]
    if missing:
        return f"第 {row_num} 行缺少必填字段: {', '.join(missing)}"

    if _is_empty(row.get("score")):
        return f"第 {row_num} 行 score 不存在"

    st = str(row.get("subject_type", "")).strip()
    if st not in VALID_SUBJECT_TYPES:
        return f"第 {row_num} 行 subject_type 无效: {st}"

    return None


def _validate_major_row(row: dict, row_num: int) -> str | None:
    required = ["year", "province", "subject_type", "school_name", "major_name", "min_score"]
    missing = [f for f in required if _is_empty(row.get(f))]
    if missing:
        return f"第 {row_num} 行缺少必填字段: {', '.join(missing)}"

    if _is_empty(row.get("major_name")):
        return f"第 {row_num} 行 major_name 为空"

    score = row.get("min_score")
    try:
        score_f = float(score)
    except (TypeError, ValueError):
        return f"第 {row_num} 行 min_score 无效: {score}"
    if not (MIN_SCORE <= score_f <= MAX_SCORE):
        return f"第 {row_num} 行 min_score 超出范围 [{MIN_SCORE}, {MAX_SCORE}]: {score_f}"

    return None


_ROW_VALIDATORS = {
    "school": _validate_school_row,
    "rank": _validate_rank_row,
    "control": _validate_control_row,
    "major": _validate_major_row,
}


def validate_dataframe(df: pd.DataFrame, data_type: str) -> ValidationResult:
    """
    校验标准化后的 DataFrame，返回通过行与错误列表。

    单行失败不中断，过滤掉无效行。
    """
    if data_type not in _ROW_VALIDATORS:
        raise ValueError(f"不支持的 data_type: {data_type}")

    if df.empty:
        return ValidationResult(valid_df=df)

    validator = _ROW_VALIDATORS[data_type]
    valid_indices: list[int] = []
    errors: list[str] = []

    for i, (_, row) in enumerate(df.iterrows(), start=1):
        row_dict = {k: (None if pd.isna(v) else v) for k, v in row.to_dict().items()}
        err = validator(row_dict, i)
        if err:
            errors.append(err)
            logger.warning(err)
        else:
            valid_indices.append(row.name)

    valid_df = df.loc[valid_indices].copy() if valid_indices else df.iloc[0:0].copy()

    # rank 表级校验：累计人数递增
    if data_type == "rank" and not valid_df.empty:
        mono_errors = _validate_rank_monotonic(valid_df)
        if mono_errors:
            errors.extend(mono_errors)
            logger.warning("rank 累计人数校验: %s", mono_errors[0])

    return ValidationResult(
        valid_df=valid_df,
        failed_count=len(errors),
        errors=errors,
    )
